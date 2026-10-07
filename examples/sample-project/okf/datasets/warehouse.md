---
type: Dataset
title: Analytics warehouse
description: The Postgres schema the nightly ETL loads for reporting.
resource: postgres://analytics.internal/warehouse
tags: [analytics, postgres]
generated: { by: claude-code/example, at: 2026-10-06T00:00:00Z }
status: stable
sources:
  - id: etl-readme
    resource: /references/etl-readme.md
    title: README of the etl/ package
---
# Contents
Tables loaded nightly by `etl/run.py`.[^etl-readme] Start with [orders](/tables/orders.md).

[^etl-readme]: README of the etl/ package
