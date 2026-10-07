#!/usr/bin/env python3
"""
validate_okf.py: check an OKF v0.2 bundle for conformance and spec hygiene.

Conformance (OKF v0.2 SPEC.md section 11): a bundle is conformant iff
  1. every non-reserved .md file has a parseable YAML frontmatter block,
  2. every such frontmatter block has a non-empty `type` field, and
  3. reserved files (index.md, log.md) follow their conventions when present
     (index.md carries NO frontmatter, except the bundle-root index.md which
     MAY carry a frontmatter block holding only `okf_version`).

Anything beyond that is reported as a WARN (a SHOULD in the spec, or a
retired v0.1 field) or an INFO (a hint). --strict turns WARNs into failures.

What the WARN pass checks (spec sections 5 through 10):
  * recommended fields: title, description, tags (resource is INFO, since
    abstract concepts legitimately have none)
  * v0.1 leftovers: `timestamp` (superseded by generated.at) and a body
    `# Citations` list (superseded by `sources`)
  * generated / verified shape, actor convention, ISO 8601 datetimes with an
    explicit UTC offset
  * status enum, stale_after format (INFO when already stale)
  * sources entries (resource required, credibility signals well-formed),
    usage_window, and footnote labels that resolve to a sources[].id
  * Attested Computation contract: runtime, parameters, computation location,
    executor.resource, attester.resource
  * cross-links (bundle-relative and relative) and path-valued fields that
    point at files missing from the bundle
  * log.md date headings (ISO YYYY-MM-DD, newest first)
  * concepts not listed in their directory's index.md (INFO)

Uses PyYAML when available for full frontmatter parsing. Without it, falls
back to a minimal top-level key parser and skips the nested-structure checks
(and says so).

Usage:
    python3 validate_okf.py <bundle-dir> [--strict] [--quiet-info]

Exit code 0 = conformant (and, with --strict, warning-free). Non-zero otherwise.
"""
import argparse
import datetime as dt
import os
import re
import sys

try:
    import yaml  # type: ignore
    HAVE_YAML = True
except ImportError:  # pragma: no cover
    yaml = None
    HAVE_YAML = False

SPEC_VERSION = "0.2"
RESERVED = {"index.md", "log.md"}
RECOMMENDED_WARN = ["title", "description", "tags"]
RECOMMENDED_INFO = ["resource"]
STATUS_VALUES = {"draft", "stable", "deprecated"}
ISO_DT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$"
)
ACTOR_RE = re.compile(r"^(human:[^\s]+|process:[^\s]+|[^\s/:]+/[^\s]+)$")
DATE_HEADING_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})(\b.*)?$")
FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\](?!:)")
FOOTNOTE_DEF_RE = re.compile(r"^\[\^([^\]\s]+)\]:", re.MULTILINE)
MD_LINK_RE = re.compile(r"\]\(([^)\s]+)\)")
URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
FENCE_RE = re.compile(r"^(```|~~~)", re.MULTILINE)


# ---------------------------------------------------------------- parsing

def split_frontmatter(text):
    """Return (frontmatter_str, body_str) or (None, text) if no block."""
    if not text.startswith("---"):
        return None, text
    m = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def parse_frontmatter(fm_text):
    """Parse to a dict. Returns (dict_or_None, error_message_or_None)."""
    if HAVE_YAML:
        try:
            data = yaml.safe_load(fm_text)
        except yaml.YAMLError as e:  # type: ignore
            return None, f"YAML parse error: {str(e).splitlines()[0]}"
        if data is None:
            return {}, None
        if not isinstance(data, dict):
            return None, "frontmatter is not a YAML mapping"
        return data, None
    # Fallback: top-level `key: value` scalars only.
    data = {}
    for line in fm_text.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if m:
            data[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    return data, None


def strip_code_fences(body):
    """Remove fenced code blocks so links/footnotes inside code are ignored."""
    out, in_fence = [], False
    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------- helpers

def is_iso_datetime(val):
    """True if val is an ISO 8601 datetime with an explicit UTC offset."""
    if isinstance(val, dt.datetime):
        return val.tzinfo is not None
    if isinstance(val, dt.date):
        return False  # bare date: needs a time and an offset
    if isinstance(val, str):
        return bool(ISO_DT_RE.match(val.strip()))
    return False


def to_datetime(val):
    if isinstance(val, dt.datetime):
        return val
    if isinstance(val, str):
        s = val.strip().replace("Z", "+00:00")
        try:
            return dt.datetime.fromisoformat(s)
        except ValueError:
            return None
    return None


def is_actor(val):
    return isinstance(val, str) and bool(ACTOR_RE.match(val.strip()))


SOURCE_AUTHOR_RE = re.compile(r"^([A-Za-z][\w-]*:[^\s]+|[^\s/:]+/[^\s]+)$")


def is_source_author(val):
    """sources[].author is looser than generated.by: the spec's own example
    uses `team:ga4-docs`, so any <kind>:<id> or <producer>/<version> passes."""
    return isinstance(val, str) and bool(SOURCE_AUTHOR_RE.match(val.strip()))


def looks_like_path(val):
    """A path-valued field that should resolve inside the bundle."""
    if not isinstance(val, str):
        return False
    v = val.strip()
    if not v or URL_SCHEME_RE.match(v) or " " in v:
        return False
    return "/" in v or v.endswith((".md", ".py", ".sql", ".yml", ".yaml", ".json"))


def resolve_path(root, rel_file, target):
    """Resolve a path-valued field or link to an absolute filesystem path.

    `/x` is bundle-relative. Anything else is tried file-relative first and
    then bundle-root-relative (the upstream sample bundles write
    `policies/x.md` from inside `computations/` and expect the latter).
    Returns the first candidate that exists, else the file-relative one.
    """
    target = target.split("#", 1)[0]
    if not target:
        return None
    if target.startswith("/"):
        return os.path.normpath(os.path.join(root, target.lstrip("/")))
    file_rel = os.path.normpath(os.path.join(os.path.dirname(rel_file), target))
    if os.path.exists(file_rel):
        return file_rel
    root_rel = os.path.normpath(os.path.join(root, target))
    return root_rel if os.path.exists(root_rel) else file_rel


# ---------------------------------------------------------------- checks

class Report:
    def __init__(self):
        self.errors, self.warnings, self.infos = [], [], []

    def err(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)

    def info(self, msg):
        self.infos.append(msg)


def check_timestamp_field(rep, rel, label, val):
    if not is_iso_datetime(val):
        rep.warn(f"{rel}: `{label}` must be an ISO 8601 datetime with an "
                 f"explicit offset (e.g. 2026-06-30T14:00:00Z), got {val!r}")


def check_actor_field(rep, rel, label, val):
    if not is_actor(val):
        rep.warn(f"{rel}: `{label}` must follow the actor convention "
                 f"(<producer>/<version>, human:<id>, process:<id>), got {val!r}")


def check_generated(rep, rel, fm):
    gen = fm.get("generated")
    if gen is None:
        return
    if not isinstance(gen, dict):
        rep.warn(f"{rel}: `generated` must be a mapping {{ by, at }}")
        return
    if "by" not in gen:
        rep.warn(f"{rel}: `generated.by` is REQUIRED within `generated`")
    else:
        check_actor_field(rep, rel, "generated.by", gen["by"])
    if "at" in gen:
        check_timestamp_field(rep, rel, "generated.at", gen["at"])


def check_verified(rep, rel, fm):
    ver = fm.get("verified")
    if ver is None:
        return
    entries = ver if isinstance(ver, list) else [ver]
    for i, ent in enumerate(entries):
        lbl = f"verified[{i}]" if isinstance(ver, list) else "verified"
        if not isinstance(ent, dict):
            rep.warn(f"{rel}: `{lbl}` must be a mapping {{ by, at }}")
            continue
        if "by" not in ent:
            rep.warn(f"{rel}: `{lbl}.by` is required")
        else:
            check_actor_field(rep, rel, f"{lbl}.by", ent["by"])
        if "at" not in ent:
            rep.warn(f"{rel}: `{lbl}.at` is required")
        else:
            check_timestamp_field(rep, rel, f"{lbl}.at", ent["at"])


def check_lifecycle(rep, rel, fm, now):
    if "status" in fm and fm["status"] not in STATUS_VALUES:
        rep.warn(f"{rel}: `status` must be one of draft|stable|deprecated, "
                 f"got {fm['status']!r}")
    if "stale_after" in fm:
        check_timestamp_field(rep, rel, "stale_after", fm["stale_after"])
        d = to_datetime(fm["stale_after"])
        if d is not None and d.tzinfo is not None and now >= d:
            rep.info(f"{rel}: stale (now >= stale_after {fm['stale_after']})")


def check_usage_window(rep, rel, label, win):
    if not isinstance(win, dict) or "from" not in win or "to" not in win:
        rep.warn(f"{rel}: `{label}` must be a mapping {{ from, to }}")
        return
    check_timestamp_field(rep, rel, f"{label}.from", win["from"])
    check_timestamp_field(rep, rel, f"{label}.to", win["to"])


def check_sources(rep, rel, fm, body_nofence, root):
    """Validate `sources`, `usage_window`, and footnote attribution."""
    src = fm.get("sources")
    ids = set()
    if src is not None:
        if not isinstance(src, list):
            rep.warn(f"{rel}: `sources` must be a YAML list of entries")
            src = []
        has_usage = False
        for i, ent in enumerate(src):
            lbl = f"sources[{i}]"
            if not isinstance(ent, dict):
                rep.warn(f"{rel}: `{lbl}` must be a mapping")
                continue
            if "resource" not in ent or not ent["resource"]:
                rep.warn(f"{rel}: `{lbl}.resource` is REQUIRED within a sources entry")
            elif looks_like_path(ent["resource"]):
                p = resolve_path(root, os.path.join(root, rel), ent["resource"])
                if p and not os.path.exists(p):
                    rep.warn(f"{rel}: `{lbl}.resource` points at a missing "
                             f"bundle file -> {ent['resource']}")
            if "id" in ent:
                ids.add(str(ent["id"]))
            if "author" in ent and not is_source_author(ent["author"]):
                rep.warn(f"{rel}: `{lbl}.author` should name who produced the source "
                         f"(human:<id>, team:<id>, process:<id>, or <producer>/<version>), "
                         f"got {ent['author']!r}")
            if "last_modified" in ent:
                check_timestamp_field(rep, rel, f"{lbl}.last_modified", ent["last_modified"])
            if "usage_count" in ent:
                has_usage = True
                if not isinstance(ent["usage_count"], int):
                    rep.warn(f"{rel}: `{lbl}.usage_count` must be an integer")
            if "usage_window" in ent:
                check_usage_window(rep, rel, f"{lbl}.usage_window", ent["usage_window"])
        if has_usage and "usage_window" not in fm and not any(
            isinstance(e, dict) and "usage_window" in e for e in src
        ):
            rep.warn(f"{rel}: `usage_count` present but no `usage_window` to frame it")
    if "usage_window" in fm:
        check_usage_window(rep, rel, "usage_window", fm["usage_window"])

    # Footnote labels are the join key into sources[].id.
    refs = set(FOOTNOTE_REF_RE.findall(body_nofence))
    defs = set(FOOTNOTE_DEF_RE.findall(body_nofence))
    for label in sorted(refs):
        if label not in defs:
            rep.warn(f"{rel}: footnote [^{label}] is referenced but never defined")
        if src is not None and ids and label not in ids:
            rep.warn(f"{rel}: footnote [^{label}] does not match any sources[].id "
                     f"(ids: {', '.join(sorted(ids))})")
        if src is None:
            rep.info(f"{rel}: footnote [^{label}] used but no `sources` frontmatter "
                     f"to attribute it to")


def check_attested_computation(rep, rel, fm, body, root):
    if str(fm.get("type", "")).strip().lower() != "attested computation":
        return
    if not fm.get("runtime"):
        rep.warn(f"{rel}: Attested Computation: `runtime` is REQUIRED for this type")
    params = fm.get("parameters")
    if params is not None:
        if not isinstance(params, list):
            rep.warn(f"{rel}: `parameters` must be a list of {{ name, type, required }}")
        else:
            for i, p in enumerate(params):
                if not isinstance(p, dict) or not {"name", "type", "required"} <= set(p):
                    rep.warn(f"{rel}: `parameters[{i}]` must carry name, type, required")
    comp = fm.get("computation")
    body_has = re.search(r"^#\s+Computation\s*$", body, re.MULTILINE) is not None
    if comp:
        p = resolve_path(root, os.path.join(root, rel), str(comp))
        if looks_like_path(str(comp)) and p and not os.path.exists(p):
            rep.warn(f"{rel}: `computation` points at a missing bundle file -> {comp}")
    elif not body_has:
        rep.warn(f"{rel}: Attested Computation needs either `computation: <path>` "
                 f"or a body `# Computation` section")
    for key in ("executor", "attester"):
        val = fm.get(key)
        if val is None:
            rep.warn(f"{rel}: Attested Computation: `{key}` is missing")
            continue
        if not isinstance(val, dict) or not val.get("resource"):
            rep.warn(f"{rel}: `{key}.resource` is required")
            continue
        res = str(val["resource"])
        if looks_like_path(res):
            p = resolve_path(root, os.path.join(root, rel), res)
            if p and not os.path.exists(p):
                rep.warn(f"{rel}: `{key}.resource` points at a missing bundle file -> {res}")
    ex = fm.get("executor")
    if isinstance(ex, dict) and "receipt" in ex and not isinstance(ex["receipt"], list):
        rep.warn(f"{rel}: `executor.receipt` must be a list of field names")


def check_links(rep, rel, body_nofence, root):
    for m in MD_LINK_RE.finditer(body_nofence):
        target = m.group(1)
        if URL_SCHEME_RE.match(target) or target.startswith("#"):
            continue
        p = resolve_path(root, os.path.join(root, rel), target)
        if p and not os.path.exists(p):
            rep.warn(f"{rel}: broken link -> {target}")


def check_root_index(rep, rel, fm_text):
    if fm_text is None:
        rep.info(f"{rel}: bundle-root index.md declares no `okf_version` "
                 f"(optional; add a frontmatter block with okf_version: \"{SPEC_VERSION}\")")
        return
    data, err = parse_frontmatter(fm_text)
    if err or data is None:
        rep.err(f"{rel}: root index.md frontmatter is unparseable ({err})")
        return
    extra = set(data) - {"okf_version"}
    if extra:
        rep.err(f"{rel}: root index.md frontmatter may only carry `okf_version`, "
                f"found: {', '.join(sorted(extra))}")
    v = data.get("okf_version")
    if v is None:
        rep.warn(f"{rel}: root index.md frontmatter present but no `okf_version`")
    elif str(v) != SPEC_VERSION:
        rep.warn(f"{rel}: declares okf_version {v!r}; this validator targets "
                 f"{SPEC_VERSION} (run migrate_okf.py to upgrade)")


def check_log(rep, rel, text):
    _, body = split_frontmatter(text)
    dates = []
    for line in body.splitlines():
        if line.startswith("## "):
            m = DATE_HEADING_RE.match(line)
            if not m:
                rep.warn(f"{rel}: log heading {line.strip()!r} does not start "
                         f"with an ISO YYYY-MM-DD date")
            else:
                dates.append(m.group(1))
    if dates != sorted(dates, reverse=True):
        rep.warn(f"{rel}: log entries should be newest first")


def check_index_coverage(rep, root, dirpath, md_names):
    idx = os.path.join(dirpath, "index.md")
    if not os.path.exists(idx):
        return
    with open(idx, encoding="utf-8") as fh:
        idx_text = fh.read()
    for name in md_names:
        if name in RESERVED:
            continue
        stem = name[:-3]
        if stem not in idx_text and name not in idx_text:
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            rep.info(f"{rel}: not listed in its directory's index.md")


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--strict", action="store_true",
                    help="treat warnings as failures")
    ap.add_argument("--quiet-info", action="store_true",
                    help="suppress INFO lines")
    args = ap.parse_args()

    root = os.path.abspath(args.bundle)
    if not os.path.isdir(root):
        print(f"ERROR: not a directory: {root}")
        return 2

    rep = Report()
    now = dt.datetime.now(dt.timezone.utc)
    concept_count = 0
    md_files = []
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        names = sorted(f for f in files if f.endswith(".md"))
        for f in names:
            md_files.append(os.path.join(dirpath, f))
        check_index_coverage(rep, root, dirpath, names)

    if not md_files:
        rep.err("bundle contains no .md files")

    for path in sorted(md_files):
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        name = os.path.basename(path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        fm_text, body = split_frontmatter(text)

        if name == "index.md":
            if os.path.dirname(path) == root:
                check_root_index(rep, rel, fm_text)
            elif fm_text is not None:
                rep.err(f"{rel}: index.md MUST NOT contain frontmatter "
                        f"(only the bundle-root index.md may, and only okf_version)")
            continue
        if name == "log.md":
            check_log(rep, rel, text)
            continue

        concept_count += 1
        if fm_text is None:
            rep.err(f"{rel}: missing YAML frontmatter block (--- ... ---)")
            continue
        fm, err = parse_frontmatter(fm_text)
        if err or fm is None:
            rep.err(f"{rel}: {err}")
            continue
        t = fm.get("type")
        if t is None or str(t).strip() == "":
            rep.err(f"{rel}: frontmatter missing non-empty `type`")

        for key in RECOMMENDED_WARN:
            if key not in fm:
                rep.warn(f"{rel}: missing recommended field `{key}`")
        for key in RECOMMENDED_INFO:
            if key not in fm:
                rep.info(f"{rel}: no `{key}` (fine for abstract concepts)")
        if "tags" in fm and not isinstance(fm["tags"], list) and HAVE_YAML:
            rep.warn(f"{rel}: `tags` must be a YAML list")

        # v0.1 leftovers
        if "timestamp" in fm:
            if "generated" in fm:
                rep.warn(f"{rel}: legacy v0.1 `timestamp` alongside `generated`; drop it")
            else:
                rep.warn(f"{rel}: legacy v0.1 `timestamp`; superseded by "
                         f"generated: {{ by, at }} (run migrate_okf.py)")
        if re.search(r"^#\s+Citations\s*$", body, re.MULTILINE):
            rep.warn(f"{rel}: body `# Citations` list is superseded by `sources` "
                     f"frontmatter with footnote attribution (run migrate_okf.py)")
        if "generated" not in fm and "timestamp" not in fm:
            rep.info(f"{rel}: no `generated` provenance (who/when produced this)")

        body_nofence = strip_code_fences(body)
        if HAVE_YAML:
            check_generated(rep, rel, fm)
            check_verified(rep, rel, fm)
            check_lifecycle(rep, rel, fm, now)
            check_sources(rep, rel, fm, body_nofence, root)
            check_attested_computation(rep, rel, fm, body, root)
        check_links(rep, rel, body_nofence, root)

    print(f"OKF v{SPEC_VERSION} validation: {root}")
    if not HAVE_YAML:
        print("  note: PyYAML not installed; nested frontmatter checks skipped")
    print(f"  concept files: {concept_count}")
    print(f"  errors:   {len(rep.errors)}")
    print(f"  warnings: {len(rep.warnings)}")
    print(f"  info:     {len(rep.infos)}")
    for e in rep.errors:
        print(f"  ERROR  {e}")
    for w in rep.warnings:
        print(f"  WARN   {w}")
    if not args.quiet_info:
        for i in rep.infos:
            print(f"  INFO   {i}")

    if rep.errors:
        print("RESULT: NON-CONFORMANT")
        return 1
    if args.strict and rep.warnings:
        print("RESULT: conformant, but warnings present (--strict)")
        return 1
    print("RESULT: CONFORMANT")
    return 0


if __name__ == "__main__":
    sys.exit(main())
