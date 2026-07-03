# Capability: Result Presentation

## What It Does

Renders the outcome of a question as plain-language text, a collapsible view of the exact analysis code that produced it (successful answers only), an interactive chart when the result shape supports one, and a summary table of the aggregate result.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Final answer text | text | Answer Synthesis & Conversation | Yes |
| Working analysis code | text | Iterative Code Execution (success only) | No — absent on a failed/gave-up question |
| Aggregate result | structured data | Iterative Code Execution (success only) | No — absent on a failed/gave-up question |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Rendered chat message | UI element | Browser — answer text, collapsible code toggle |
| Chart | UI element | Browser — only rendered when the result shape supports it |
| Summary table | UI element | Browser — the aggregate result rows/columns |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| None | Chart/table are derived purely from the already-computed aggregate result; no external or LLM call is made to render them | N/A |

## Business Rules

- The analysis code is shown, collapsed by default, ONLY alongside a successful answer — never alongside a failure/apology message, and never expanded automatically (the plain answer is the primary content; the code is a supporting detail the user opts into).
- Chart and table content is derived strictly from the already-computed aggregate result — never from the raw uploaded file directly, and never re-fetched or re-computed for display.
- When the aggregate result's shape doesn't support a meaningful chart (e.g. it's a single number), no chart placeholder is shown as if it were real — the answer and/or table stand alone rather than displaying an empty or misleading chart.
- The mapping from a result's shape to a chart type is a fixed, predictable rule (e.g. one category column + one numeric column → bar chart; a time-ordered column + one numeric column → line chart; a single value → no chart, table/text only) — never an arbitrary or surprising choice.

## Success Criteria

- [ ] Every successful answer shows a collapsed "view code" affordance that expands to the exact code that produced the answer.
- [ ] A failed/gave-up answer shows no code affordance and no chart/table.
- [ ] A result shaped as category → value pairs renders as a chart with the correct data points.
- [ ] A single-scalar result renders no chart component (text/table only) — no empty or placeholder chart is shown as if functional.
