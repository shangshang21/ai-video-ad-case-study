"""用 OpenAI 图片 API 出图（默认 gpt-image-2.5-sunburst），可以带参考图。key 从 ~/.config/openai/key 读取。

用法: .venv/bin/python sunburst.py <提示词.txt> <输出.png> [--ref 图.png ...] [--model M] [--quality high] [--size 1536x1024]
"""
import argparse
import base64
import json
import pathlib
import subprocess

ap = argparse.ArgumentParser()
ap.add_argument("prompt")
ap.add_argument("out")
ap.add_argument("--ref", action="append", default=[])
ap.add_argument("--model", default="gpt-image-2.5-sunburst")
ap.add_argument("--quality", default="high")
ap.add_argument("--size", default="1536x1024")
a = ap.parse_args()

key = (pathlib.Path.home() / ".config/openai/key").read_text().strip()
prompt = pathlib.Path(a.prompt).read_text().strip()
common = ["curl", "-s", "--max-time", "600", "-H", f"Authorization: Bearer {key}"]
if a.ref:
    cmd = common + ["https://api.openai.com/v1/images/edits",
                    "-F", f"model={a.model}", "-F", f"prompt={prompt}", "-F", f"quality={a.quality}",
                    "-F", f"size={a.size}"] + [x for r in a.ref for x in ("-F", f"image[]=@{r}")]
else:
    body = {"model": a.model, "prompt": prompt, "quality": a.quality, "size": a.size}
    cmd = common + ["https://api.openai.com/v1/images/generations", "-H", "Content-Type: application/json",
                    "-d", json.dumps(body)]

d = json.loads(subprocess.run(cmd, capture_output=True, text=True).stdout)
if "error" in d:
    raise SystemExit(f"ERR {d['error'].get('code')}: {d['error']['message']}")
pathlib.Path(a.out).write_bytes(base64.b64decode(d["data"][0]["b64_json"]))
u = d.get("usage", {})
it = u.get("input_tokens_details", {})
cost = it.get("text_tokens", 0) * 5e-6 + it.get("image_tokens", 0) * 8e-6 + u.get("output_tokens", 0) * 30e-6
print(f"OK {a.out}  in={u.get('input_tokens')} out={u.get('output_tokens')}  ≈${cost:.3f}")
