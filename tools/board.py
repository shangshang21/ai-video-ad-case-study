"""审图拼板：把几张图缩到同一宽度，左上角标上名字，按网格拼成一张。

用法: .venv/bin/python board.py <输出.jpg> <列数> <图1>=<标签1> <图2>=<标签2> ...
"""
import pathlib
import subprocess
import sys

FFMPEG = str(pathlib.Path(__file__).parent / "bin" / "ffmpeg")
FONT = "/System/Library/Fonts/STHeiti Medium.ttc"
CELL_W = 768

out, cols, items = sys.argv[1], int(sys.argv[2]), sys.argv[3:]
paths, labels = zip(*(item.split("=", 1) for item in items))

# 用第一张图的比例定格子高度，空位补黑块
probe = subprocess.run([FFMPEG, "-hide_banner", "-i", paths[0]], capture_output=True, text=True).stderr
w, h = map(int, __import__("re").search(r", (\d+)x(\d+)", probe).groups())
cell_h = round(CELL_W * h / w / 2) * 2

chains, names = [], []
for i, label in enumerate(labels):
    label = label.replace("\\", "").replace("'", "").replace(":", "\\:").replace(",", "\\,")  # drawtext 的特殊字符
    chains.append(f"[{i}]scale={CELL_W}:{cell_h},drawtext=fontfile='{FONT}':text='{label}':x=12:y=12:"
                  f"fontsize=30:fontcolor=white:box=1:boxcolor=black@0.6[v{i}]")
    names.append(f"[v{i}]")
while len(names) % cols:
    k = len(names)
    chains.append(f"color=black:s={CELL_W}x{cell_h}:d=1[v{k}]")
    names.append(f"[v{k}]")
rows = [names[r:r + cols] for r in range(0, len(names), cols)]
row_names = []
for r, row in enumerate(rows):
    if len(row) == 1:
        chains.append(f"{row[0]}null[r{r}]")
    else:
        chains.append(f"{''.join(row)}hstack={len(row)}[r{r}]")
    row_names.append(f"[r{r}]")
chains.append(f"{''.join(row_names)}vstack={len(row_names)}" if len(row_names) > 1 else f"{row_names[0]}null")

cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"]
for p in paths:
    cmd += ["-i", p]
cmd += ["-filter_complex", ";".join(chains), "-frames:v", "1", out]
subprocess.run(cmd, check=True)
print("ok", out)
