#!/usr/bin/env python3
"""
migrate_okf.py: upgrade an OKF v0.1 bundle in place to v0.2.

What it changes (SPEC.md section 13, "Changes from v0.1"):
  1. `timestamp: <datetime>`  ->  `generated: { by: <actor>, at: <datetime> }`
     The value is kept; a bare date gains T00:00:00Z; a datetime without an
     offset gains Z. If `generated` already exists, `timestamp` is just dropped.
  2. A body `# Citations` list of markdown links  ->  `sources:` frontmatter
     entries (id, resource, title) plus footnote definitions `[^id]: Title` in
     the body, so claims can be attributed per the v0.2 footnote convention.
     Only sections made purely of link bullets are converted; anything else is
     left alone and reported for manual attention.
  3. Bundle-root index.md: a body line `okf_version: "0.1"` becomes a
     frontmatter block declaring okf_version: "0.2" (the only frontmatter an
     index.md may carry).
  4. log.md at the bundle root gets a dated **Migration** entry, newest first.

Frontmatter is edited line by line, never re-serialized, so key order,
comments, and quoting elsewhere in the file survive untouched.

Usage:
    python3 migrate_okf.py <bundle-dir> --by <actor> [--dry-run] [--no-citations]

  --by ACTOR   REQUIRED. Who produced the existing content, in the actor
               convention: `human:<id>` for hand-written concepts, or
               `<producer>/<version>` (e.g. claude-code/fable-5.1) for
               agent-generated ones. Choose honestly: consumers derive trust
               from it. With --by-git this is only the fallback.
  --by-git     Derive each concept's actor from git: the Co-Authored-By
               trailer of the last commit touching that file (e.g.
               "Claude Opus 4.8 (1M context)" becomes claude-code/opus-4.8).
               Files with no such trailer, or not in git, use --by.
  --dry-run    Print the plan, change nothing.
  --no-citations   Skip the # Citations -> sources conversion.

Run validate_okf.py afterwards.
"""
import argparse
import datetime as dt
import os
import re
import sys

ACTOR_RE = re.compile(r"^(human:[^\s]+|process:[^\s]+|[^\s/:]+/[^\s]+)$")
TS_LINE_RE = re.compile(r"^(\s*)timestamp\s*:\s*(.*?)\s*$")
KEY_RE = re.compile(r"^([A-Za-z_][\w-]*)\s*:")
LINK_RE = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")
CIT_HEAD_RE = re.compile(r"^#\s+Citations\s*$")
VERSION_BODY_RE = re.compile(r"^\s*okf_version\s*:\s*[\"']?0\.1[\"']?\s*$")


def split_frontmatter(text):
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def normalize_ts(raw):
    v = raw.strip().strip('"').strip("'")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", v):
        return v + "T00:00:00Z"
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$", v):
        return v.replace(" ", "T") + "Z"
    if re.match(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:?\d{2})$", v):
        v = v.replace(" ", "T")
        m = re.match(r"^(.*[+-]\d{2})(\d{2})$", v)
        return f"{m.group(1)}:{m.group(2)}" if m else v
    return None


def slugify(text, taken):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    s = "-".join(s.split("-")[:5]) or "source"
    base, n = s, 2
    while s in taken:
        s, n = f"{base}-{n}", n + 1
    taken.add(s)
    return s


def git_actor(path):
    """Actor from the Co-Authored-By trailer of the last commit touching path."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", os.path.dirname(path), "log", "-1",
             "--format=%(trailers:key=Co-Authored-By,valueonly)", "--", os.path.basename(path)],
            capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    for line in out.stdout.splitlines():
        m = re.match(r"\s*Claude\s+([^<(]+?)\s*(\(.*?\))?\s*<", line)
        if m:
            slug = re.sub(r"[^a-z0-9.]+", "-", m.group(1).strip().lower()).strip("-")
            return f"claude-code/{slug}"
    return None


def top_level_keys(fm_text):
    return {m.group(1) for line in fm_text.splitlines() for m in [KEY_RE.match(line)] if m}


def migrate_frontmatter(fm_text, actor, notes):
    """Return new frontmatter text (or None if unchanged)."""
    keys = top_level_keys(fm_text)
    if "timestamp" not in keys:
        return None
    out, changed = [], False
    for line in fm_text.splitlines():
        m = TS_LINE_RE.match(line)
        if m and m.group(1) == "":
            if "generated" in keys:
                notes.append("dropped `timestamp` (generated already present)")
            else:
                ts = normalize_ts(m.group(2))
                if ts is None:
                    notes.append(f"could not parse timestamp {m.group(2)!r}; left as is")
                    out.append(line)
                    continue
                out.append(f"generated: {{ by: {actor}, at: {ts} }}")
                notes.append(f"timestamp -> generated.at ({ts})")
            changed = True
            continue
        out.append(line)
    return "\n".join(out) if changed else None


def extract_citations(body):
    """Return (links, new_body) if a pure link-list # Citations section exists."""
    lines = body.splitlines()
    start = next((i for i, l in enumerate(lines) if CIT_HEAD_RE.match(l)), None)
    if start is None:
        return None, body
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("# ")), len(lines))
    links = []
    for l in lines[start + 1:end]:
        s = l.strip()
        if not s:
            continue
        m = LINK_RE.search(s)
        prefix = s[:m.start()] if m else s
        # Allow "- ", "* ", "[1] ", "1. " prefixes only; anything else is prose.
        if not m or not re.match(r"^(\s*(?:[-*]|\[\d+\]|\d+\.)\s*)?$", prefix):
            return "manual", body
        links.append((m.group(1).strip(), m.group(2).strip()))
    if not links:
        return None, body
    return links, "\n".join(lines[:start] + lines[end:]).rstrip("\n") + "\n"


def migrate_concept(path, actor, do_citations, dry, log, by_git=False, tally=None):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    fm_text, body = split_frontmatter(text)
    if fm_text is None:
        return False
    notes = []
    if by_git:
        derived = git_actor(path)
        if derived:
            actor = derived
        else:
            notes.append(f"no git co-author trailer; using fallback actor {actor}")
        if tally is not None:
            tally[actor] = tally.get(actor, 0) + 1
    new_fm = migrate_frontmatter(fm_text, actor, notes)
    fm_out = new_fm if new_fm is not None else fm_text
    body_out = body

    if do_citations:
        links, stripped = extract_citations(body)
        if links == "manual":
            notes.append("# Citations section has non-link content; convert to `sources` by hand")
        elif links and "sources" in top_level_keys(fm_out):
            notes.append("# Citations present but `sources` already exists; merge by hand")
        elif links:
            taken = set()
            entries, defs = [], []
            for title, url in links:
                sid = slugify(title or url, taken)
                entries.append(f"  - id: {sid}\n    resource: {url}\n    title: {yaml_str(title or url)}")
                defs.append(f"[^{sid}]: {title or url}")
            fm_out = fm_out.rstrip("\n") + "\nsources:\n" + "\n".join(entries)
            body_out = stripped.rstrip("\n") + "\n\n# Sources\n\n" + "\n".join(defs) + "\n"
            notes.append(f"# Citations -> sources ({len(links)} entries) + footnote definitions")

    if not notes:
        return False
    log.append((path, notes))
    if not dry and (fm_out != fm_text or body_out != body):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"---\n{fm_out}\n---\n{body_out}")
    return True


def yaml_str(s):
    if re.search(r"[:#\[\]{}&*!|>'\"%@`,]", s) or s != s.strip():
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def migrate_root_index(root, dry, log):
    path = os.path.join(root, "index.md")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    fm_text, body = split_frontmatter(text)
    notes = []
    if fm_text is not None:
        new_fm = re.sub(r"(okf_version\s*:\s*)[\"']?[\d.]+[\"']?", r'\g<1>"0.2"', fm_text)
        if new_fm == fm_text and "okf_version" not in fm_text:
            new_fm = fm_text.rstrip("\n") + '\nokf_version: "0.2"'
        if new_fm != fm_text:
            notes.append("okf_version -> \"0.2\" in frontmatter")
            text = f"---\n{new_fm}\n---\n{body}"
    else:
        lines = body.splitlines()
        kept = [l for l in lines if not VERSION_BODY_RE.match(l)]
        if len(kept) != len(lines):
            notes.append("moved body line okf_version: \"0.1\" into frontmatter as \"0.2\"")
        else:
            notes.append("added frontmatter okf_version: \"0.2\"")
        body_new = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).lstrip("\n")
        text = f'---\nokf_version: "0.2"\n---\n{body_new}' + ("\n" if not body_new.endswith("\n") else "")
    if notes:
        log.append((path, notes))
        if not dry:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(text)


def append_log(root, dry, log, summary):
    path = os.path.join(root, "log.md")
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    entry = (f"## {today}\n* **Migration**: Upgraded bundle from OKF v0.1 to v0.2 "
             f"with migrate_okf.py ({summary}).\n")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if "migrate_okf.py" in text:
            return
        lines = text.splitlines(keepends=True)
        # insert after the first H1 (and its trailing blank line), else at top
        i = 0
        if lines and lines[0].startswith("# "):
            i = 1
            while i < len(lines) and lines[i].strip() == "":
                i += 1
        head = "".join(lines[:i]).rstrip("\n")
        text = (head + "\n\n" if head else "") + entry + "\n" + "".join(lines[i:])
    else:
        text = f"# Change Log\n\n{entry}"
    log.append((path, ["appended **Migration** entry"]))
    if not dry:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


def main():
    ap = argparse.ArgumentParser(description="Upgrade an OKF v0.1 bundle to v0.2 in place.")
    ap.add_argument("bundle")
    ap.add_argument("--by", required=True, metavar="ACTOR",
                    help="actor who produced the content (human:<id> or <producer>/<version>)")
    ap.add_argument("--by-git", action="store_true",
                    help="derive each file's actor from its last git Co-Authored-By trailer")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-citations", action="store_true")
    args = ap.parse_args()

    if not ACTOR_RE.match(args.by):
        print(f"ERROR: --by {args.by!r} is not an OKF actor "
              f"(human:<id>, process:<id>, or <producer>/<version>)")
        return 2
    root = os.path.abspath(args.bundle)
    if not os.path.isdir(root):
        print(f"ERROR: not a directory: {root}")
        return 2

    log = []
    tally = {} if args.by_git else None
    concepts = migrated = 0
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in sorted(files):
            if not f.endswith(".md") or f in ("index.md", "log.md"):
                continue
            concepts += 1
            if migrate_concept(os.path.join(dirpath, f), args.by, not args.no_citations,
                               args.dry_run, log, args.by_git, tally):
                migrated += 1
    migrate_root_index(root, args.dry_run, log)
    if migrated or not args.dry_run:
        if tally:
            who = "generated.by derived from git trailers: " + ", ".join(
                f"{k} x{v}" for k, v in sorted(tally.items(), key=lambda kv: -kv[1]))
        else:
            who = f"generated.by set to {args.by}"
        append_log(root, args.dry_run, log, f"{migrated} of {concepts} concepts touched; {who}")

    mode = "DRY RUN" if args.dry_run else "APPLIED"
    print(f"OKF migration {mode}: {root}")
    print(f"  concepts: {concepts}, changed: {migrated}")
    if tally:
        for k, v in sorted(tally.items(), key=lambda kv: -kv[1]):
            print(f"  actor {k}: {v}")
    for path, notes in log:
        rel = os.path.relpath(path, root)
        for n in notes:
            print(f"  {rel}: {n}")
    print("Next: python3 validate_okf.py", root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
