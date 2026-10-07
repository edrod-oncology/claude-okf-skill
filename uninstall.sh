#!/usr/bin/env bash
# Remove the OKF skill and hook from ~/.claude (or $CLAUDE_HOME).
set -euo pipefail
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SKILL_DEST="$CLAUDE_HOME/skills/okf"
HOOK_DEST="$CLAUDE_HOME/hooks/okf-commit-gate.py"
SETTINGS="$CLAUDE_HOME/settings.json"

rm -rf "$SKILL_DEST" && echo "removed $SKILL_DEST"
rm -f "$HOOK_DEST" && echo "removed $HOOK_DEST"

if [ -f "$SETTINGS" ]; then
  cp "$SETTINGS" "$SETTINGS.pre-okf-uninstall-$(date +%Y%m%d-%H%M%S)"
  HOOK_DEST="$HOOK_DEST" SETTINGS="$SETTINGS" python3 - <<'PY'
import json, os
hook, path = os.environ["HOOK_DEST"], os.environ["SETTINGS"]
s = json.load(open(path))
groups = s.get("hooks", {}).get("PreToolUse", [])
cmd = f"python3 {hook}"
for g in groups:
    g["hooks"] = [h for h in g.get("hooks", []) if h.get("command") != cmd]
s.get("hooks", {})["PreToolUse"] = [g for g in groups if g.get("hooks")]
if not s.get("hooks", {}).get("PreToolUse"):
    s.get("hooks", {}).pop("PreToolUse", None)
json.dump(s, open(path, "w"), indent=2); open(path, "a").write("\n")
print(f"hook entry removed from {path}")
PY
fi
echo "Project okf/ bundles are untouched; they are plain markdown and belong to each repo."
