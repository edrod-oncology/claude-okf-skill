---
type: Table
title: orders
description: One row per completed customer order.
tags: [sales]
generated: { by: claude-code/example, at: 2026-10-06T00:00:00Z }
status: stable
sources:
  - id: orders-ddl
    resource: /references/orders-ddl.md
    title: migrations/0003_orders.sql
---
# Schema
| Column | Type | Description |
|---|---|---|
| `order_id` | text | Primary key. |
| `customer_id` | text | Customer identifier. |
| `amount` | numeric | Paid amount in USD. |
| `placed_at` | timestamptz | When the order was placed. |

Part of the [analytics warehouse](/datasets/warehouse.md).[^orders-ddl]

[^orders-ddl]: migrations/0003_orders.sql
