---
type: Metric
title: Revenue
description: Sum of paid order amounts in a period.
tags: [sales, finance]
generated: { by: claude-code/example, at: 2026-10-06T00:00:00Z }
status: draft
---
# Definition
`SUM(amount)` over [orders](/tables/orders.md) where `placed_at` falls in the period.

> TODO: confirm with Finance whether refunds are netted out. Do not guess; the formula is a draft until confirmed.
