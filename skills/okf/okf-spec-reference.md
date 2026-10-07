# OKF v0.2: Normative Reference

Open Knowledge Format (OKF), published by Google Cloud in the dedicated repo
`GoogleCloudPlatform/open-knowledge-format`, specification version **0.2**
(July 2026; timestamp rule tightened August 21, 2026). This file restates the
normative rules in condensed form. Load it only when you need exact
conformance details; the day-to-day workflow lives in `SKILL.md`. Section
numbers (§) match upstream `SPEC.md`.

OKF represents knowledge as **plain markdown files with YAML frontmatter** in
a directory tree, readable by humans and consumable by agents with no SDK, no
runtime, and no translation layer. v0.2 adds first-class **provenance, trust,
lifecycle, and attestation** so a corpus that agents keep rewriting stays
trustable.

## §2 Terminology

- **Bundle**: a self-contained directory tree of knowledge documents; the unit of distribution.
- **Concept**: one unit of knowledge, one markdown file. **Concept ID** = file path minus `.md`.
- **Source**: material a concept derives from, recorded in `sources`. **Provenance** = the set of sources.
- **Credibility signal**: an objective per-source fact (`author`, `usage_count`, `last_modified`). OKF records signals, never a score.
- **Actor**: `<producer>/<version>` (agent/tool), `human:<id>`, or `process:<id>` (§7).
- **Trust tier**: derived from `verified`: unverified, machine-confirmed, human-reviewed (§5.3).
- **Attested Computation**: a concept carrying a sanctioned way to compute a value (§10). **Executor** runs it and returns a **receipt**; a deterministic **attester** checks the receipt. Receipts are runtime artifacts, never stored in the bundle.

## §3 Bundle structure

- A bundle is a directory tree of markdown files; layout is the producer's choice.
- Distributed as a git repo (recommended), a tarball/zip, or a subdirectory of a larger repo (e.g. `myproject/okf/`).
- **Reserved filenames** at any level, never used for concepts: `index.md` (§8) and `log.md` (§9). Every other `.md` is a concept.
- Tags are expressed only via the `tags` field; there is no tag-file format. Consumers may synthesize tag views.

## §4 Concept documents

Each concept is a UTF-8 markdown file: a `---`-delimited YAML frontmatter block, then a markdown body (may be empty).

**Required:** `type`. A short descriptive string (`BigQuery Table`, `Metric`, `Runbook`, `API Endpoint`, `Playbook`, `Reference`, `Attested Computation`). Not centrally registered. Consumers MUST tolerate unknown types. A concept carrying only `type` is fully conformant.

**Recommended:** `title` (else consumers may derive from filename), `description` (one sentence; feeds indexes and previews), `resource` (URI of the underlying asset; absent for abstract concepts), `tags` (YAML list).

**Optional families:** provenance, trust, lifecycle (§5); computation keys for Attested Computations (§10).

**Extensions:** producers MAY add any keys; consumers SHOULD preserve them and MUST NOT reject unknown ones.

**Body (§4.2):** standard markdown; favor structure (headings, lists, tables, fences). No required sections. Conventional headings: `# Schema` (fields/columns), `# Examples`, `# Computation` (§10). Per-claim attribution uses footnotes keyed to `sources[].id`, not a body citations list.

## §5 Provenance, trust, lifecycle

All optional. Absence is meaningful (unverified is distinguishable from verified) but never grounds for rejection. **Every timestamp-valued key is an ISO 8601 datetime with an explicit UTC offset**, e.g. `2026-06-30T14:00:00Z`.

### §5.1 Provenance: `sources`

```yaml
sources:
  - id: ga4-schema                     # optional; SHOULD exist when the body cites it
    resource: https://developers.google.com/analytics/bigquery/export-schema   # REQUIRED
    title: GA4 BigQuery Export schema  # optional
    author: team:ga4-docs              # credibility signal (actor convention)
    usage_count: 5000                  # credibility signal (int, framed by usage_window)
    last_modified: 2026-05-30T00:00:00Z   # credibility signal (when the SOURCE changed)
usage_window: { from: 2026-06-01T00:00:00Z, to: 2026-06-30T00:00:00Z }   # sibling of sources
```

- `resource` names a followable artifact (absolute URL, bundle-relative path, or path into `references/`) **or** a scope descriptor that cannot be followed (e.g. `all queries in BigQuery project X`).
- `usage_count` counts exercises of the resource over `usage_window` (shared sibling; an entry MAY carry its own to override). Read it as liveness and trend, not as a score.
- `last_modified` is when the source changed; `generated.at` is when the concept was written. Keep them distinct.
- Lineage is expressed through links: when `resource` points at another concept, consumers MAY recurse into that concept's `sources`. External `derived_from` and data lineage are out of scope for v0.2.
- **Per-claim attribution:** a markdown footnote whose label is a `sources[].id`:
  `sharded daily as events_YYYYMMDD.[^ga4-schema]` ... `[^ga4-schema]: GA4 BigQuery Export schema`. The label is the join key; keyed labels survive reordering, positional indexes do not.

### §5.2 Trust: `generated` and `verified`

```yaml
generated: { by: reference_agent/gemini-2.5-pro, at: 2026-06-20T22:53:05Z }
verified:
  - { by: human:ahormati, at: 2026-06-25T09:00:00Z }
  - { by: process:finance-nightly, at: 2026-06-26T02:00:00Z }
```

- `generated.by` is REQUIRED within `generated` (an actor). `generated.at` marks the content's last meaningful change.
- `verified` is a list of `{ by, at }` events; independent checks accumulate; "how recently" is the latest `at`. A bare `{ by, at }` mapping is allowed and MUST be read as a one-element list.
- Who wrote (`generated`) and who confirmed (`verified`) are deliberately separate.

### §5.3 Trust tiers (derived, advisory, not access control)

| `verified` state | Tier |
|---|---|
| absent | unverified |
| only non-`human:` actors | machine-confirmed |
| any `human:<id>` actor | human-reviewed |

### §5.4 `status`

`draft` (not yet reviewed, possibly incomplete) | `stable` (default when absent) | `deprecated` (kept for links and history; no longer current).

### §5.5 `stale_after`

An absolute instant; the concept is stale when `now >= stale_after`. Absolute, not a TTL, so staleness is a plain comparison.

## §6 Cross-linking and paths

- **Bundle-relative (absolute)** links begin with `/` and resolve from the bundle root. RECOMMENDED: stable when files move within a subdirectory. Example: `[customers](/tables/customers.md)`.
- **Relative** links are ordinary markdown paths: `[other](./other.md)`, `[rev](../computations/revenue.md)`.
- A link asserts an untyped directed relationship; the kind (joins-with, depends-on) comes from surrounding prose.
- Consumers MUST tolerate broken links (not-yet-written knowledge is legitimate).
- **Path-valued fields** (`resource`, `sources[].resource`, `computation`, `executor.resource`, `attester.resource`) accept an absolute URL, a bundle-relative `/path`, or a relative path.
- **`references/` convention (§6.3):** mirrors external material, run instructions, or code as first-class concepts (e.g. `references/attesters/revenue.py`). A convention, not a requirement.

## §7 Actor convention

`generated.by`, `verified[].by`, and `sources[].author` use one convention: `<producer>/<version>` for agents and tools (`reference_agent/gemini-2.5-pro`, `claude-code/fable-5.1`), `human:<id>` for a person, `process:<id>` for automation. Trust classification keys off the `human:` prefix, so producers MUST use it for hand-authored or human-confirmed content.

## §8 Index files

- `index.md` MAY appear in any directory for **progressive disclosure**.
- Contains **no frontmatter**, with one exception: the bundle-root `index.md` MAY carry a frontmatter block holding `okf_version` (§12).
- Body: one or more section headings, each with `* [Title](relative-url) - description` bullets. Entries SHOULD reuse the concept's `description`. Subdirectories may be listed as `* [Subdirectory](subdir/) - description`.
- Producers MAY generate indexes; consumers MAY synthesize them when absent.

## §9 Log files

- `log.md` MAY appear at any level; records change history for that scope.
- Flat, date-grouped, **newest first**; date headings MUST be ISO `YYYY-MM-DD` (`## 2026-05-22`).
- Entries are prose bullets; a leading bold word (`**Update**`, `**Creation**`, `**Deprecation**`) is a convention, not a requirement.

## §10 Attested Computation

A standalone concept with `type: Attested Computation` carrying a sanctioned computation. Concepts that need the value (a `Metric`, a table) link to it with a normal markdown link. One computation, many consumers; trust state (`verified`, `stale_after`, `attester`) is per computation.

**Contract fields (top-level frontmatter, alongside the §5 families):**

| Field | Status | Meaning |
|---|---|---|
| `runtime` | REQUIRED for this type | How to run it and what `parameters` mean: `bigquery`, `postgres`, `dbt`, `python`, `Looker`, ... |
| `parameters` | optional | List of `{ name, type, required }`; the only holes an agent may fill |
| `computation` | optional | Path to a file holding the computation; absent means the body `# Computation` fence is the computation |
| `executor` | optional | `resource` (run instructions or code) and `receipt` (list of fields a run must return, e.g. `[job_id, executed_sql, result]`) |
| `attester` | optional | `resource`: deterministic, no-LLM code that takes a receipt and returns a verdict; runs consumer-side |

**Rules:** the agent MAY only supply parameter values; it MUST NOT author or edit the computation. Binding parameters into the executable artifact is the consumer's job; the attester re-derives the same binding and compares against what actually ran (`executed_sql`, `compiled_sql`), so a rewritten query or swapped file fails.

**Consumer flow (informative, §10.5):** discover by type, load contract + computation, parameterize, execute (get receipt), attest (provenance: sanctioned computation ran; fidelity: displayed value matches the receipt's source), gate (refuse failing attestation; warn or refuse when `now >= stale_after`).

**Verification vs attestation (§10.6):** `verified` confirms the *definition* still matches policy (doc-level, slow, in the bundle). Attestation confirms a single *run* produced the value the sanctioned way (per call, runtime, not stored). Both are needed.

## §11 Conformance

A bundle is conformant with v0.2 iff:
1. every non-reserved `.md` has a parseable YAML frontmatter block;
2. every frontmatter block has a non-empty `type`;
3. reserved files (`index.md`, `log.md`) follow §8 and §9 when present.

When the optional families are present, producers SHOULD follow §5 through §10, and consumers MUST treat a bare `verified` mapping as a one-element list, MUST NOT reject a concept for missing any optional family, and SHOULD surface (not drop) a failing attestation.

Consumers MUST NOT reject a bundle for: missing optional fields, unknown `type` values, unknown extra keys, broken cross-links, or missing `index.md` files.

## §12 Versioning

`<major>.<minor>`. Minor = backward-compatible additions; major = breaking changes. Bundles MAY declare `okf_version: "0.2"` in a frontmatter block of the bundle-root `index.md` (the only place an index may carry frontmatter). Consumers SHOULD attempt best-effort consumption of unknown versions.

Deferred to a future revision: receipt/verdict wire formats and the attestation lifecycle, attester ABI and sandboxing, attestation caching, semantic-layer templates (Looker, dbt).

## §13 Changes from v0.1

**Breaking (two):**
- `timestamp` is superseded by `generated: { by, at }`. Consumers MAY fall back to `timestamp` when `generated` is absent.
- The body `# Citations` list is superseded by `sources` frontmatter (with footnote attribution). Consumers MAY still parse a legacy `# Citations` list.

**Additive:** `sources` (+ `author`, `usage_count`, `last_modified`, `usage_window`), `generated`, `verified`, `status`, `stale_after`; the `Attested Computation` type with `runtime`, `parameters`, `computation`, `executor`, `attester`; the `# Computation` heading; the actor convention.

Everything else (bundle structure, reserved filenames, required `type`, recommended fields, links, indexes, logs, permissive conformance) is unchanged. `migrate_okf.py` in this skill applies the two breaking changes mechanically.

## Sources
- [Open Knowledge Format spec (SPEC.md), GoogleCloudPlatform/open-knowledge-format](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
- [Sample bundles (acme_retail exercises every v0.2 family)](https://github.com/GoogleCloudPlatform/open-knowledge-format/tree/main/bundles)
- [Frozen v0.1-era snapshot (no longer maintained), GoogleCloudPlatform/knowledge-catalog/okf](https://github.com/GoogleCloudPlatform/knowledge-catalog/tree/main/okf)
- [Google Cloud Blog: How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/)
