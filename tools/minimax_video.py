"""调用 MiniMax H3 视频生成 API（v2）：提交任务 → 轮询 → 下载 → 记账。key 从 ~/.config/minimax/key 读取。

用法:
  .venv/bin/python minimax_video.py 提示词.txt 输出.mp4 [--first 首帧图] [--last 尾帧图] [--ref 参考图 ...]
         [--model MiniMax-H3] [--resolution 768P] [--duration 6] [--ratio 16:9]
首尾帧和参考图不能混用（官方互斥规则）。
"""
import argparse
import base64
import json
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

HOST = "https://api.minimax.cn"
PRICE = {"768P": 0.5, "2K": 0.8, "480P": 0.33}  # 元/秒，官方刊例价（2026-10-22 查）
LEDGER = pathlib.Path(__file__).parent / "minimax_ledger.jsonl"

ap = argparse.ArgumentParser()
ap.add_argument("prompt")
ap.add_argument("out")
ap.add_argument("--first")
ap.add_argument("--last")
ap.add_argument("--ref", action="append", default=[])
ap.add_argument("--model", default="MiniMax-H3")
ap.add_argument("--resolution", default="768P")
ap.add_argument("--duration", type=int, default=6)
ap.add_argument("--ratio")
ap.add_argument("--key", default="key", help="~/.config/minimax/ 下的密钥文件名（key=按量，key_plan=套餐）")
a = ap.parse_args()
if (a.first or a.last) and a.ref:
    sys.exit("首尾帧和参考图不能混用")

key = (pathlib.Path.home() / ".config/minimax" / a.key).read_text().strip()


def data_url(path):
    """转成 JPEG 再 base64，体积小很多。"""
    tmp = pathlib.Path(tempfile.mkdtemp()) / "img.jpg"
    subprocess.run(["sips", "-s", "format", "jpeg", "-s", "formatOptions", "90", path, "--out", str(tmp)],
                   check=True, capture_output=True)
    return "data:image/jpeg;base64," + base64.b64encode(tmp.read_bytes()).decode()


def call(method, path, body=None):
    req = urllib.request.Request(HOST + path, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                                 data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"HTTP {e.code}: {e.read().decode()[:600]}")


content = [{"type": "text", "text": pathlib.Path(a.prompt).read_text().strip()}]
if a.first:
    content.append({"type": "image_url", "image_url": {"url": data_url(a.first)}, "role": "first_frame"})
if a.last:
    content.append({"type": "image_url", "image_url": {"url": data_url(a.last)}, "role": "last_frame"})
for r in a.ref:
    content.append({"type": "image_url", "image_url": {"url": data_url(r)}, "role": "reference_image"})

body = {"model": a.model, "content": content, "resolution": a.resolution, "duration": a.duration}
if a.ratio:
    body["ratio"] = a.ratio
created = call("POST", "/v2/video_generation", body)
task_id = created.get("task_id")
if not task_id:
    sys.exit(f"创建失败: {created}")
print(f"task {task_id} 已提交，等待生成…", flush=True)

t0 = time.time()
while True:
    time.sleep(10)
    task = call("GET", f"/v2/query/video_generation/{task_id}")["task"]
    if task["status"] in ("succeeded", "failed", "cancelled"):
        break
    if time.time() - t0 > 1800:
        sys.exit(f"超时，task {task_id} 状态 {task['status']}，稍后可再查")

usage = task.get("usage", {})
cost = usage.get("output_seconds", 0) * PRICE.get(a.resolution, 0.5)
with LEDGER.open("a") as f:
    f.write(json.dumps({"time": time.strftime("%F %T"), "task_id": task_id, "out": a.out, "status": task["status"],
                        "model": a.model, "resolution": a.resolution, "duration": a.duration,
                        "usage": usage, "est_cost_yuan": cost, "error": task.get("error")}, ensure_ascii=False) + "\n")
if task["status"] != "succeeded":
    sys.exit(f"任务 {task['status']}: {task.get('error')}")
urllib.request.urlretrieve(task["content"]["url"], a.out)
print(f"OK {a.out}  {usage.get('output_seconds')}s  约 ¥{cost:.2f}  用时 {time.time() - t0:.0f}s")
