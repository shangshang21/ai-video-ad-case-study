"""调用 MiniMax 音乐生成 API（纯音乐）：提交 → 拿到 hex 音频 → 存 mp3 → 记账。key 从 ~/.config/minimax/ 读取。

用法:
  .venv/bin/python minimax_music.py 提示词.txt 输出.mp3 [--model music-3.0] [--key key]
"""
import argparse
import json
import pathlib
import sys
import time
import urllib.request

HOST = "https://api.minimax.cn"
PRICE_USD = 0.15  # 每首（最长 5 分钟），官方按量价（2026-10-22 查）
LEDGER = pathlib.Path(__file__).parent / "minimax_ledger.jsonl"

ap = argparse.ArgumentParser()
ap.add_argument("prompt")
ap.add_argument("out")
ap.add_argument("--model", default="music-3.0")
ap.add_argument("--key", default="key", help="~/.config/minimax/ 下的密钥文件名（key=按量，key_plan=套餐）")
a = ap.parse_args()

key = (pathlib.Path.home() / ".config/minimax" / a.key).read_text().strip()
body = {"model": a.model, "prompt": pathlib.Path(a.prompt).read_text().strip(), "is_instrumental": True,
        "output_format": "hex", "audio_setting": {"sample_rate": 44100, "bitrate": 256000, "format": "mp3"}}
req = urllib.request.Request(HOST + "/v1/music_generation", method="POST", data=json.dumps(body).encode(),
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=600) as r:
        resp = json.loads(r.read())
except urllib.error.HTTPError as e:
    sys.exit(f"HTTP {e.code}: {e.read().decode()[:600]}")

base = resp.get("base_resp", {})
audio = (resp.get("data") or {}).get("audio")
with LEDGER.open("a") as f:
    f.write(json.dumps({"time": time.strftime("%F %T"), "kind": "music", "out": a.out, "model": a.model,
                        "status_code": base.get("status_code"), "status_msg": base.get("status_msg"),
                        "extra_info": resp.get("extra_info"), "est_cost_usd": PRICE_USD if audio else 0},
                       ensure_ascii=False) + "\n")
if base.get("status_code") != 0 or not audio:
    sys.exit(f"失败: {base}")
pathlib.Path(a.out).write_bytes(bytes.fromhex(audio))
print(f"OK {a.out}  {resp.get('extra_info')}  约 ${PRICE_USD}  用时 {time.time() - t0:.0f}s")
