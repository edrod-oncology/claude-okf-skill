---
okf_version: "0.2"
---
# sample-project: Knowledge Bundle (example)

This is an Open Knowledge Format (OKF v0.2) bundle for **sample-project**. Each concept
is one markdown file with YAML frontmatter; the directory tree groups concepts
by type and markdown links connect related concepts. Provenance lives in
frontmatter: `generated` says who wrote a concept and when, `verified` who
confirmed it, `sources` what it was derived from, and `status` /
`stale_after` whether it is still current.

## Concept types
* [datasets](/datasets/index.md) - logical data sources
* [tables](/tables/index.md) - individual tables / collections / schemas
* [metrics](/metrics/index.md) - defined measures and their formulas
* [runbooks](/runbooks/index.md) - operational procedures
* [references](/references/index.md) - mirrored external material and context

## History
* [log](/log.md) - change history, newest first
