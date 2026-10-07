# claude-okf-skill

A Claude Code skill that keeps a project's knowledge (datasets, tables, metrics, runbooks, playbooks, APIs) in Google's [Open Knowledge Format](https://github.com/GoogleCloudPlatform/open-knowledge-format) v0.2, plus a commit hook that refuses to let the code and the knowledge drift apart.

OKF is plain markdown with YAML frontmatter, one concept per file, in a directory tree that lives in git next to the code. No SDK, no runtime, no translation layer. The same files are readable by a person and consumable by an agent. v0.2 adds provenance (`sources`), trust (`generated`, `verified`), lifecycle (`status`, `stale_after`) and attested computations, so a corpus that agents keep rewriting stays trustable.

This repo contains:

- **`skills/okf/`**: the skill. `SKILL.md` tells Claude when and how to build, extend, validate and migrate an `okf/` bundle, and which intake questions to ask when a project starts. It ships three tools:
  - `scaffold_okf.sh <project-dir>`: creates a conformant empty bundle.
  - `validate_okf.py <bundle> [--strict] [--quiet-info]`: checks spec section 11 conformance and sections 5 through 10 hygiene. Degrades gracefully without PyYAML.
  - `migrate_okf.py <bundle> --by <actor> [--dry-run]`: upgrades a v0.1 bundle in place (`timestamp` to `generated`, `# Citations` lists to `sources` plus footnotes, `okf_version` into root-index frontmatter).
  - `okf-spec-reference.md`: condensed normative rules, loaded only when exact conformance details are needed.
- **`hooks/okf-commit-gate.py`**: a `PreToolUse` hook on `Bash`. When Claude runs `git commit`, the hook blocks if the staged changes imply a knowledge concept is now stale and no `okf/` file is staged with them, and blocks if the staged bundle does not validate. Exit code 2 feeds the reason back to Claude, which then fixes the bundle and commits again.

## Requirements

- Claude Code with hooks and user-level skills (`~/.claude/skills/`).
- bash, git, python3 3.9 or later.
- PyYAML (`pip install pyyaml`) is optional. Without it the validator uses a reduced frontmatter parser and says so.

## Install

```bash
git clone https://github.com/edrod-oncology/claude-okf-skill.git
cd claude-okf-skill
./install.sh            # skill + hook
./install.sh --no-hook  # skill only
```

If the clone lost its executable bits, run `bash install.sh` instead.

The installer copies `skills/okf/` to `~/.claude/skills/okf/`, copies the hook to `~/.claude/hooks/okf-commit-gate.py`, and merges one `PreToolUse` entry into `~/.claude/settings.json` (backup taken first, existing hooks untouched, safe to rerun). Open `/hooks` in a running session, or restart Claude Code, to load it. Set `CLAUDE_HOME` to install somewhere other than `~/.claude`.

`./uninstall.sh` reverses all of it. Project `okf/` bundles are never touched; they belong to each repo.

To install by hand instead, copy the two directories and add this to `settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "python3 /home/you/.claude/hooks/okf-commit-gate.py", "timeout": 30 }
        ]
      }
    ]
  }
}
```

## Use

| You want | Do |
|---|---|
| Start a project with knowledge captured from day one | Ask Claude to plan or init the project. The skill adds eight intake questions (datasets, tables, metrics, runbooks, playbooks, APIs, authorities, producers vs consumers) and writes answers as concept files. |
| Organize an existing project | "Organize this project's knowledge in OKF." Claude inventories the repo, scaffolds `okf/`, seeds concepts it can verify, stubs the rest with `status: draft` and a `> TODO:` body, cross-links, writes indexes, logs, validates. |
| Check a bundle | `python3 ~/.claude/skills/okf/validate_okf.py path/to/okf --strict` |
| Upgrade a v0.1 bundle | `python3 ~/.claude/skills/okf/migrate_okf.py path/to/okf --by human:yourname --dry-run`, read the plan, rerun without `--dry-run`. |
| Commit a change that carries no new knowledge | Add `[okf-skip]` to the commit command. The override is greppable on purpose. |
| Let a repo define its own gate rules | Ship `scripts/okf-gate.mjs` (or set `OKF_PROJECT_GATE` to another path, `.py` also works). The hook defers to it and uses its exit code. |

The skill triggers on phrases like "OKF", "Open Knowledge Format", "make this knowledge portable / agent-readable", "organize the project's documentation", and on a bundle that still declares `okf_version: "0.1"`.

## What the commit gate does, and does not, fire on

Most commits do not change what a project *knows*. A typo fix, a refactor, a test rename: none of those age the bundle. A gate that fires on changes it has no business firing on gets switched off, and then it protects nothing. So the hook fires only on paths that map to a concept type, and it names which concept is stale rather than saying "update the docs":

| Staged path matches | Implied stale concept | Reason given |
|---|---|---|
| `migrations/`, `drizzle/`, `schema/*.{ts,py,sql}`, `models.{ts,py}` | `tables` | schema or model changed |
| `index.ts`, `api/`, `routes/`, `endpoints/`, `openapi.{yaml,json}` | `apis` | an API surface or contract changed |
| `config.{ts,py,js}` | `metrics` | tunable configuration changed |
| `.github/workflows/`, `Dockerfile`, `docker-compose.yml`, `vercel.json`, `fly.toml`, `scripts/` | `runbooks` | CI, deployment or an operational script changed |
| `docs/**/*(spec|design|plan|record)*` | `references` | a spec, plan or record changed |

Ignored: `okf/` itself, `node_modules/`, lockfiles, `.gitignore`, `CHANGELOG`, `LICENSE`, images and PDFs. The hook also stands down when the repo has no `okf/` directory, when nothing is staged, and for any Bash command that is not `git commit`.

Edit `KNOWLEDGE_PATHS` and `IGNORED` in the hook to match your stack. Keep the bar at "this changes what the project knows"; do not lower it to "this changes a file".

## Example

`examples/sample-project/okf/` is a small conformant bundle (one dataset, one table, a draft metric with an honest `> TODO:`, a runbook, two mirrored references) that shows the shape without any real data. Validate it with `python3 skills/okf/validate_okf.py examples/sample-project/okf --strict`.

## Verify

```bash
bash tests/smoke.sh
```

The smoke test scaffolds a bundle, checks that the validator rejects a missing `type` and accepts a well-formed concept, migrates a v0.1 bundle, then drives the hook through its block, allow, opt-out, invalid-bundle and no-bundle paths in a throwaway git repo. Fifteen checks, no network.

## Design notes

- **Never fabricate.** The skill and the gate both say it: where the ground truth is not known, a conformant stub with `status: draft` and `> TODO:` is correct; an invented schema is not. Agents are good at filling gaps with plausible text, and provenance fields are worthless if the content under them was guessed.
- **Trust comes from actors.** `generated.by` and `verified.by` use `<producer>/<version>` for agents, `human:<id>` for people, `process:<id>` for automation. The skill forbids recording `human:` verification on a person's behalf.
- **The gate names the concept, not the chore.** "okf/tables/ is stale because migrations/ changed" is actionable; "update the docs" is not.
- **The opt-out is greppable.** `[okf-skip]` in the commit command is the same bargain as an eslint-disable: visible to any reviewer who wants to see how often it was used.

## Sources

- [OKF specification (SPEC.md)](https://github.com/GoogleCloudPlatform/open-knowledge-format/blob/main/SPEC.md)
- [Sample bundles, including `acme_retail`](https://github.com/GoogleCloudPlatform/open-knowledge-format/tree/main/bundles)
- [Google Cloud blog: How the Open Knowledge Format can improve data sharing](https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/)
- [Claude Code hooks reference](https://code.claude.com/docs/en/hooks)

## License

MIT. OKF itself is a Google Cloud specification; this repo is an independent implementation of a skill and hook around it and is not affiliated with Google.
