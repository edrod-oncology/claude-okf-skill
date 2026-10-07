#!/usr/bin/env python3
"""
OKF commit gate. PreToolUse hook on Bash.

Blocks a `git commit` when the staged changes are knowledge-bearing and the
project's OKF bundle was not updated alongside them, and blocks when a staged
OKF bundle does not validate.

DESIGN NOTE, and the reason this is not simply "block every commit that does not
touch okf/": a gate that fires on changes it has no business firing on gets
switched off, and then it protects nothing. Most commits do not change what a
project KNOWS. A typo fix, a refactor, a test rename: none of those age the
knowledge bundle. So this fires only on paths that map to an OKF concept type,
and it names which concept the change implies rather than saying "update the
docs".

Exit codes (Claude Code PreToolUse contract):
  0  allow
  2  block, and feed stderr back to the model so it can act
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

def find_validator():
    """Locate validate_okf.py. Order: OKF_VALIDATOR env var, a skills/okf dir
    next to this hook (repo checkout layout), then the installed skill under
    $CLAUDE_HOME (default ~/.claude)."""
    env = os.environ.get("OKF_VALIDATOR")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    candidates = [
        here.parent / "skills" / "okf" / "validate_okf.py",
        Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude")) / "skills" / "okf" / "validate_okf.py",
    ]
    for c in candidates:
        if c.exists():
            return c
    return candidates[-1]


VALIDATOR = find_validator()

# A repo can take over the gate by shipping its own script at this path
# (relative to the repo root). Override with OKF_PROJECT_GATE.
PROJECT_GATE = os.environ.get("OKF_PROJECT_GATE", "scripts/okf-gate.mjs")

# A staged path matching one of these implies the named OKF concept type may be
# stale. Ordered most specific first; the first match wins.
KNOWLEDGE_PATHS = [
    (r"(^|/)(drizzle|migrations)/", "tables", "schema or migration changed"),
    (r"(^|/)schema/.*\.(ts|py|sql)$", "tables", "schema changed"),
    (r"(^|/)models?\.(ts|py)$", "tables", "model definitions changed"),
    (r"(^|/)index\.ts$", "apis", "a package's public surface changed"),
    (r"(^|/)(api|routes?|endpoints?)/", "apis", "an API surface changed"),
    (r"(^|/)openapi\.(ya?ml|json)$", "apis", "the API contract changed"),
    (r"(^|/)config\.(ts|py|js)$", "metrics", "tunable configuration changed"),
    (r"(^|/)\.github/workflows/", "runbooks", "CI changed"),
    (r"(^|/)(Dockerfile|docker-compose\.ya?ml|vercel\.json|fly\.toml)$", "runbooks", "deployment changed"),
    (r"(^|/)scripts/", "runbooks", "an operational script changed"),
    (r"(^|/)docs/.*(spec|design|plan|record)", "references", "a spec, plan, or record changed"),
]

# Paths that never imply a knowledge update, checked before the list above.
IGNORED = [
    r"(^|/)okf/",                      # the bundle itself
    r"(^|/)node_modules/",
    r"\.lock$|lock\.ya?ml$|-lock\.json$",
    r"(^|/)\.gitignore$",
    r"(^|/)(CHANGELOG|LICENSE)(\.md)?$",
    r"\.(png|jpe?g|gif|svg|ico|webp|pdf)$",
]

SKIP_MARKERS = ("[okf-skip]", "[skip-okf]")


def run(args, cwd):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=15)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception:
        return 1, "", ""


def repo_root(cwd):
    code, out, _ = run(["git", "rev-parse", "--show-toplevel"], cwd)
    return Path(out) if code == 0 and out else None


def staged_files(cwd):
    code, out, _ = run(["git", "diff", "--cached", "--name-only"], cwd)
    if code != 0 or not out:
        return []
    return [line for line in out.splitlines() if line]


def classify(paths):
    """Return {concept_type: set(reasons)} for knowledge-bearing staged paths."""
    hits = {}
    for p in paths:
        if any(re.search(pat, p) for pat in IGNORED):
            continue
        for pat, kind, reason in KNOWLEDGE_PATHS:
            if re.search(pat, p):
                hits.setdefault(kind, set()).add(reason)
                break
    return hits


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if payload.get("tool_name") != "Bash":
        sys.exit(0)

    command = (payload.get("tool_input") or {}).get("command", "") or ""
    if not re.search(r"\bgit\s+(-\S+\s+)*commit\b", command):
        sys.exit(0)

    # An explicit, greppable opt-out. Same bargain as an eslint-disable: the
    # override is visible in the command that used it.
    if any(m in command for m in SKIP_MARKERS):
        sys.exit(0)

    cwd = payload.get("cwd") or os.getcwd()
    root = repo_root(cwd)
    if root is None:
        sys.exit(0)

    bundle = root / "okf"
    if not bundle.is_dir():
        sys.exit(0)  # project has no OKF bundle; nothing to keep in sync

    # A repo that defines its own gate owns the rules. Its knowledge-bearing
    # paths are project specific, and two definitions of the same rule drift.
    # This falls back to the built-in defaults only for repos with no gate.
    own_gate = root / PROJECT_GATE
    if own_gate.exists():
        runner = ["node"] if own_gate.suffix in (".js", ".mjs", ".cjs") else ["python3"]
        code, out, err = run(runner + [str(own_gate), command], cwd)
        if code != 0:
            print((out + "\n" + err).strip(), file=sys.stderr)
            sys.exit(2)
        sys.exit(0)

    paths = staged_files(cwd)
    if not paths:
        sys.exit(0)  # nothing staged; let git report that itself

    okf_staged = [p for p in paths if re.search(r"(^|/)okf/", p)]

    # 1. If the bundle IS being changed, it must still validate.
    if okf_staged and VALIDATOR.exists():
        code, out, err = run(["python3", str(VALIDATOR), str(bundle), "--strict"], cwd)
        if code != 0:
            detail = (out + "\n" + err).strip()
            print(
                "OKF bundle does not validate, so this commit is blocked.\n\n"
                f"{detail}\n\n"
                "Fix the bundle, then commit. Run:\n"
                f"  python3 {VALIDATOR} {bundle} --strict",
                file=sys.stderr,
            )
            sys.exit(2)

    # 2. Knowledge-bearing changes must carry a bundle update.
    hits = classify(paths)
    if hits and not okf_staged:
        lines = [
            "This commit changes what the project KNOWS, but no OKF concept is staged with it.",
            "",
            "Staged changes imply these concept types are now stale:",
            "",
        ]
        for kind in sorted(hits):
            reasons = ", ".join(sorted(hits[kind]))
            existing = bundle / kind
            where = f"okf/{kind}/" if existing.is_dir() else f"okf/{kind}/ (create it)"
            lines.append(f"  {where:<28} {reasons}")
        lines += [
            "",
            "Update or add the matching concept file, stage it, and commit again.",
            "Never invent a fact to satisfy this gate: a conformant stub with a",
            "'> TODO:' body is correct where the ground truth is not known yet.",
            "",
            "If this change genuinely carries no new knowledge, say so explicitly by",
            "adding [okf-skip] to the commit command. The override is greppable on",
            "purpose, so a reviewer can see every time it was used.",
        ]
        print("\n".join(lines), file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
