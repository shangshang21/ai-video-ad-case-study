"""NOCTELLE 粗剪 v2：用“时间线”思路解决拼凑感。
- 画面：硬切的镜头先渲染成一个个“块”文件（时间码干净），再用 xfade 在块之间做叠化 / 黑场过渡
- 声音：每段原声单独淡入淡出、对齐响度，按时间线放置；J-cut（声音先进）用 lead 提前；底下铺连续的雨声 + 房间底噪
- 调色：所有镜头统一压一遍（微对比、降饱和、暗部偏暖、暗角、胶片颗粒）
"""
import pathlib
import subprocess

FF = "/Users/a1234/Claude/shorts/tools/bin/ffmpeg"
FONT = "/System/Library/Fonts/Supplemental/Didot.ttc"
FPS = 24
OUT = "粗剪_全片_v2.mp4"
TMP = pathlib.Path("tmp_v2"); TMP.mkdir(exist_ok=True)
CUT = None  # 硬切

# (文件, 入点, 出点, 进入这段时的转场(类型, 时长) 或 CUT, 原声增益dB, J-cut 提前秒数, 额外处理)
EDL = [
    ("V01_窗景月牙_test", 0.4, 2.3, CUT, 0, 0, ""),
    ("V02_膏体剪影", 1.2, 2.2, CUT, -14, 0, ""),
    ("V03_睁眼", 1.0, 4.1, ("fadeblack", 0.25), 0, 0, ""),           # 睁眼 + 转头整个做完
    ("V05_侧影望窗", 0.6, 2.6, ("fade", 0.30), 0, 0, "hflip"),        # 叠化接侧影（镜像，视线方向对上）
    ("V04_06_开灯捏起", 3.35, 6.3, CUT, 2, 0.45, ""),                 # 开灯“咔”在 3.75s；声音提前 0.45s（J-cut）
    ("V07_开盖", 0.3, 2.1, CUT, -2, 0, ""),
    ("V08b_旋出_套餐测试", 0.8, 2.0, ("fade", 0.15), 0, 0, ""),
    ("V09_嘴唇", 0.7, 2.6, CUT, 0, 0, ""),
    ("V11_玻璃当镜子", 0.5, 2.3, CUT, 0, 0, ""),
    ("V12_推门", 0.3, 1.9, ("fade", 0.20), 0, 0, ""),                # 她迈步之前切走
    ("V13_14_灯火上摇", 1.2, 4.9, CUT, -4, 0, ""),
    ("V15_16_丝绒成裙", 2.4, 5.95, ("fade", 0.45), -8, 0, ""),        # 丝绒天空叠化成丝绒涌入
    ("V16_17_后拉揭示", 0.05, 4.2, ("fade", 0.08), -4, 0, ""),        # 首尾同一张图，接起来像一镜到底
    ("V18_回看", 0.2, 2.0, CUT, 0, 0, ""),
    ("V02_膏体剪影", 2.8, 3.2, CUT, -18, 0, ""),
    ("V09_嘴唇", 3.6, 4.0, CUT, -6, 0, ""),
    ("V15_16_丝绒成裙", 5.5, 5.9, CUT, -14, 0, ""),
    ("V22_定版", 1.3, 5.0, ("fadeblack", 0.35), 0, 0, "TEXT"),
]
GRADE = ("eq=contrast=1.06:saturation=0.9:gamma=0.97,"
         "colorbalance=rs=0.04:gs=-0.01:bs=-0.05:rm=0.02:bm=-0.03,"
         "vignette=PI/5,noise=alls=6:allf=t")


def ff(args):
    subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y"] + args, check=True)


def seg_filter(idx, seg):
    name, a, b, tr, gain, lead, extra = seg
    d = b - a
    v = f"[{idx}:v]trim={a}:{b},setpts=PTS-STARTPTS"
    if extra == "hflip":
        v += ",crop=iw:ih*0.88,hflip"
    v += f",scale=1344:768,setsar=1,fps={FPS},format=yuv420p,{GRADE}"
    if extra == "TEXT":
        f1 = f"alpha='if(lt(t,{d - 2.3}),0,min(1,(t-{d - 2.3})/0.7))'"
        f2 = f"alpha='if(lt(t,{d - 1.8}),0,min(1,(t-{d - 1.8})/0.7))'"
        v += (f",drawtext=fontfile='{FONT}':text='Wear the':fontsize=64:fontcolor=white:shadowcolor=black@0.6:shadowx=2:shadowy=2:x=110:y=(h-text_h)/2:{f1}"
              f",drawtext=fontfile='{FONT}':text='Night.':fontsize=64:fontcolor=0xB0283D:shadowcolor=black@0.6:shadowx=2:shadowy=2:x=412:y=(h-text_h)/2:{f2}")
    return v + ",format=yuv420p"


# ---- 第一步：按硬切分组，每组渲染成一个块文件 ----
blocks = []
for i, seg in enumerate(EDL):
    if i == 0 or seg[3] is CUT:
        if i == 0:
            blocks.append({"tr": None, "segs": [i]})
        else:
            blocks[-1]["segs"].append(i)
    else:
        blocks.append({"tr": seg[3], "segs": [i]})
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
    frames = int(log.rsplit("frame=", 1)[1].split()[0])
    blk["len"] = frames / FPS
    blk["nominal"] = sum(EDL[i][2] - EDL[i][1] for i in blk["segs"])

# ---- 时间线：每段在成片里的开始时间 ----
starts, total = [0.0] * len(EDL), 0.0
for j, blk in enumerate(blocks):
    bstart = 0.0 if j == 0 else total - blk["tr"][1]
    blk["start"] = bstart
    scale = blk["len"] / blk["nominal"]
    t = bstart
    for i in blk["segs"]:
        starts[i] = t
        t += (EDL[i][2] - EDL[i][1]) * scale
    total = bstart + blk["len"]

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
    k = nb + i
    sa = max(0.0, a - lead)
    dur = b - sa
    delay = int(max(0.0, starts[i] - lead) * 1000)
    fl.append(f"[{k}:a]atrim={sa}:{b},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
              f"afade=t=in:d=0.08,afade=t=out:st={max(0, dur - 0.12):.3f}:d=0.12,volume={gain}dB,"
              f"adelay={delay}|{delay}[a{i}]")
    mix.append(f"[a{i}]")
ins += ["-i", "V01_窗景月牙_test.mp4"]
bed = nb + len(EDL)
fl.append(f"[{bed}:a]atrim=0.3:4.3,asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
          f"aloop=loop=-1:size={4 * 48000},atrim=0:{total:.3f},volume=6dB,afade=t=in:d=0.5,afade=t=out:st={total - 1.5:.3f}:d=1.5[bed]")
fl.append(f"anoisesrc=color=brown:amplitude=0.02:d={total:.3f},lowpass=f=300,aformat=channel_layouts=stereo,aresample=48000[room]")
mix += ["[bed]", "[room]"]
fl.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:dropout_transition=0,alimiter=limit=0.9[aout]")
ff(ins + ["-filter_complex", ";".join(fl), "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}",
          "-c:v", "libx264", "-crf", "19", "-preset", "medium", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
          "-movflags", "+faststart", OUT])
print(f"blocks {nb}, total {total:.1f}s")
