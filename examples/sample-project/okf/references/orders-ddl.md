---
type: Reference
title: orders DDL
description: Mirrored DDL from migrations/0003_orders.sql.
generated: { by: claude-code/example, at: 2026-10-06T00:00:00Z }
tags: [reference, ddl]
---
    create table orders (order_id text primary key, customer_id text, amount numeric, placed_at timestamptz);
