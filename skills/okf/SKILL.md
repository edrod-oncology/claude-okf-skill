---
name: okf
description: Use when starting a new project or organizing an existing project's knowledge (docs, datasets, tables, metrics, runbooks, playbooks, APIs) so both AI agents and humans can consume it. Use during project init/planning intake, when creating or reorganizing project documentation, when asked to make knowledge portable, agent-readable, or Open Knowledge Format / OKF compliant, when an okf/ bundle still declares okf_version 0.1 or uses the retired timestamp field, or when a concept needs provenance, verification, staleness, or an attested computation.
---

# OKF: Open Knowledge Format

## Overview

OKF (Open Knowledge Format, Google Cloud, **v0.2**, canonical repo `GoogleCloudPlatform/open-knowledge-format`) represents project knowledge as **plain markdown files with YAML frontmatter in a directory tree**. The same files are readable by humans and consumable by AI agents with no SDK, no runtime, and no translation layer. It lives in git next to the code it describes.

**Core principle:** one concept = one file; the file path is its identity; markdown links between files form a knowledge graph. The only required frontmatter field is `type`. v0.2 adds optional, queryable **provenance** (`sources`), **trust** (`generated`, `verified`), **lifecycle** (`status`, `stale_after`), and **attestation** (`Attested Computation`) so a corpus that agents keep rewriting stays trustable.

Use this skill to (a) organize a project's knowledge into a conformant `okf/` bundle, (b) ask the right intake questions during project init/planning so knowledge is captured in OKF shape from day one, and (c) upgrade existing v0.1 bundles.

**Full normative rules:** see `okf-spec-reference.md` (load only when you need exact conformance details).

## When to use

- Starting a new project (capture knowledge in OKF shape from the start).
- Organizing or documenting an existing project's data, metrics, runbooks, APIs.
- Asked to make knowledge "portable," "agent-readable," or "OKF compliant."
- During project init / planning intake (ask the OKF questions below).
- An existing bundle declares `okf_version: "0.1"` or its concepts carry `timestamp` or a `# Citations` list (migrate it, see below).

**When NOT to use:** quick one-off answers, code that needs no shared knowledge artifact, or knowledge that already lives in a conformant v0.2 bundle (just update it).

## Bundle structure (quick reference)

A bundle is a directory (default `<project>/okf/`). One concept per file, grouped however fits:

```
okf/
├── index.md          # navigation; the ONLY index that may carry frontmatter (okf_version: "0.2")
├── log.md            # change history, newest first, ## YYYY-MM-DD headings (optional)
├── datasets/  tables/  metrics/  runbooks/  playbooks/  apis/  references/  computations/
│   ├── index.md      # listing for that group (NO frontmatter)
│   └── <concept>.md  # one concept, with frontmatter
```

Concept types and directories are **your choice**. The dirs above are a starting menu, not a requirement. `references/` conventionally mirrors external material, run instructions, or attester code; `computations/` holds Attested Computations.

## Frontmatter fields

| Field | Status | Notes |
|-------|--------|-------|
| `type` | **REQUIRED** | e.g. `BigQuery Table`, `Metric`, `Runbook`, `API Endpoint`, `Dataset`, `Attested Computation`. Free-form. |
| `title` | recommended | human-readable name |
| `description` | recommended | single sentence; feeds indexes and previews |
| `resource` | recommended | URI of the real asset; omit for abstract concepts |
| `tags` | recommended | YAML list |
| `generated` | trust | `{ by: <actor>, at: <datetime> }`; `by` required within it. Replaces v0.1 `timestamp`. |
| `verified` | trust | list of `{ by, at }` confirmation events (a bare mapping = one entry) |
| `status` | lifecycle | `draft` \| `stable` (default) \| `deprecated` |
| `stale_after` | lifecycle | absolute datetime; stale when `now >= stale_after` |
| `sources` | provenance | list of `{ id, resource (required), title, author, usage_count, last_modified }`; `usage_window: { from, to }` as a sibling frames any `usage_count` |
| `runtime`, `parameters`, `computation`, `executor`, `attester` | Attested Computation only | `runtime` required for that type |
| custom keys | optional | freely add; consumers must tolerate them |

**Every datetime is ISO 8601 with an explicit offset**, e.g. `2026-09-04T14:30:00Z`. **Actors** are `<producer>/<version>` for agents and tools (`claude-code/fable-5.1`), `human:<id>` for people, `process:<id>` for automation. Use `human:` only for content a person wrote or confirmed; trust tiers key off it (no `verified` = unverified; non-human verifiers = machine-confirmed; any `human:` verifier = human-reviewed).

Concept body: use headings/tables/lists. Conventional headings when applicable: `# Schema`, `# Examples`, `# Computation`. Attribute a specific claim with a footnote whose label is a `sources[].id` (`...sharded daily.[^ga4-schema]` plus `[^ga4-schema]: GA4 export schema`). Link related concepts with **bundle-relative** links starting `/` (e.g. `[customers](/tables/customers.md)`).

## Concept template

```markdown
---
type: BigQuery Table
title: Orders
description: One row per completed customer order.
resource: https://console.cloud.google.com/bigquery?...&t=orders
tags: [sales, revenue]
generated: { by: claude-code/fable-5.1, at: 2026-09-04T14:30:00Z }
verified: { by: human:jane.doe, at: 2026-09-04T15:00:00Z }
status: stable
sources:
  - id: orders-ddl
    resource: /references/orders-ddl.md
    title: orders table DDL from migrations/0003_orders.sql
---
# Schema
| Column | Type | Description |
|--------|------|-------------|
| `order_id` | STRING | Unique order id. |
| `customer_id` | STRING | FK to [customers](/tables/customers.md). |

# Joins
Joined with [customers](/tables/customers.md) on `customer_id`.[^orders-ddl]

[^orders-ddl]: orders table DDL
```

Set `generated.by` to yourself as an agent actor when you write the file. Add a `verified` entry only when someone actually checked the content against its source; never add `human:` verification on a person's behalf. Add `sources` whenever you derived the content from a file, doc, or URL you can name.

## Attested Computation (when a number must be reproducible)

When a metric or figure has one sanctioned formula (SQL, dbt, Python), put the formula in its own concept and link to it from the metric:

```markdown
---
type: Attested Computation
title: Revenue for fiscal year
description: Recognized revenue for a fiscal year, per Finance's definition.
runtime: bigquery
parameters:
  - { name: year, type: integer, required: true }
executor: { resource: /references/skills/run-on-bq.md, receipt: [job_id, executed_sql, result] }
attester: { resource: /references/attesters/sql_equality.py }
generated: { by: claude-code/fable-5.1, at: 2026-09-04T14:30:00Z }
stale_after: 2026-12-31T00:00:00Z
---
# Computation
    SELECT SUM(amount) AS revenue FROM finance.recognized_revenue WHERE fiscal_year = @year
```

Agents may only fill declared `parameters`; they must never edit the computation. A long computation can live in a file named by `computation:` instead of the body fence. Skip this type entirely when no formula needs guarding.

## Organizing a project into OKF

1. **Inventory the real knowledge.** Read the repo's README, CLAUDE.md, schema/migrations, `package.json`/configs, docs, env templates, and any data dictionaries. List the actual datasets, tables, metrics, runbooks, playbooks, APIs.
2. **Scaffold.** Run `scaffold_okf.sh <project-dir>` to create `<project>/okf/` with type-dir indexes and a root index declaring `okf_version: "0.2"`. Delete type dirs that don't apply; add ones that do.
3. **Seed real concepts.** Write one file per concept you can verify from the repo, each with `generated: { by, at }` and `sources` naming what you read. **Never invent facts.** Where a concept clearly exists but you lack ground truth (exact columns, formula), create the file with `type` + `title` + `description`, `status: draft`, and a `> TODO:` note in the body. A conformant stub is fine; a fabricated schema is not.
4. **Cross-link.** Connect related concepts with bundle-relative links (table to dataset, metric to table, metric to computation, runbook to api).
5. **Write indexes.** Each dir gets an `index.md` of `* [Title](url) - description` lines (no frontmatter); the root `index.md` carries the `okf_version` frontmatter block.
6. **Log.** Add a `## YYYY-MM-DD` entry to `log.md`, newest first.
7. **Validate.** Run `python3 validate_okf.py <project>/okf` (add `--strict` to fail on warnings, `--quiet-info` to hide hints). Fix all ERRORs; read every WARN.

## Migrating a v0.1 bundle

Symptoms: root `index.md` says `okf_version: "0.1"` in its body, concepts carry `timestamp:`, or bodies end in a `# Citations` list. The validator flags all three.

1. Decide the actor for `generated.by`: `human:<id>` if a person wrote the concepts, otherwise the agent that did (`claude-code/<model>`). Be honest; consumers derive trust from it.
2. `python3 migrate_okf.py <project>/okf --by <actor> --dry-run`, read the plan.
3. Rerun without `--dry-run`. It rewrites `timestamp` to `generated.at`, turns pure-link `# Citations` lists into `sources` entries plus footnote definitions, moves `okf_version` into root-index frontmatter as `"0.2"`, and appends a `**Migration**` log entry. Mixed-content citation sections are reported for manual conversion.
4. `python3 validate_okf.py <project>/okf`, then commit.

## Intake questions (new or existing projects)

Ask these during project init/planning so knowledge maps cleanly to OKF (don't ask all; pick what's unanswered):

1. What are the **data sources / datasets** this project reads or writes?
2. What **tables / collections / schemas** matter, and how do they relate (joins, FKs)?
3. What **metrics / KPIs** are defined, and what are their exact formulas? (Formulas that must be reproducible become Attested Computations.)
4. What **operational runbooks** exist (deploy, migrate, on-call, incident)?
5. What **playbooks / decision guides** drive judgment calls?
6. What **APIs / integrations / services** does it expose or depend on?
7. What **external authorities** should concepts cite (`resource` and `sources` links)?
8. Who **produces** vs **consumes** this knowledge (humans, agents, pipelines)? Who is allowed to mark a concept `verified`?

Capture answers directly as OKF concept files (or stubs) rather than prose notes.

## Conformance checklist

- [ ] Bundle is a directory tree of `.md` files.
- [ ] Every non-reserved `.md` has a `--- … ---` frontmatter block with a **non-empty `type`**.
- [ ] Non-root `index.md` files contain **no** frontmatter; the root one carries only `okf_version: "0.2"`.
- [ ] Every concept has `generated: { by, at }`; no `timestamp` fields remain.
- [ ] Every datetime is ISO 8601 with an explicit offset; every `by` follows the actor convention.
- [ ] Footnote labels match a `sources[].id`; no `# Citations` body lists remain.
- [ ] Cross-links are bundle-relative (`/…`) where possible.
- [ ] `validate_okf.py` reports **CONFORMANT** (no ERRORs) and you have read the WARNs.

## Common mistakes

| Mistake | Fix |
|---------|-----|
| Inventing schemas/metrics you can't verify | Write a conformant stub with `status: draft` and `> TODO:`; never fabricate. |
| Still writing `timestamp:` | Use `generated: { by: <actor>, at: <datetime> }`; run `migrate_okf.py` on old bundles. |
| Marking `verified` with `human:<id>` because you assume the user agrees | Only record verification that actually happened; agent checks use an agent or `process:` actor. |
| Datetime without an offset (`2026-09-04`) | Every timestamp needs a time and offset: `2026-09-04T00:00:00Z`. |
| Citations as a body list | Put them in `sources` (with `id`) and cite claims with `[^id]` footnotes. |
| Putting frontmatter in a non-root `index.md` | Only the bundle-root index may carry frontmatter, and only `okf_version`. |
| One giant doc | One concept per file; link them. One Attested Computation per figure. |
| Relative-only links that break on move | Prefer bundle-relative links starting `/`. |
| Treating type dirs as fixed | Types are free-form; use what fits the project. |
| Letting an agent rewrite a sanctioned formula | The computation is the contract; agents supply parameter values only. |

## Tools (in this skill dir)

- `scaffold_okf.sh <project-dir> [bundle-name]`: create the v0.2 bundle skeleton (refuses to overwrite).
- `validate_okf.py <bundle> [--strict] [--quiet-info]`: check §11 conformance plus §5 to §10 hygiene (uses PyYAML when present, degrades gracefully without it).
- `migrate_okf.py <bundle> --by <actor> [--dry-run] [--no-citations]`: upgrade a v0.1 bundle in place.
- `okf-spec-reference.md`: condensed OKF v0.2 normative rules.

## Sources
- [OKF spec (SPEC.md), GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
- [Sample bundles, including acme_retail which exercises every v0.2 family](https://github.com/GoogleCloudPlatform/open-knowledge-format/tree/main/bundles)
- [Google Cloud Blog: How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/)
