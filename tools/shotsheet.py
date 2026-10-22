"""拆片工具：找出视频里的硬切点，每个镜头取中间一帧，拼成带编号、起始时间和时长的分镜联系表。

用法: .venv/bin/python shotsheet.py <视频> <输出目录> [场景阈值=0.3]
"""
import pathlib
import re
import subprocess
import sys

FFMPEG = str(pathlib.Path(__file__).parent / "bin" / "ffmpeg")
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"

video, out = sys.argv[1], pathlib.Path(sys.argv[2])
thresh = float(sys.argv[3]) if len(sys.argv) > 3 else 0.3
shots_dir = out / "shots"
shots_dir.mkdir(parents=True, exist_ok=True)
for f in shots_dir.glob("*.jpg"):
    f.unlink()

probe = subprocess.run([FFMPEG, "-hide_banner", "-i", video], capture_output=True, text=True).stderr
h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", probe).groups()
duration = int(h) * 3600 + int(m) * 60 + float(s)

log = subprocess.run(
    [FFMPEG, "-hide_banner", "-i", video, "-vf", f"select='gt(scene,{thresh})',showinfo", "-an", "-f", "null", "-"],
    capture_output=True, text=True).stderr
cuts = [float(t) for t in re.findall(r"pts_time:([\d.]+)", log)]
bounds = [0.0] + cuts + [duration]
shots = [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]

for i, (a, b) in enumerate(shots, 1):
    label = f"{i:02d}  {a:.1f}s  ({b - a:.1f}s)"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{(a + b) / 2:.3f}", "-i", video,
                    "-frames:v", "1", "-vf",
                    f"scale=384:-2,drawtext=fontfile='{FONT}':text='{label}':x=6:y=6:fontsize=18:"
                    "fontcolor=yellow:box=1:boxcolor=black@0.6",
                    str(shots_dir / f"{i:02d}.jpg")], check=True)

cols = 6
rows = -(-len(shots) // cols)
subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-pattern_type", "glob", "-i",
                str(shots_dir / "*.jpg"), "-vf", f"tile={cols}x{rows}:padding=4:color=black", "-frames:v", "1",
                str(out / "分镜联系表.jpg")], check=True)

lengths = [b - a for a, b in shots]
print(f"duration {duration:.2f}s, shots {len(shots)}, avg {sum(lengths) / len(lengths):.2f}s, "
      f"min {min(lengths):.2f}s, max {max(lengths):.2f}s")
for i, (a, b) in enumerate(shots, 1):
    print(f"{i:02d} {a:6.2f}-{b:6.2f} ({b - a:.2f}s)")
