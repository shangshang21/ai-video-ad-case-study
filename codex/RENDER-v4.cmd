@echo off
cd /d "%~dp0.."
uv run --python 3.12 --with-requirements codex/tools/requirements.txt codex/tools/render_v4.py all
pause
