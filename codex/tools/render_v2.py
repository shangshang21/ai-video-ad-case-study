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
WORK = ROOT / ".codex-work" / "v2"
WORK.mkdir(parents=True, exist_ok=True)
OUT = ROOT / "codex/build/v2"
SOURCE = ROOT / "assets/05-video/粗剪_全片_v1.mp4"
FFMPEG = shutil.which("ffmpeg")
FPS = 24
WIDTH, HEIGHT = 1920, 1080
TOTAL_FRAMES = 648

# Source ranges are seconds; every output length is an integer number of frames.
SHOTS = [
    dict(name="夜色", source="original", start=0.25, length=1.0, frames=24),
    dict(name="目光", source="original", start=2.75, length=1.5, frames=36),
    dict(name="红色的预告", source="original", start=1.625, length=0.75, frames=18),
    dict(name="选择", source="original", start=4.875, length=1.0, frames=24),
    dict(name="触碰", source="original", start=8.375, length=1.25, frames=30),
    dict(name="开盖", source="original", start=10.125, length=1.0, frames=24),
    dict(name="膏体", source="original", start=11.875, length=1.0, frames=24),
    dict(name="最后一笔", source="bridge", start=1.5, length=2.75, frames=48),
    dict(name="倒影", source="original", start=15.125, length=1.0, frames=24),
    dict(name="面向城市", source="original", start=16.75, length=1.0, frames=24),
    dict(name="红色漫过夜空", source="original", start=18.375, length=2.5, frames=60),
    dict(name="红色涌入", source="original", start=21.4166667, length=0.75, frames=18),
    dict(name="红裙完成", source="original", start=23.25, length=1.0, frames=24),
    dict(name="气场", source="original", start=25.3333333, length=2.25, frames=54),
    dict(name="直视", source="original", start=28.2083333, length=1.75, frames=42),
    dict(name="唇色回响", source="original", start=30.4166667, length=0.3333333, frames=12),
    dict(name="产品回响", source="original", start=11.9583333, length=0.75, frames=18),
    dict(name="合盖", source="original", start=31.5, length=3.125, frames=60, endcard=True),
    dict(name="品牌停留", source="still", start=34.625, length=1/24, frames=84, endcard=True),
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
    # This is a native video title overlay; the original product photograph is retained.
    overlay = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pixels = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    for x in range(WIDTH):
        alpha = 255 if x < 930 else int(255 * max(0, 1 - (x - 930) / 300))
        pixels[:, x, :3] = (9, 8, 8)
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
    source = ROOT / "codex/assets/source/bridge_generated.mp4" if shot["source"] == "bridge" else SOURCE
    output = WORK / "segments" / f"{index:02d}.mp4"
    inputs = [FFMPEG, "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{shot['start']:.8f}", "-i", str(source)]
    filters = []
    if shot["source"] == "still":
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
    else:
        filters += ["eq=saturation=0.98:contrast=1.008"]
    if index == 0:
        filters += ["fade=t=in:st=0:d=0.25"]
    if shot.get("endcard"):
        inputs += ["-i", str(WORK / "end-panel.png"), "-i", str(WORK / "end-type.png")]
        graph = "[0:v]" + ",".join(filters) + "[base];[base][1:v]overlay=0:0[panel];"
        if shot["source"] == "still":
            graph += "[panel][2:v]overlay=0:0,format=yuv420p[v]"
        else:
            graph += "[2:v]format=rgba,fade=t=in:st=0.25:d=0.65:alpha=1[title];[panel][title]overlay=0:0,format=yuv420p[v]"
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
    n = int(27 * sr)
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
    env = np.minimum(t / 2.0, 1) * np.clip((27-t)/2.0, 0, 1)
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

    paste(foley, click(.12, .6), 5.12)
    paste(foley, click(.17, 1), 5.54)
    paste(foley, click(.18, 1.25), 22.92)
    paste(foley, click(.12, .45), 23.07)
    for start, duration, gain in ((11.4, 2.4, .012), (13.8, .9, .01), (14.65, 1.05, .009)):
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
        main = score.copy()
        main *= np.minimum(np.arange(len(main))/sr/.65,1)[:,None]
        main *= np.clip((len(main)/sr-np.arange(len(main))/sr)/1.0,0,1)[:,None]
        paste(music, main, 6.1, .82)
        # Extend the resolving tail into the brand hold with filtered reverb taps.
        tail = score[-int(2*sr):].copy()
        for delay, gain in ((21.1,.16),(22.2,.11),(23.3,.075),(24.4,.04)):
            paste(music, tail, delay, gain)
        score_kind = "MiniMax-H3 generated instrumental, edited and mixed locally"
    else:
        raise RuntimeError("Generated score not yet available")

    # Musical ducking makes space for the cap, without a broadband whoosh on each cut.
    duck = np.ones(n)
    for center, width, depth in ((5.56,.20,.60),(22.95,.22,.32)):
        duck *= 1 - depth * np.exp(-.5*((t-center)/width)**2)
    music *= duck[:,None]
    end_env = np.clip((27-t)/.8,0,1)
    mixed = (music + bed + foley) * end_env[:,None]
    # Endpoints are tapered to avoid an audible digital cut.
    mixed *= np.minimum(t/.025,1)[:,None]
    sf.write(WORK / "mix-premaster.wav", mixed, sr, subtype="PCM_24")
    sf.write(WORK / "music-stem.wav", music + bed, sr, subtype="PCM_24")
    sf.write(WORK / "foley-stem.wav", foley, sr, subtype="PCM_24")
    (WORK / "audio-origin.json").write_text(json.dumps({"score":score_kind,"effects":"Locally synthesized click, cloth and atmospheric textures","duration":27,"sample_rate":sr},indent=2), encoding="utf-8")
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
    run([FFMPEG,"-y","-hide_banner","-loglevel","error","-i",str(WORK / "picture-locked.mp4"),"-i",str(WORK / "mix-master.wav"),"-map","0:v:0","-map","1:a:0","-c:v","copy","-c:a","aac","-b:a","320k","-ar","48000","-t","27","-metadata","title=NOCTELLE — Wear the Night | Director Cut","-movflags","+faststart",str(OUT / "NOCTELLE_导演精剪_v2_27秒.mp4")],"mux-final.log")
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
