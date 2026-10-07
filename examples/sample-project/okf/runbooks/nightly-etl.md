---
type: Runbook
title: Nightly ETL
description: How the warehouse load runs and what to do when it fails.
tags: [operations]
generated: { by: claude-code/example, at: 2026-10-06T00:00:00Z }
status: stable
---
# Schedule
`etl/run.py` runs at 02:00 UTC from the `nightly` GitHub Actions workflow.

# On failure
1. Read the workflow log.
2. Re-run with `python etl/run.py --since <date>`.
3. Record the incident in [log.md](/log.md).
