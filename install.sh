#!/usr/bin/env bash
# Install the OKF skill and the commit gate hook into ~/.claude (or $CLAUDE_HOME).
# Usage: ./install.sh [--no-hook] [--dry-run]
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude}"
SKILL_DEST="$CLAUDE_HOME/skills/okf"
HOOK_DEST="$CLAUDE_HOME/hooks/okf-commit-gate.py"
HOOK=1; DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --no-hook) HOOK=0; shift;;
    --dry-run) DRY=1; shift;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

for tool in python3 bash git; do
  command -v "$tool" >/dev/null || { echo "missing dependency: $tool" >&2; exit 1; }
done
python3 - <<'PY' || { echo "python3 >= 3.9 is required" >&2; exit 1; }
import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)
PY
python3 -c "import yaml" 2>/dev/null || \
  echo "note: PyYAML not found. The validator still runs, with a reduced frontmatter parser. 'pip install pyyaml' for full checks."

if [ "$DRY" -eq 1 ]; then
  echo "dry run: would copy skills/okf/ to $SKILL_DEST"
  [ "$HOOK" -eq 1 ] && echo "dry run: would copy hooks/okf-commit-gate.py to $HOOK_DEST and register a PreToolUse(Bash) hook in $CLAUDE_HOME/settings.json"
  exit 0
fi

mkdir -p "$SKILL_DEST"
for f in SKILL.md okf-spec-reference.md scaffold_okf.sh validate_okf.py migrate_okf.py; do
  cp "$HERE/skills/okf/$f" "$SKILL_DEST/$f"
done
chmod +x "$SKILL_DEST/scaffold_okf.sh" "$SKILL_DEST/validate_okf.py" "$SKILL_DEST/migrate_okf.py"
echo "skill installed to $SKILL_DEST"

if [ "$HOOK" -eq 1 ]; then
  mkdir -p "$CLAUDE_HOME/hooks"
  cp "$HERE/hooks/okf-commit-gate.py" "$HOOK_DEST"
  chmod +x "$HOOK_DEST"

  SETTINGS="$CLAUDE_HOME/settings.json"
  [ -f "$SETTINGS" ] || echo '{}' > "$SETTINGS"
  cp "$SETTINGS" "$SETTINGS.pre-okf-$(date +%Y%m%d-%H%M%S)"
  HOOK_DEST="$HOOK_DEST" SETTINGS="$SETTINGS" python3 - <<'PY'
import json, os
hook, path = os.environ["HOOK_DEST"], os.environ["SETTINGS"]
s = json.load(open(path))
hooks = s.setdefault("hooks", {})
groups = hooks.setdefault("PreToolUse", [])
cmd = f"python3 {hook}"
if any(cmd == h.get("command") for g in groups for h in g.get("hooks", [])):
    print("hook already registered; settings unchanged")
else:
    groups.append({"matcher": "Bash", "hooks": [{"type": "command", "command": cmd,
                   "timeout": 30, "statusMessage": "OKF commit gate"}]})
    json.dump(s, open(path, "w"), indent=2); open(path, "a").write("\n")
    print(f"hook registered in {path}")
PY
  echo "Open /hooks in a running Claude Code session (or restart) to load the hook."
fi

echo
echo "Try it: ask Claude to 'organize this project's knowledge in OKF', or run"
echo "  $SKILL_DEST/scaffold_okf.sh /path/to/project"
echo "  python3 $SKILL_DEST/validate_okf.py /path/to/project/okf"
