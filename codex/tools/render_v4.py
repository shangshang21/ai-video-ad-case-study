from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from PIL import Image, ImageDraw, ImageFont
from scipy import signal

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / ".codex-work" / "v4"
WORK.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "codex/build/v4"
SOURCE = ROOT / "assets/05-video/粗剪_全片_v1.mp4"
CLAUDE = ROOT / "assets/05-video/粗剪_全片_v3.mp4"
CLAUDE32 = ROOT / "assets/05-video/粗剪_全片_v3.2.mp4"
FFMPEG = shutil.which("ffmpeg")
FPS = 24
WIDTH, HEIGHT = 1920, 1080
TOTAL_FRAMES = 720

# Source ranges are seconds; every output length is an integer number of frames.
SHOTS = [
    dict(name="夜色", source="original", start=0.25, length=1.25, frames=30),
    dict(name="红色的预告", source="original", start=1.625, length=0.75, frames=18),
    dict(name="睁眼转头连续拉远_Claude新版", source="claude", start=2.9166667, length=5.5, frames=126),
    dict(name="捏起缓推接开盖_Claude最新版v3.2", source="claude32", start=9.25, length=2.25, frames=54),
    dict(name="膏体", source="original", start=11.875, length=1.0, frames=24),
    dict(name="最后一笔", source="bridge", start=1.5, length=2.75, frames=48),
    dict(name="倒影", source="original", start=15.125, length=1.0, frames=24),
    dict(name="面向城市", source="original", start=16.75, length=1.0, frames=24),
    dict(name="红色漫过夜空", source="original", start=18.375, length=2.5, frames=60),
    dict(name="红色成裙_压缩过程", source="claude", start=22.875, length=2.75, frames=42),
    dict(name="连续后拉到全身_Claude完整段落", source="claude", start=25.625, length=4.75, frames=108),
    dict(name="合盖近景_Claude新版", source="claude", start=30.5, length=4.4166667, frames=90, endcard=True),
    dict(name="近景品牌停留", source="claude", start=35.375, length=1/24, frames=72, endcard=True, freeze=True),
]


def run(args: list[str], log_name: str):
    result = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (WORK / log_name).write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"{log_name}: {result.stderr.decode('utf-8', errors='replace')[-2500:]}")


def tracked(draw, position, text, font, fill, spacing):
    x, y = position
    for char in text:
        draw.text((int(x), y), char, font=font, fill=fill)
        x += draw.textlength(char, font=font) + spacing


def make_titles():
    # Use an earlier, clean frame as the left-side video plate. This retains the
    # room and bokeh while covering the wording baked into Claude's compressed cut.
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", "34", "-i", str(CLAUDE), "-vf", "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos,crop=1920:1080,setsar=1,hqdn3d=1.0:1.0:2.0:2.0,eq=gamma=1.035:saturation=1.02", "-frames:v", "1", str(WORK / "clean-plate.png")], "clean-plate.log")
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    plate = Image.open(WORK / "clean-plate.png").convert("RGBA")
    pixels = np.asarray(plate).copy()
    for x in range(WIDTH):
        alpha = 255 if x < 930 else int(255 * max(0, 1 - (x - 930) / 160))
        pixels[:, x, 3] = alpha
    panel = Image.fromarray(pixels)
    panel.save(WORK / "end-panel.png")
    draw = ImageDraw.Draw(overlay)
    brand = ImageFont.truetype("C:/Windows/Fonts/times.ttf", 76)
    italic = ImageFont.truetype("C:/Windows/Fonts/timesi.ttf", 52)
    tiny = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 17)
    tracked(draw, (128, 402), "NOCTELLE", brand, (238, 226, 204, 255), 9)
    draw.line((132, 512, 250, 512), fill=(157, 117, 69, 255), width=2)
    draw.text((128, 552), "Wear the Night.", font=italic, fill=(224, 215, 203, 255))
    tracked(draw, (133, 661), "L I P  C O L O R", tiny, (177, 156, 131, 255), 2)
    overlay.save(WORK / "end-type.png")


def render_shot(index, shot):
    duration = shot["frames"] / FPS
    source = {"original": SOURCE, "claude": CLAUDE, "claude32": CLAUDE32, "bridge": ROOT / "codex/assets/source/bridge_generated.mp4"}[shot["source"]]
    output = WORK / "segments" / f"{index:02d}.mp4"
    inputs = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{shot['start']:.8f}", "-i", str(source)]
    filters = []
    if shot.get("freeze"):
        filters += ["trim=end_frame=1", "setpts=PTS-STARTPTS", f"tpad=stop_mode=clone:stop_duration={duration+0.1}"]
    else:
        factor = duration / shot["length"]
        filters += [f"trim=duration={shot['length']:.8f}", f"setpts=(PTS-STARTPTS)*{factor:.10f}"]
    filters += [
        "fps=24",
        "scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos",
        "crop=1920:1080",
        "setsar=1",
    ]
    if shot["source"] == "bridge":
        filters += ["eq=brightness=-0.018:saturation=0.94:contrast=1.012"]
    elif shot["source"].startswith("claude"):
        filters += ["hqdn3d=1.0:1.0:2.0:2.0", "eq=gamma=1.035:saturation=1.02"]
    else:
        filters += ["eq=saturation=0.98:contrast=1.008"]
    if index == 0:
        filters += ["fade=t=in:st=0:d=0.25"]
    if shot.get("endcard"):
        inputs += ["-i", str(WORK / "end-panel.png"), "-i", str(WORK / "end-type.png")]
        graph = "[0:v]" + ",".join(filters) + "[base];"
        if shot.get("freeze"):
            graph += "[base][1:v]overlay=0:0[panel];[2:v]format=rgba,fade=t=in:st=0.15:d=0.6:alpha=1[title];[panel][title]overlay=0:0,format=yuv420p[v]"
        else:
            graph += "[base][1:v]overlay=0:0:enable='gte(t,3.10)',format=yuv420p[v]"
        # Loop the transparent type input so its fade advances at video frame rate.
        inputs = inputs[:-4] + ["-loop", "1", "-framerate", "24", "-i", str(WORK / "end-panel.png"), "-loop", "1", "-framerate", "24", "-i", str(WORK / "end-type.png")]
        args = inputs + ["-filter_complex", graph, "-map", "[v]"]
    else:
        args = inputs + ["-vf", ",".join(filters)]
    args += ["-an", "-frames:v", str(shot["frames"]), "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-threads", "4", "-video_track_timescale", "12288", str(output)]
    run(args, f"render-{index:02d}.log")
    return {"index": index, "name": shot["name"], "frames": shot["frames"], "file": str(output)}


def render_picture():
    OUT.mkdir(parents=True, exist_ok=True)
    (WORK / "segments").mkdir(exist_ok=True)
    make_titles()
    assert sum(x["frames"] for x in SHOTS) == TOTAL_FRAMES
    timeline = []
    cursor = 0
    for i, shot in enumerate(SHOTS):
        timeline.append(dict(shot, index=i, output_start=cursor/FPS, output_end=(cursor+shot["frames"])/FPS))
        cursor += shot["frames"]
    (WORK / "timeline.json").write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(render_shot, i, shot) for i, shot in enumerate(SHOTS)]
        for f in concurrent.futures.as_completed(futures):
            result = f.result()
            print(json.dumps(result, ensure_ascii=False), flush=True)
    concat = WORK / "picture-concat.txt"
    concat.write_text("\n".join("file '" + (WORK / "segments" / f"{i:02d}.mp4").as_posix() + "'" for i in range(len(SHOTS))), encoding="utf-8")
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(WORK / "picture-locked.mp4")], "concat-picture.log")
    print("PICTURE_READY", flush=True)


def add_soundtrack():
    sr = 48000
    n = int(30 * sr)
    rng = np.random.default_rng(117)
    t = np.arange(n, dtype=np.float64) / sr
    bed = np.zeros((n, 2), dtype=np.float64)
    foley = np.zeros_like(bed)
    music = np.zeros_like(bed)

    def paste(track, audio, start, gain=1.0):
        i = int(round(start * sr))
        a = np.asarray(audio)
        if a.ndim == 1:
            a = np.column_stack([a, a])
        if i < 0:
            a = a[-i:]
            i = 0
        size = min(len(a), len(track) - i)
        if size > 0:
            track[i:i+size] += a[:size] * gain

    # A very quiet, warm musical floor bridges the edited generated cue.
    env = np.minimum(t / 2.0, 1) * np.clip((30-t)/2.0, 0, 1)
    for k, freq in enumerate((73.4162, 110.0, 146.8324, 164.8138, 174.6141)):
        for ch, detune in enumerate((-0.0012, 0.0012)):
            tone = np.sin(2*np.pi*freq*(1+detune)*t + k*.7)
            tone += .17*np.sin(2*np.pi*freq*2*(1+detune)*t + k)
            bed[:, ch] += tone * env * (0.004 if k < 2 else .002)
    noise = rng.normal(0, 1, n)
    air = signal.sosfilt(signal.butter(2, (150, 1800), btype="bandpass", fs=sr, output="sos"), noise)
    bed[:, 0] += air * .0012 * env
    bed[:, 1] += np.roll(air, 287) * .0012 * env

    # Synthetic, original close-up foley. No downloaded effects are used.
    def click(duration=.14, strength=1):
        tt = np.arange(int(duration*sr))/sr
        nn = rng.normal(size=len(tt))
        nn = signal.sosfilt(signal.butter(2, (450, 6500), btype="bandpass", fs=sr, output="sos"), nn)
        transient = nn*np.exp(-tt*105)*.045
        body = (np.sin(2*np.pi*1450*tt)+.45*np.sin(2*np.pi*2300*tt))*np.exp(-tt*72)*.018
        return (transient+body)*strength

    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", "9.25", "-i", str(CLAUDE32), "-t", "2.25", "-vn", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(WORK / "opening-native.wav")], "opening-audio.log")
    opening_audio, _ = sf.read(WORK / "opening-native.wav", always_2d=True)
    opening_t = np.arange(len(opening_audio))/sr
    opening_audio *= np.minimum(opening_t/.08,1)[:,None] * np.clip((2.25-opening_t)/.1,0,1)[:,None]
    paste(foley, opening_audio, 7.25, .6)
    run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", "30.5", "-i", str(CLAUDE), "-t", "4.4166667", "-vn", "-af", "atempo=1.17777778", "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(WORK / "closing-native.wav")], "closing-audio.log")
    close_audio, _ = sf.read(WORK / "closing-native.wav", always_2d=True)
    close_t = np.arange(len(close_audio))/sr
    close_audio *= np.minimum(close_t/.1,1)[:,None] * np.clip((3.75-close_t)/.12,0,1)[:,None]
    # Keep the sound generated with the close-up in sync with its retimed motion.
    paste(foley, close_audio, 23.25, .75)
    for start, duration, gain in ((14.4, 2.4, .012), (16.8, .9, .01), (17.65, 1.05, .009)):
        tt = np.arange(int(duration*sr))/sr
        nn = rng.normal(size=len(tt))
        nn = signal.sosfilt(signal.butter(2, (250, 4500), btype="bandpass", fs=sr, output="sos"), nn)
        shape = np.sin(np.pi*np.clip(tt/duration,0,1))**2
        motion = np.column_stack([nn*shape, np.roll(nn, 300)*shape])
        paste(foley, motion, start, gain)

    score_path = ROOT / "codex/assets/source/score_generated.mp4"
    if score_path.exists():
        wav_path = WORK / "score-raw.wav"
        run([FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-i", str(score_path), "-vn", "-ar", str(sr), "-ac", "2", "-c:a", "pcm_s24le", str(wav_path)], "extract-score.log")
        score, source_sr = sf.read(wav_path, always_2d=True)
        assert source_sr == sr
        peak = np.max(np.abs(score))
        if peak < 1e-5:
            raise RuntimeError("Generated score is silent")
        score = score / peak * .37
        # First a restrained opening excerpt, then the complete cue at the product reveal.
        intro = score[:int(6.3*sr)].copy()
        intro *= np.minimum(np.arange(len(intro))/sr/.65,1)[:,None]
        intro *= np.clip((6.3-np.arange(len(intro))/sr)/1.0,0,1)[:,None]
        paste(music, intro, 0, .48)
        prelude = score[int(1.0*sr):int(4.5*sr)].copy()
        prelude_t = np.arange(len(prelude))/sr
        prelude *= np.minimum(prelude_t/.5,1)[:,None]
        prelude *= np.clip((3.5-prelude_t)/.65,0,1)[:,None]
        paste(music, prelude, 5.8, .34)
        main = score.copy()
        main *= np.minimum(np.arange(len(main))/sr/.65,1)[:,None]
        main *= np.clip((len(main)/sr-np.arange(len(main))/sr)/1.0,0,1)[:,None]
        paste(music, main, 9.25, .82)
        # Extend the resolving tail into the brand hold with filtered reverb taps.
        tail = score[-int(2*sr):].copy()
        for delay, gain in ((24.25,.16),(25.35,.11),(26.45,.075),(27.55,.04)):
            paste(music, tail, delay, gain)
        score_kind = "MiniMax-H3 generated instrumental, edited and mixed locally"
    else:
        raise RuntimeError("Generated score not yet available")

    # Musical ducking makes space for the cap, without a broadband whoosh on each cut.
    duck = np.ones(n)
    for center, width, depth in ((8.70,.20,.60),(26.25,.22,.42)):
        duck *= 1 - depth * np.exp(-.5*((t-center)/width)**2)
    music *= duck[:,None]
    end_env = np.clip((30-t)/.8,0,1)
    mixed = (music + bed + foley) * end_env[:,None]
    # Endpoints are tapered to avoid an audible digital cut.
    mixed *= np.minimum(t/.025,1)[:,None]
    sf.write(WORK / "mix-premaster.wav", mixed, sr, subtype="PCM_24")
    sf.write(WORK / "music-stem.wav", music + bed, sr, subtype="PCM_24")
    sf.write(WORK / "foley-stem.wav", foley, sr, subtype="PCM_24")
    (WORK / "audio-origin.json").write_text(json.dumps({"score":score_kind,"effects":"Native opening from Claude v3.2; native closing from Claude v3; synthesized cloth and atmosphere","duration":30,"sample_rate":sr},indent=2), encoding="utf-8")
    # Measure first, then preserve the cue's intentional opening and resolving dynamics.
    run([FFMPEG,"-hide_banner","-loglevel","info","-i",str(WORK / "mix-premaster.wav"),"-af","loudnorm=I=-17:TP=-1.5:LRA=21:print_format=json","-f","null","-"],"audio-analysis.log")
    analysis = (WORK / "audio-analysis.log").read_text(encoding="utf-8", errors="replace")
    measured = json.loads(re.findall(r'\{\s*"input_i".*?\}', analysis, flags=re.S)[-1])
    normalization = (
        "loudnorm=I=-17:TP=-1.5:LRA=21:linear=true:print_format=json"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}"
    )
    run([FFMPEG,"-y","-hide_banner","-loglevel","info","-i",str(WORK / "mix-premaster.wav"),"-af",normalization,"-ar",str(sr),"-c:a","pcm_s24le",str(WORK / "mix-master.wav")],"audio-master.log")
    run([FFMPEG,"-y","-hide_banner","-loglevel","error","-i",str(WORK / "picture-locked.mp4"),"-i",str(WORK / "mix-master.wav"),"-map","0:v:0","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18","-maxrate","6M","-bufsize","12M","-pix_fmt","yuv420p","-c:a","aac","-b:a","320k","-ar","48000","-t","30","-metadata","title=NOCTELLE — Wear the Night | Fusion Cut v4","-movflags","+faststart",str(OUT / "NOCTELLE_融合精剪_v4_30秒.mp4")],"mux-final.log")
    shutil.copy2(WORK / "mix-master.wav", OUT / "NOCTELLE_配乐与音效混音.wav")
    print("FILM_READY", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["picture", "audio", "all"])
    args = parser.parse_args()
    if args.stage in ("picture", "all"):
        render_picture()
    if args.stage in ("audio", "all"):
        add_soundtrack()
