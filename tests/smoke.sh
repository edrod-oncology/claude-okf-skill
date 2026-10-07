#!/usr/bin/env bash
# End-to-end smoke test. Needs bash, python3, git. Runs entirely in a temp dir.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SKILL="$HERE/skills/okf"
HOOK="$HERE/hooks/okf-commit-gate.py"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT
pass=0; fail=0
ok()   { pass=$((pass+1)); echo "  ok   $1"; }
bad()  { fail=$((fail+1)); echo "  FAIL $1"; }

# Run the hook the way Claude Code does: JSON on stdin, exit code is the verdict.
gate() {  # gate <cwd> <command>  -> prints exit code
  local cwd="$1" cmd="$2"
  python3 -c 'import json,sys; print(json.dumps({"tool_name":"Bash","tool_input":{"command":sys.argv[1]},"cwd":sys.argv[2]}))' "$cmd" "$cwd" \
    | OKF_VALIDATOR="$SKILL/validate_okf.py" python3 "$HOOK" >/dev/null 2>"$T/gate.err" && echo 0 || echo $?
}

echo "scaffold + validate"
P="$T/proj"; mkdir -p "$P"
bash "$SKILL/scaffold_okf.sh" "$P" >/dev/null
[ -f "$P/okf/index.md" ] && ok "scaffold created okf/index.md" || bad "scaffold"
python3 "$SKILL/validate_okf.py" "$P/okf" --strict --quiet-info >/dev/null && ok "fresh scaffold is CONFORMANT under --strict" || bad "fresh scaffold validates"
bash "$SKILL/scaffold_okf.sh" "$P" >/dev/null 2>&1 && bad "scaffold overwrote an existing bundle" || ok "scaffold refuses to overwrite"

echo "validator catches a missing type"
cat > "$P/okf/tables/orders.md" <<'EOF'
---
title: Orders
---
# Schema
EOF
python3 "$SKILL/validate_okf.py" "$P/okf" >/dev/null 2>&1 && bad "missing type passed" || ok "missing type is an ERROR"
cat > "$P/okf/tables/orders.md" <<'EOF'
---
type: Table
title: Orders
description: One row per order.
tags: [sales]
generated: { by: claude-code/test, at: 2026-01-01T00:00:00Z }
status: stable
---
# Schema
| Column | Type |
|---|---|
| order_id | STRING |
EOF
printf '# Tables\n\n* [Orders](/tables/orders.md) - one row per order\n' > "$P/okf/tables/index.md"
python3 "$SKILL/validate_okf.py" "$P/okf" --strict --quiet-info >/dev/null && ok "well-formed concept validates" || bad "well-formed concept"

echo "migrate a v0.1 bundle"
M="$T/old/okf"; mkdir -p "$M/metrics"
printf '# Bundle\n\nokf_version: "0.1"\n\n* [metrics](/metrics/index.md)\n' > "$M/index.md"
printf '# Metrics\n\n* [Revenue](/metrics/revenue.md)\n' > "$M/metrics/index.md"
cat > "$M/metrics/revenue.md" <<'EOF'
---
type: Metric
title: Revenue
description: Sum of paid orders.
timestamp: 2026-01-01T00:00:00Z
---
# Computation
SUM(amount)

# Citations
* [Finance definition](https://example.com/finance/revenue)
EOF
python3 "$SKILL/migrate_okf.py" "$M" --by human:tester >/dev/null
grep -q 'generated:' "$M/metrics/revenue.md" && ! grep -q '^timestamp:' "$M/metrics/revenue.md" && ok "timestamp rewritten to generated" || bad "migrate timestamp"
grep -q 'okf_version: "0.2"' "$M/index.md" && ok "okf_version moved to 0.2 frontmatter" || bad "migrate version"
python3 "$SKILL/validate_okf.py" "$M" >/dev/null 2>&1 && ok "migrated bundle validates" || bad "migrated bundle validates"

echo "commit gate"
G="$T/gated"; mkdir -p "$G"; git -C "$G" init -q; git -C "$G" config user.email t@example.com; git -C "$G" config user.name t
bash "$SKILL/scaffold_okf.sh" "$G" >/dev/null
mkdir -p "$G/migrations" "$G/src"
echo 'create table x(id int);' > "$G/migrations/0001.sql"
echo 'x = 1' > "$G/src/util.py"
git -C "$G" add -A; git -C "$G" commit -qm init
echo 'alter table x add y int;' >> "$G/migrations/0001.sql"; git -C "$G" add -A
[ "$(gate "$G" 'git commit -m "schema"')" = 2 ] && grep -q 'okf/tables' "$T/gate.err" && ok "blocks a schema change with no okf/ update, names tables/" || bad "block on stale knowledge"
[ "$(gate "$G" 'git commit -m "schema" [okf-skip]')" = 0 ] && ok "[okf-skip] opt-out allows" || bad "okf-skip"
echo '* placeholder' >> "$G/okf/tables/index.md"; git -C "$G" add -A
[ "$(gate "$G" 'git commit -m "schema + okf"')" = 0 ] && ok "allows when okf/ is staged alongside" || bad "allow with okf staged"
git -C "$G" commit -qm "schema + okf"
echo 'y = 2' >> "$G/src/util.py"; git -C "$G" add -A
[ "$(gate "$G" 'git commit -m "refactor"')" = 0 ] && ok "ignores a plain code change" || bad "plain code change blocked"
printf -- '---\ntitle: broken\n---\nno type\n' > "$G/okf/tables/broken.md"; git -C "$G" add -A
[ "$(gate "$G" 'git commit -m "bad bundle"')" = 2 ] && grep -q 'does not validate' "$T/gate.err" && ok "blocks a non-validating bundle" || bad "block on invalid bundle"
[ "$(gate "$G" 'git status')" = 0 ] && ok "non-commit git commands pass through" || bad "non-commit passthrough"
N="$T/nobundle"; mkdir -p "$N"; git -C "$N" init -q; echo a > "$N/migrations.sql"; git -C "$N" add -A
[ "$(gate "$N" 'git commit -m x')" = 0 ] && ok "repos without okf/ are left alone" || bad "no-bundle passthrough"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
