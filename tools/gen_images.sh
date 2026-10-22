#!/bin/bash
# 依次调用 GPT 生图（一次只跑一个任务）。用法: gen_images.sh <输出目录> "<名字>|<参考图或->" ...
# 提示词从 <输出目录>/prompts/<名字>.txt 读取，输出 <输出目录>/<名字>.png
X=/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex
OUT=$1; shift
for spec in "$@"; do
  name=${spec%%|*}; ref=${spec#*|}
  args=(exec --skip-git-repo-check -C "$OUT" --ephemeral)
  [ "$ref" != "-" ] && args+=(-i "$OUT/$ref.png")
  { printf '$imagegen '; cat "$OUT/prompts/$name.txt"; printf '\nSave the final image as %s and tell me the exact path.\n' "$OUT/$name.png"; } | "$X" "${args[@]}" > "$OUT/prompts/$name.log" 2>&1
  [ -f "$OUT/$name.png" ] && echo "OK   $name" || echo "FAIL $name (see prompts/$name.log)"
done
