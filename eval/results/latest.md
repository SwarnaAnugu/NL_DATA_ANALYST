## Answerable questions (execution accuracy vs gold SQL)

| Variant | Correct | **Silent wrong answers** | Abstained | Caveat correct | Median latency |
|---|---|---|---|---|---|
| naive | 62/74 (84%) | 12/74 (16%) | 0/74 (0%) | 58/64 (91%) | 1.5s |
| notes | 72/74 (97%) | 2/74 (3%) | 0/74 (0%) | 58/64 (91%) | 1.4s |
| full | 70/74 (95%) | 2/74 (3%) | 2/74 (3%) | 60/62 (97%) | 4.8s |

'Silent wrong answers' is the hallucination metric: the system returned a confident number that does not match the gold answer. 'Abstained' means it asked a question or failed visibly instead.

## Accuracy by question group

| Group | naive | notes | full |
|---|---|---|---|
| join | 16/20 | 20/20 | 20/20 |
| landmine | 6/6 | 6/6 | 4/6 |
| simple | 26/28 | 28/28 | 28/28 |
| time | 8/12 | 12/12 | 12/12 |
| trap | 6/8 | 6/8 | 6/8 |

## Non-answer behaviour (clarify / out of scope / refuse writes)

| Variant | Handled correctly |
|---|---|
| naive | 2/18 (11%) |
| notes | 2/18 (11%) |
| full | 18/18 (100%) |

Full pipeline: first-try rate 100%, needed one repair 0%.

## Full-pipeline failures to investigate

- **p03** (wrong_answer): How many distinct customers placed an order that was delivered?
  - status: success; SQL: `SELECT COUNT(DISTINCT c.customer_unique_id)
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL`
- **p03** (wrong_answer): How many distinct customers placed an order that was delivered?
  - status: success; SQL: `SELECT COUNT(DISTINCT c.customer_unique_id)
FROM orders o
JOIN customers c ON o.customer_id = c.customer_id
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL`