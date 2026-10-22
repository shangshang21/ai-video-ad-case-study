"""每条片子的动作曲线（相邻帧差）和音量曲线，用来挑剪辑点。"""
import subprocess, sys, numpy as np
FF = "/Users/a1234/Claude/shorts/tools/bin/ffmpeg"
for name in sys.argv[1:]:
    raw = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-i", f"{name}.mp4", "-vf", "scale=64:36,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, 36, 64).astype(float)
    diff = np.abs(np.diff(fr, axis=0)).mean(axis=(1, 2))
    aud = subprocess.run([FF, "-hide_banner", "-loglevel", "error", "-i", f"{name}.mp4", "-ac", "1", "-ar", "8000",
                          "-f", "s16le", "-"], capture_output=True).stdout
    a = np.frombuffer(aud, np.int16).astype(float) / 32768
    line = []
    for t in np.arange(0, len(diff) / 24, 0.25):
        i = int(t * 24); m = diff[i:i + 6].mean() if i < len(diff) else 0
        seg = a[int(t * 8000):int((t + 0.25) * 8000)]
        db = 20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-9) if len(seg) else -99
        line.append(f"{t:4.2f}:{m:4.1f}/{db:3.0f}")
    print(f"== {name} (motion/dB per 0.25s)")
    print("  ".join(line))
