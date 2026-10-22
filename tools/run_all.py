"""按 manifest.json 并行（3 路）提交 H3 出片；已存在的成片跳过。用法: python3 run_all.py [名字过滤...]"""
import json
import pathlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).parent
TOOLS = pathlib.Path("/Users/a1234/Claude/shorts/tools")
SEARCH = [HERE.parent / "v3" / "twostep", HERE.parent / "v3"]


def img(name):
    for d in SEARCH:
        p = d / f"{name}.png"
        if p.exists():
            return str(p)
    raise FileNotFoundError(name)


def run(r):
    out = HERE / f"{r['name']}.mp4"
    if out.exists():
        return f"skip {r['name']}"
    cmd = [str(TOOLS / ".venv/bin/python"), str(TOOLS / "minimax_video.py"), str(HERE / "prompts" / f"{r['name']}.txt"),
           str(out), "--first", img(r["first"]), "--duration", str(r["duration"]), "--resolution", "768P"]
    if r["last"]:
        cmd += ["--last", img(r["last"])]
    log = HERE / "logs" / f"{r['name']}.log"
    with log.open("w") as f:
        subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)
    return log.read_text().strip().splitlines()[-1] if log.read_text().strip() else f"{r['name']}: no output"


runs = json.loads((HERE / "manifest.json").read_text())
if len(sys.argv) > 1:
    runs = [r for r in runs if any(k in r["name"] for k in sys.argv[1:])]
(HERE / "logs").mkdir(exist_ok=True)
with ThreadPoolExecutor(3) as ex:
    for line in ex.map(run, runs):
        print(line, flush=True)
