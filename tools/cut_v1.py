"""NOCTELLE 粗剪 v1：按 docs/14 的顺序裁切、拼接，片尾加广告语。"""
import subprocess
FF = "/Users/a1234/Claude/shorts/tools/bin/ffmpeg"
FONT = "/System/Library/Fonts/Supplemental/Didot.ttc"
# (文件, 入点, 出点, 额外视频滤镜)
EDL = [
    ("V01_窗景月牙_test", 0.6, 2.2, ""),
    ("V02_膏体剪影", 1.5, 2.4, ""),
    ("V03_睁眼", 1.1, 3.3, ""),
    ("V05_侧影望窗", 0.3, 2.1, "hflip"),          # 镜像：让她朝向和上一镜视线一致（这条自带上下黑边，下面裁掉）
    ("V04_06_开灯捏起", 2.8, 6.3, ""),
    ("V07_开盖", 0.2, 2.0, ""),
    ("V08b_旋出_套餐测试", 0.8, 2.0, ""),
    ("V09_嘴唇", 0.6, 2.4, ""),
    ("V11_玻璃当镜子", 0.6, 2.2, ""),
    ("V12_推门", 0.5, 2.3, ""),                    # 她走出门之前就切走
    ("V13_14_灯火上摇", 2.0, 5.0, ""),
    ("V15_16_丝绒成裙", 2.0, 6.0, ""),
    ("V16_17_后拉揭示", 3.3, 6.3, ""),
    ("V18_回看", 0.2, 2.0, ""),
    ("V02_膏体剪影", 2.8, 3.2, ""),                # 快闪 ×3
    ("V09_嘴唇", 3.6, 4.0, ""),
    ("V15_16_丝绒成裙", 5.5, 5.9, ""),
    ("V22_定版", 1.5, 5.0, "TEXT"),
]
inputs, chains, labels = [], [], []
for i, (name, a, b, extra) in enumerate(EDL):
    inputs += ["-i", f"{name}.mp4"]
    v = f"[{i}:v]trim={a}:{b},setpts=PTS-STARTPTS,scale=1344:768,fps=24,format=yuv420p"
    if extra == "hflip":
        v = v.replace("setpts=PTS-STARTPTS,", "setpts=PTS-STARTPTS,crop=iw:ih*0.88,") + ",hflip"
    if extra == "TEXT":
        d = b - a
        fade = f"alpha='if(lt(t,{d-2.2}),0,min(1,(t-{d-2.2})/0.6))'"
        fade2 = f"alpha='if(lt(t,{d-1.7}),0,min(1,(t-{d-1.7})/0.6))'"
        v += (f",drawtext=fontfile='{FONT}':text='Wear the':fontsize=64:fontcolor=white:shadowcolor=black@0.6:shadowx=2:shadowy=2:x=110:y=(h-text_h)/2:{fade}"
              f",drawtext=fontfile='{FONT}':text='Night.':fontsize=64:fontcolor=0xB0283D:shadowcolor=black@0.6:shadowx=2:shadowy=2:x=110+302:y=(h-text_h)/2:{fade2}")
    chains.append(v + f"[v{i}]")
    chains.append(f"[{i}:a]atrim={a}:{b},asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo[a{i}]")
    labels.append(f"[v{i}][a{i}]")
chains.append("".join(labels) + f"concat=n={len(EDL)}:v=1:a=1[v][a]")
subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-y"] + inputs +
               ["-filter_complex", ";".join(chains), "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "19",
                "-preset", "medium", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", "粗剪_全片_v1.mp4"], check=True)
print("total", round(sum(b - a for _, a, b, _ in EDL), 1), "s")
