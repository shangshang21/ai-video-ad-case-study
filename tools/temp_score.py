"""临时配乐（temp track）：按画面时间点直接“写”出来的极简暗调电子乐，用来先把卡点和混音流水线跑通。
等 Gemini / Lyria 的正式配乐到了就换掉。全部用 numpy 合成：加法合成锯齿波（随时间变化的低通）、毛毡钢琴、心跳低音、滴答、合成混响。

用法: python temp_score.py 输出.wav [时间点.json]
时间点（秒，成片时间）默认用下面 ANCHORS（v3.2 的时间线）；剪辑脚本卡点之后会把新的时间点写成 json 传进来。
"""
import json
import sys

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve, butter, sosfilt

SR = 48000
ANCHORS = {
    "glint": 1.86,     # 膏体金边一闪
    "eyes": 2.58,      # 黑场进眼睛
    "lamp": 8.92,      # 开灯“咔”：律动从这一下开始
    "door": 16.94,     # 推门
    "lights": 18.51,   # 灯火上升：弦乐开始涌
    "velvet": 21.96,   # 丝绒涌入（叠化中点）：高潮
    "reveal": 25.12,   # 后拉揭示
    "cut": 29.83,      # 硬切到合盖：音乐在这个强拍上停
    "click": 33.31,    # 合盖“啪嗒”：最后一个和弦从这里起
    "end": 35.79,
}
if len(sys.argv) > 2:
    ANCHORS.update(json.loads(open(sys.argv[2]).read()))
A = ANCHORS
BAR = (A["cut"] - A["lamp"]) / 8          # 开灯到硬切正好 8 小节（约 91.8 BPM）
BEAT = BAR / 4
N = int(A["end"] * SR) + SR * 4           # 多留 4 秒给混响尾巴，最后再裁
t_all = np.arange(N) / SR


def hz(note):
    names = {"C": 0, "C#": 1, "D": 2, "Eb": 3, "E": 4, "F": 5, "F#": 6, "G": 7, "Ab": 8, "A": 9, "Bb": 10, "B": 11}
    return 440 * 2 ** ((names[note[:-1]] + 12 * (int(note[-1]) + 1) - 69) / 12)


def env_adsr(n, a, d, s, r_start, r):
    """n 个采样的包络：attack a 秒、decay d 秒到 s、从 r_start 秒开始 release r 秒。"""
    t = np.arange(n) / SR
    e = np.where(t < a, t / max(a, 1e-4), s + (1 - s) * np.exp(-(t - a) / max(d, 1e-4)))
    rel = np.clip(1 - (t - r_start) / max(r, 1e-4), 0, 1)
    return e * np.where(t > r_start, rel, 1)


def saw(f, t, cutoff, detune=0.0, fm=None):
    """带随时间变化低通的锯齿波（加法合成，不混叠）。cutoff 可以是数组；fm 是频率倍数曲线（揉弦用）。"""
    out = np.zeros_like(t)
    f = f * (1 + detune)
    phase = 2 * np.pi * f * (t if fm is None else t[0] + np.cumsum(fm) / SR)
    for k in range(1, int(9000 / f) + 1):
        w = 1 / (1 + (k * f / cutoff) ** 4)
        if np.max(w) < 1e-3:
            break
        out += w * np.sin(k * phase + k * 0.7) / k
    return out


def place(buf, sig, at):
    i = int(at * SR)
    j = min(len(buf), i + len(sig))
    if j > i:
        buf[i:j] += sig[: j - i]


def piano(note, dur=3.0, vel=1.0):
    """毛毡钢琴：几根略微失谐的谐波，高次谐波衰减更快，起音带一点闷的“噗”。"""
    f = hz(note)
    n = int(dur * SR)
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for k, amp in enumerate([1, 0.45, 0.22, 0.12, 0.06], start=1):
        fk = f * k * (1 + 0.0004 * k * k)
        sig += amp * np.sin(2 * np.pi * fk * t) * np.exp(-t * (1.2 + 1.8 * k))
    thump = np.random.default_rng(int(f)).standard_normal(n) * np.exp(-t * 90) * 0.08
    sig = sig + sosfilt(butter(2, 900, fs=SR, output="sos"), thump)
    return vel * sig * np.minimum(1, t / 0.006)


def stereo(m, pan=0.0):
    return np.stack([m * np.sqrt(0.5 * (1 - pan)), m * np.sqrt(0.5 * (1 + pan))], axis=1)


rng = np.random.default_rng(7)
dry = np.zeros((N, 2))
wet_send = np.zeros((N, 2))

# 1. 低频长音（全程到硬切）：D2 + A2，开头从无到有
seg = np.clip((A["cut"] - t_all) / 0.015, 0, 1)        # 硬切处 15ms 收掉，避免数字爆音
cut_drone = 220 + 260 * np.clip((t_all - A["lamp"]) / (A["velvet"] - A["lamp"]), 0, 1)
drone = sum(saw(hz(n), t_all, cut_drone, d) for n in ["D2", "A2"] for d in (-0.0015, 0.0015))
drone_env = np.clip(t_all / 3.0, 0, 1) * (0.3 + 0.7 * np.clip((t_all - A["lamp"]) / 6, 0, 1))   # 开灯前压低，前奏要“几乎无声”
drone_env *= seg
dry += stereo(drone * drone_env * 0.05)
wet_send += stereo(drone * drone_env * 0.03)

# 2. 雨一样的空气声：粉红噪声过带通，很轻
noise = rng.standard_normal(N)
air = sosfilt(butter(2, [1500, 7000], btype="band", fs=SR, output="sos"), noise)
air_env = np.clip(t_all / 2, 0, 1) * np.clip(1 - (t_all - A["cut"]) / 0.3, 0, 1)
dry += np.stack([air, np.roll(air, 4000)], axis=1) * air_env[:, None] * 0.004

# 3. 毛毡钢琴：金边一闪落一个单音；开灯后的第 2、4、6 小节各弹一次三音动机 A–F–D
place(wet_send, stereo(piano("D5", 4, 0.10), 0.2), A["glint"])
place(dry, stereo(piano("D5", 4, 0.06), 0.2), A["glint"])
for bar in (1, 3, 5):
    t0 = A["lamp"] + bar * BAR
    for off, note in ((0, "A4"), (1.5, "F4"), (3, "D4")):
        p = piano(note, 3.5, 0.11)
        place(dry, stereo(p, -0.15), t0 + off * BEAT)
        place(wet_send, stereo(p * 0.9, -0.15), t0 + off * BEAT)

# 4. 心跳低音：开灯那一下开始，每拍一下（2、4 拍后面带一个轻的回跳），到硬切为止
def thump(vel):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 48 + 50 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) + 0.25 * np.sin(2 * ph)          # 二次谐波让手机喇叭也听得到
    return vel * body * np.minimum(1, t / 0.004) * np.exp(-t / 0.16)

k = 0
while A["lamp"] + k * BEAT < A["cut"] - 0.01:
    t0 = A["lamp"] + k * BEAT
    grow = 0.55 + 0.45 * min(1, (t0 - A["lamp"]) / (A["velvet"] - A["lamp"]))
    place(dry, stereo(thump(0.32 * grow)), t0)
    if k % 2 == 1:
        place(dry, stereo(thump(0.12 * grow)), t0 + 0.17)
    k += 1

# 5. 滴答：第 2 小节起，八分音符，正拍重、反拍轻，左右轻轻交替
def tick(vel):
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    s = rng.standard_normal(n) * np.exp(-t / 0.0025)
    return vel * sosfilt(butter(2, [5000, 11000], btype="band", fs=SR, output="sos"), s)

k = 0
while A["lamp"] + BAR + k * BEAT / 2 < A["cut"] - 0.01:
    t0 = A["lamp"] + BAR + k * BEAT / 2
    s = tick(0.10 if k % 2 == 0 else 0.055)
    place(dry, stereo(s, 0.35 if k % 2 else -0.35), t0)
    place(wet_send, stereo(s * 0.5), t0)
    k += 1

# 6. 合成器铺底：开灯后每两小节换一个和弦 Dm – Bb – Gm – A，低通从 500Hz 慢慢开到 2600Hz
CHORDS = [["D3", "F3", "A3"], ["Bb2", "D3", "F3"], ["G2", "Bb2", "D3"], ["A2", "C#3", "E3"]]
for i in range(4):
    t0 = A["lamp"] + i * 2 * BAR
    dur = 2 * BAR + (0.15 if i < 3 else 0.0)
    n = int(dur * SR)
    tt = np.arange(n) / SR + t0
    cut = 500 + 2100 * np.clip((tt - A["lamp"]) / (A["velvet"] - A["lamp"]), 0, 1) ** 1.5
    pad = sum(saw(hz(note), tt, cut, d) for note in CHORDS[i] for d in (-0.003, 0.003))
    e = env_adsr(n, 0.6 if i == 0 else 0.15, 1.0, 1.0, dur - 0.15, 0.15)
    level = 0.022 + 0.018 * min(1, i / 2)
    place(dry, np.stack([pad * e * level, np.roll(pad, 300) * e * level], axis=1), t0)
    place(wet_send, stereo(pad * e * level * 1.2), t0)

# 7. 弦乐涌起：灯火上升开始，丝绒涌入到达高潮，一直撑到硬切
n = int((A["cut"] - A["lights"]) * SR)
tt = np.arange(n) / SR + A["lights"]
vib = 1 + 0.004 * np.sin(2 * np.pi * 5.2 * tt)
strings = np.zeros(n)
for i in range(4):
    a0 = A["lamp"] + i * 2 * BAR
    a1 = a0 + 2 * BAR
    mask = np.clip((tt - a0) / 0.08, 0, 1) * np.clip((a1 + 0.08 - tt) / 0.08, 0, 1)   # 换和弦时 80ms 交叉淡化，不爆音
    if not mask.any():
        continue
    top = [hz(x) * 2 for x in CHORDS[i]]
    for f in top:
        for d in (-0.004, 0.0, 0.004):
            strings += mask * saw(f, tt, 2200, d, fm=vib) * 0.5
swell = np.clip((tt - A["lights"]) / (A["velvet"] - A["lights"]), 0, 1) ** 2
swell = np.where(tt > A["reveal"], 1 + 0.25 * np.clip((tt - A["reveal"]) / 2, 0, 1), swell)
strings *= swell * 0.012
place(dry, np.stack([strings, np.roll(strings, 500)], axis=1), A["lights"])
place(wet_send, stereo(strings * 1.6), A["lights"])

# 8. 开灯前的“吸一口气”：一段反向噪声慢慢涌到开灯那一下
n = int(1.3 * SR)
t = np.arange(n) / SR
breath = sosfilt(butter(2, [800, 6000], btype="band", fs=SR, output="sos"), rng.standard_normal(n)) * (t / t[-1]) ** 3
place(dry, stereo(breath * 0.02), A["lamp"] - 1.3)
place(wet_send, stereo(breath * 0.03), A["lamp"] - 1.3)

# 9. 合盖之后最后一个和弦：低音 D 小调 + 钢琴，长长的混响，到片尾淡出
n = int((A["end"] - A["click"] + 3) * SR)
tt = np.arange(n) / SR
final = sum(saw(hz(note), tt, 900, d) for note in ["D2", "A2", "D3", "F3"] for d in (-0.002, 0.002))
final *= env_adsr(n, 0.08, 1.5, 0.6, A["end"] - A["click"] - 1.0, 1.0) * 0.035
place(dry, stereo(final), A["click"])
place(wet_send, stereo(final * 1.5), A["click"])
for note, v in (("D4", 0.12), ("A3", 0.09)):
    place(dry, stereo(piano(note, 3, v)), A["click"] + 0.02)
    place(wet_send, stereo(piano(note, 3, v)), A["click"] + 0.02)

# 混响：衰减的立体声噪声当冲激响应（RT60 约 2.8 秒），预延迟 20ms
ir_n = int(3.2 * SR)
ti = np.arange(ir_n) / SR
ir = rng.standard_normal((ir_n, 2)) * np.exp(-ti / (2.8 / 6.9))[:, None]
ir = sosfilt(butter(2, 5000, fs=SR, output="sos"), ir, axis=0)
ir = np.concatenate([np.zeros((int(0.02 * SR), 2)), ir])
ir /= np.sqrt((ir ** 2).sum(axis=0))
wet = np.stack([fftconvolve(wet_send[:, c], ir[:, c])[:N] for c in range(2)], axis=1)

mix = dry + wet * 0.55
mix = mix[: int(A["end"] * SR)]
fade = np.clip((A["end"] - np.arange(len(mix)) / SR) / 0.6, 0, 1)
mix *= fade[:, None]
mix = np.tanh(mix * 1.6) / 1.6                     # 软限幅
mix *= 0.89 / np.max(np.abs(mix))
sf.write(sys.argv[1], mix.astype(np.float32), SR)
print(f"BPM {60 / BEAT:.2f}, bar {BAR:.3f}s, {len(mix) / SR:.2f}s -> {sys.argv[1]}")
