"""NOCTELLE 粗剪 v4：配乐 + 卡点（画面沿用 v3.2，推近用 B 档 1.22 倍）。
- 卡点：开灯的“咔”= 律动的第一拍。开灯之后的每一刀都吸附到最近的八分音符上（最多挪 0.16 秒，挪的是上一镜的出点；
  叠化取中点对拍）。硬切到合盖那一刀落在开灯后第 8 小节的强拍上，音乐就在这一下停住
- 配乐：现在用的是临时配乐（../music/temp_score.py 按卡点后的时间点现场合成），等正式配乐到了再换
- 音效：三次“咔哒”统一音色。合盖那一声当母版，降 3 个半音轻轻叠在开灯上，升 2 个半音叠在开盖上
- 混音：有了音乐以后，镜头原声整体让 3dB（三声“咔哒”所在的镜头除外），雨声底子也压低一点
"""
import json
import math
import pathlib
import subprocess

FF = "/Users/a1234/Claude/shorts/tools/bin/ffmpeg"
PY = "/Users/a1234/Claude/shorts/tools/.venv/bin/python"
MUSIC_DIR = pathlib.Path("../music")
FONT = "/System/Library/Fonts/Supplemental/Didot.ttc"
FPS = 24
OUT = "粗剪_全片_v4_配乐.mp4"
TMP = pathlib.Path("tmp_v4"); TMP.mkdir(exist_ok=True)
CUT = None  # 硬切

# (文件, 入点, 出点, 进入这段时的转场(类型, 时长) 或 CUT, 原声增益dB, J-cut 提前秒数, 额外处理)
EDL = [list(s) for s in [
    ("V01_窗景月牙_test", 0.4, 2.3, CUT, 0, 0, ""),
    ("V02_膏体剪影", 1.2, 2.2, CUT, -14, 0, ""),
    ("V03_05_睁眼拉远", 0.3, 6.3, ("fadeblack", 0.25), 0, 0, ""),     # 3 和 5 合成一镜：从眼睛一路拉到窗前侧脸
    ("V04_06_开灯捏起", 3.35, 5.35, CUT, 2, 0.45, "PUSH:0:1.22"),      # 开灯“咔”提前 0.45s（J-cut）；手指捏住就切；整镜缓推
    ("V07_开盖", 0.05, 2.1, CUT, -2, 0, ""),                         # 从盖子刚离开开始
    ("V08b_旋出_套餐测试", 0.8, 2.0, ("fade", 0.15), 0, 0, ""),
    ("V09_嘴唇", 0.7, 2.6, CUT, 0, 0, ""),
    ("V11_玻璃当镜子", 0.5, 2.3, CUT, 0, 0, ""),
    ("V12_推门", 0.3, 1.9, ("fade", 0.20), 0, 0, ""),
    ("V13_14_灯火上摇", 1.2, 4.9, CUT, -4, 0, ""),
    ("V15_16_丝绒成裙", 2.4, 5.95, ("fade", 0.45), -8, 0, ""),
    ("V16_17_后拉揭示", 0.05, 4.8, ("fade", 0.08), -4, 0, ""),        # 一路后拉到全身
    ("V22b_合盖近景", 0.3, 4.9, CUT, 4, 0, "TEXT:1.4"),               # 直接切到近景合盖“啪嗒”，最后一帧停 1.4s 出字
]]
# 三声“咔哒”在原片里的位置（镜头名, 原片秒数），用 5ms 窗找的峰
LAMP = ("V04_06_开灯捏起", 3.77)
UNCAP = ("V07_开盖", 0.34)
CLOSE = ("V22b_合盖近景", 3.78)
KEEP_LOUD = {LAMP[0], UNCAP[0], CLOSE[0]}  # 这几个镜头的原声不给音乐让路
DUCK_DB = -3
# 某个原片时间点之前的原声压低多少 dB。合盖镜头里拿盖子（1.45s）、套盖子（2.89s）的声音和“啪嗒”一样响，
# 音乐停住以后连响三下，“啪嗒”就不突出了；压低前两下，让它成为唯一的一声
AUDIO_GATE = {CLOSE[0]: (3.7, -12)}
MUSIC_DB = -6
GRADE = ("eq=contrast=1.06:saturation=0.9:gamma=0.97,"
         "colorbalance=rs=0.04:gs=-0.01:bs=-0.05:rm=0.02:bm=-0.03,"
         "vignette=PI/5,noise=alls=6:allf=t")


def ff(args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y"] + args, check=True)


def seg_len(seg):
    """一段实际会渲染出多少秒。trim 只留时间戳落在 [入点, 出点) 里的帧，fps 滤镜在结尾还会再丢一帧；
    不按这个算，开灯的位置会比名义时间线早 0.15 秒，卡点全偏。"""
    frames = math.ceil(seg[2] * FPS - 1e-6) - math.ceil(seg[1] * FPS - 1e-6) - 1
    if seg[6].startswith("TEXT:"):
        frames += math.ceil(float(seg[6].split(":")[1]) * FPS - 1e-6)
    return frames / FPS


def group_blocks():
    blocks = []
    for i, seg in enumerate(EDL):
        if i == 0:
            blocks.append({"tr": None, "segs": [i]})
        elif seg[3] is CUT:
            blocks[-1]["segs"].append(i)
        else:
            blocks.append({"tr": seg[3], "segs": [i]})
    return blocks


def timeline(blocks, lens=None):
    """每段在成片里的开始时间。lens 给的是块的实际长度（按帧数），不给就用名义长度。"""
    starts, total = [0.0] * len(EDL), 0.0
    for j, blk in enumerate(blocks):
        nominal = sum(seg_len(EDL[i]) for i in blk["segs"])
        scale = (lens[j] / nominal) if lens else 1.0
        bstart = 0.0 if j == 0 else total - blk["tr"][1]
        blk["start"] = bstart
        t = bstart
        for i in blk["segs"]:
            starts[i] = t
            t += seg_len(EDL[i]) * scale
        total = bstart + nominal * scale
    return starts, total


def idx(name):
    return next(i for i, s in enumerate(EDL) if s[0] == name)


def at(starts, point):
    """某个原片时间点在成片里的位置。"""
    i = idx(point[0])
    return starts[i] + point[1] - EDL[i][1]


def cut_time(i, starts):
    """第 i 段的入画时刻：硬切就是开始时间，叠化取中点。"""
    tr = EDL[i][3]
    return starts[i] + (tr[1] / 2 if tr else 0)


# ---- 第零步：卡点。网格从开灯那一下起算，开灯到最后一刀正好 8 小节 ----
starts, _ = timeline(group_blocks())
lamp = at(starts, LAMP)
last = idx(CLOSE[0])
BAR = (cut_time(last, starts) - lamp) / 8
EIGHTH = BAR / 8
print(f"网格: {60 / (BAR / 4):.2f} BPM, 开灯 {lamp:.2f}s")
for i in range(idx(UNCAP[0]), last + 1):
    starts, _ = timeline(group_blocks())
    t = cut_time(i, starts)
    step = BAR if i == last else EIGHTH                  # 最后一刀对小节线，其余对八分音符
    target = lamp + round((t - lamp) / step) * step
    delta = target - t
    EDL[i - 1][2] += delta                               # 挪上一镜的出点，后面整体跟着走
    print(f"  {EDL[i][0]:<20} {t:6.2f} -> {target:6.2f}  ({delta:+.2f}s，{EDL[i - 1][0]} 出点 {EDL[i - 1][2]:.2f})")


def seg_filter(idx_, seg):
    name, a, b, tr, gain, lead, extra = seg
    d = b - a
    v = f"[{idx_}:v]trim={a}:{b},setpts=PTS-STARTPTS"
    if extra.startswith("PUSH"):
        # 数码推近：先放大两倍再 zoompan，取整误差减半，画面不抖；右边缘锚定，口红往画面中间走
        # 缓推：前 25% 柔和起步，之后匀速，切的时候还在慢慢往前走
        _, ts, zend = extra.split(":")
        u, k = f"((it-{ts})/{d - float(ts)})", 0.25
        z = f"if(lt(it,{ts}),1,1+{float(zend) - 1}*if(lt({u},{k}),pow({u},2)/{2 * k},{u}-{k / 2})/{1 - k / 2})"
        v += f",scale=2688:1536:flags=lanczos,zoompan=z='{z}':x='iw-iw/zoom':y='(ih-ih/zoom)/2':d=1:s=1344x768:fps={FPS}"
    v += f",scale=1344:768,setsar=1,fps={FPS},format=yuv420p,{GRADE}"
    if extra.startswith("TEXT"):
        hold = float(extra.split(":")[1]) if ":" in extra else 0
        v += f",tpad=stop_mode=clone:stop_duration={hold}"
        d = d + hold
        f1 = f"alpha='if(lt(t,{d - 2.0}),0,min(1,(t-{d - 2.0})/0.6))'"
        f2 = f"alpha='if(lt(t,{d - 1.5}),0,min(1,(t-{d - 1.5})/0.6))'"
        v += (f",drawtext=fontfile='{FONT}':text='Wear the':fontsize=64:fontcolor=white:shadowcolor=black@0.6:shadowx=2:shadowy=2:x=110:y=(h-text_h)/2:{f1}"
              f",drawtext=fontfile='{FONT}':text='Night.':fontsize=64:fontcolor=0xB0283D:shadowcolor=black@0.6:shadowx=2:shadowy=2:x=412:y=(h-text_h)/2:{f2}")
    return v + ",format=yuv420p"


# ---- 第一步：按硬切分组，每组渲染成一个块文件 ----
blocks = group_blocks()
lens = []
for j, blk in enumerate(blocks):
    ins, fl = [], []
    for k, i in enumerate(blk["segs"]):
        ins += ["-i", f"{EDL[i][0]}.mp4"]
        fl.append(seg_filter(k, EDL[i]) + f"[s{k}]")
    n = len(blk["segs"])
    fl.append("".join(f"[s{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[out]")
    blk["file"] = str(TMP / f"block{j}.mp4")
    ff(ins + ["-filter_complex", ";".join(fl), "-map", "[out]", "-an", "-c:v", "libx264", "-crf", "12",
              "-preset", "fast", "-r", str(FPS), blk["file"]])
    # 按实际渲染出来的帧数算长度（每段裁切都会舍掉零点几帧，累积起来会让 xfade 够不着）
    log = subprocess.run([FF, "-hide_banner", "-i", blk["file"], "-f", "null", "-"], capture_output=True, text=True).stderr
    lens.append(int(log.rsplit("frame=", 1)[1].split()[0]) / FPS)
    predicted = sum(seg_len(EDL[i]) for i in blk["segs"])
    if abs(lens[-1] - predicted) > 0.5 / FPS:
        print(f"  注意：块 {j} 实际 {lens[-1] * FPS:.0f} 帧，预测 {predicted * FPS:.0f} 帧，卡点会偏")
starts, total = timeline(blocks, lens)

# ---- 临时配乐：按实际时间点合成 ----
anchors = {
    "glint": starts[idx("V02_膏体剪影")], "eyes": starts[idx("V03_05_睁眼拉远")],
    "lamp": at(starts, LAMP), "door": cut_time(idx("V12_推门"), starts),
    "lights": starts[idx("V13_14_灯火上摇")], "velvet": cut_time(idx("V15_16_丝绒成裙"), starts),
    "reveal": cut_time(idx("V16_17_后拉揭示"), starts), "cut": starts[last],
    "click": at(starts, CLOSE), "end": total,
}
(TMP / "anchors.json").write_text(json.dumps(anchors, indent=1))
music = MUSIC_DIR / "temp_v4.wav"
subprocess.run([PY, str(MUSIC_DIR / "temp_score.py"), str(music), str(TMP / "anchors.json")], check=True)

# ---- 第二步：块之间 xfade + 声音时间线 ----
ins, fl = [], []
for blk in blocks:
    ins += ["-i", blk["file"]]
nb = len(blocks)
prev = "0:v"
for j in range(1, nb):
    out = f"x{j}" if j < nb - 1 else "vout"
    tr = blocks[j]["tr"]
    fl.append(f"[{prev}][{j}:v]xfade=transition={tr[0]}:duration={tr[1]:.3f}:offset={blocks[j]['start']:.3f}[{out}]")
    prev = out
mix = []
for i, (name, a, b, tr, gain, lead, extra) in enumerate(EDL):
    ins += ["-i", f"{name}.mp4"]
    k = len(ins) // 2 - 1
    sa = max(0.0, a - lead)
    dur = b - sa
    delay = int(max(0.0, starts[i] - lead) * 1000)
    g = gain + (0 if name in KEEP_LOUD else DUCK_DB)
    gate = ""
    if name in AUDIO_GATE:
        until, db = AUDIO_GATE[name]
        lo, te = 10 ** (db / 20), until - sa
        gate = f"volume='min(1,max({lo:.3f},{lo:.3f}+(t-{te - 0.05:.3f})/0.05*{1 - lo:.3f}))':eval=frame,"   # 50ms 斜坡放开
    fl.append(f"[{k}:a]atrim={sa}:{b},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,{gate}"
              f"afade=t=in:d=0.08,afade=t=out:st={max(0, dur - 0.12):.3f}:d=0.12,volume={g}dB,"
              f"adelay={delay}|{delay}[a{i}]")
    mix.append(f"[a{i}]")
ins += ["-i", "V01_窗景月牙_test.mp4"]
k = len(ins) // 2 - 1
fl.append(f"[{k}:a]atrim=0.3:4.3,asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
          f"aloop=loop=-1:size={4 * 48000},atrim=0:{total:.3f},volume=3dB,afade=t=in:d=0.5,afade=t=out:st={total - 1.5:.3f}:d=1.5[bed]")
fl.append(f"anoisesrc=color=brown:amplitude=0.02:d={total:.3f},lowpass=f=300,aformat=channel_layouts=stereo,aresample=48000[room]")
mix += ["[bed]", "[room]"]
# 统一音色的“咔哒”：合盖那一声当母版（峰在采样里 0.02 秒处），变调后叠到开灯、开盖上
for tag, point, semis in (("lamp", LAMP, -3), ("uncap", UNCAP, 2)):
    ins += ["-i", f"{CLOSE[0]}.mp4"]
    k = len(ins) // 2 - 1
    r = 2 ** (semis / 12)
    delay = int((at(starts, point) - 0.02 / r) * 1000)
    fl.append(f"[{k}:a]atrim={CLOSE[1] - 0.02}:{CLOSE[1] + 0.18},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
              f"asetrate={int(48000 * r)},aresample=48000,afade=t=out:st=0.1:d=0.08,volume=-10dB,adelay={delay}|{delay}[c_{tag}]")
    mix.append(f"[c_{tag}]")
ins += ["-i", str(music)]
k = len(ins) // 2 - 1
fl.append(f"[{k}:a]aresample=48000,aformat=channel_layouts=stereo,volume={MUSIC_DB}dB[music]")
mix.append("[music]")
fl.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:dropout_transition=0,volume=2dB,alimiter=limit=0.75:attack=2:release=60:level=0[aout]")   # 留 2.5dB 给 AAC 编码的过冲；level=0 关掉自动拉回 0dBFS（默认开着，真峰值会到 +0.3）
ff(ins + ["-filter_complex", ";".join(fl), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
          "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
          "-movflags", "+faststart", OUT])
print(f"blocks {nb}, total {total:.2f}s")
print(json.dumps({k: round(v, 2) for k, v in anchors.items()}, ensure_ascii=False))
