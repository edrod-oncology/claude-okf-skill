#!/usr/bin/env bash
# scaffold_okf.sh: create a minimal conformant OKF v0.2 bundle skeleton.
#
# Usage:  scaffold_okf.sh <project-dir> [bundle-name]
#   <project-dir>  project root (the bundle is created at <project-dir>/<bundle-name>)
#   [bundle-name]  defaults to "okf"
#
# This only creates structure, a root index (declaring okf_version "0.2" in
# the one frontmatter block an index.md may carry), empty type-directory
# indexes, and a log. Seed real concept files yourself (or with a subagent);
# do NOT invent facts. Every concept you write should carry
# `generated: { by: <actor>, at: <ISO datetime with offset> }`.
set -euo pipefail

PROJECT_DIR="${1:?usage: scaffold_okf.sh <project-dir> [bundle-name]}"
BUNDLE_NAME="${2:-okf}"
BUNDLE="$PROJECT_DIR/$BUNDLE_NAME"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo 2026-06-15T00:00:00Z)"
PROJ="$(basename "$PROJECT_DIR")"

if [ -e "$BUNDLE/index.md" ]; then
  echo "refusing to overwrite existing bundle at: $BUNDLE" >&2
  exit 1
fi

mkdir -p "$BUNDLE"
# Common concept-type directories. Trim/extend per project after scaffolding.
# Add `computations/` when the project has Attested Computations (spec section 10).
for d in datasets tables metrics runbooks playbooks apis references; do
  mkdir -p "$BUNDLE/$d"
done

cat > "$BUNDLE/index.md" <<EOF
---
okf_version: "0.2"
---
# $PROJ: Knowledge Bundle

This is an Open Knowledge Format (OKF v0.2) bundle for **$PROJ**. Each concept
is one markdown file with YAML frontmatter; the directory tree groups concepts
by type and markdown links connect related concepts. Provenance lives in
frontmatter: \`generated\` says who wrote a concept and when, \`verified\` who
confirmed it, \`sources\` what it was derived from, and \`status\` /
\`stale_after\` whether it is still current.

## Concept types
* [datasets](/datasets/index.md) - logical data sources
* [tables](/tables/index.md) - individual tables / collections / schemas
* [metrics](/metrics/index.md) - defined measures and their formulas
* [runbooks](/runbooks/index.md) - operational procedures
* [playbooks](/playbooks/index.md) - strategies and decision guides
* [apis](/apis/index.md) - service endpoints and integrations
* [references](/references/index.md) - mirrored external material and context

## History
* [log](/log.md) - change history, newest first
EOF

for d in datasets tables metrics runbooks playbooks apis references; do
  cat > "$BUNDLE/$d/index.md" <<EOF
# ${d^}

* _none yet: add ${d%s} concept files here_
EOF
done

cat > "$BUNDLE/log.md" <<EOF
# Change Log

## ${NOW%%T*}
* **Initialization**: Created the OKF v0.2 bundle scaffold for $PROJ.
EOF

echo "Scaffolded OKF v0.2 bundle at: $BUNDLE"
echo "Next: replace placeholder indexes with real, repo-seeded concept files,"
echo "      each with generated: { by: <actor>, at: $NOW }."
