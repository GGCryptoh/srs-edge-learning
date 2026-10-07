#!/usr/bin/env bash
# SRS Edge Learning — installer for macOS / Linux.
#   curl -fsSL https://raw.githubusercontent.com/GGCryptoh/srs-edge-learning/main/install.sh | bash
# Installs the skill into ~/.claude/skills/srs-edge-learning (Claude Code) and, if those folders exist, ~/.codex/skills and ~/.copilot/skills.
# Override the target with SKILLS_DIR=/path. Re-running updates in place.
set -euo pipefail
NAME="srs-edge-learning"; URL="https://github.com/GGCryptoh/srs-edge-learning/releases/latest/download/srs-edge-learning.zip"; DEST="${SKILLS_DIR:-$HOME/.claude/skills}"
command -v python3 >/dev/null 2>&1 || { echo "python3 is required (macOS: xcode-select --install, or brew install python)"; exit 1; }
command -v unzip  >/dev/null 2>&1 || { echo "unzip is required"; exit 1; }
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
echo "Downloading $URL"
curl -fsSL "$URL" -o "$tmp/skill.zip"
mkdir -p "$DEST"; rm -rf "$DEST/$NAME"; unzip -q "$tmp/skill.zip" -d "$DEST"
echo "Installed → $DEST/$NAME"
for d in "$HOME/.codex/skills" "$HOME/.copilot/skills"; do
  if [ -d "$d" ] && [ "$d" != "$DEST" ]; then rm -rf "$d/$NAME"; cp -R "$DEST/$NAME" "$d/"; echo "Also installed → $d/$NAME"; fi
done
python3 "$DEST/$NAME/scripts/learn.py" setup >/dev/null 2>&1 || true
echo
echo "Done. Open your agent (Claude Code, Codex, Copilot CLI) in a new session and type:"
echo "  /srs-edge-learning <the thing you want to get smart at>"
