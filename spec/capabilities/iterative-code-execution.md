# Capability: Iterative Code Execution

## What It Does

For a single plain-English question about the uploaded file, iteratively generates analysis code, runs it against the real, complete dataset, checks whether the result is usable, and retries with a different approach on failure — up to a configurable limit — instead of ever answering from a single untested attempt.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Question | text | User, via the chat input | Yes |
| Schema/summary profile | structured data | Produced by File Ingestion for the active session | Yes |
| Prior conversation turns | list of question/answer text pairs | Session's running history (see Answer Synthesis & Conversation) | No — empty is valid |
| Retry limit | integer, configurable | System configuration | Yes (has a sensible default) |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Working analysis code (last successful attempt only) | text | Returned for display (Result Presentation) — only on success |
| Aggregate result | structured data (small — counts, sums, groupings, etc.) | Passed to Answer Synthesis & Conversation |
| Attempt count | integer | Logged (Answer Synthesis & Conversation's log capability) |
| Give-up signal | boolean/status | Passed to Answer Synthesis & Conversation, which then produces the plain failure message |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Generate a candidate analysis approach for the question | If Gemini itself is unreachable, this is a fatal error for the question (surfaced clearly); if Gemini merely returns code that fails to run, that is a normal, expected retry, not an error state |

## Business Rules

- The question is never answered from a single, unverified attempt: every candidate is actually executed against the real data before it is trusted.
- Analysis always runs against the complete uploaded dataset, never a truncated sample — a correct answer must reflect every row, not just the first few.
- The dataset itself is never sent to Gemini — only the schema/summary profile and the question (and, on a retry, the previous attempt's error) are used to ask for the next candidate.
- Execution happens in a way that isolates a runaway, hanging, or crashing analysis attempt so it cannot take down the whole agent or run indefinitely — a stuck attempt is treated as a failed attempt after a hard time limit, and the loop moves on.
- A result that looks like it contains raw data (e.g., far more values than a reasonable summary would have) is treated as an invalid attempt and retried with feedback — it is never passed along as if it were a valid answer.
- On exhausting the retry limit with no valid result, the capability stops and hands off a "no working answer" signal — it does not fabricate an answer, and the failed attempts along the way are not shown to the user (only the fact that it gave up).

## Success Criteria

- [ ] A well-formed, answerable question against a valid file succeeds, producing a working piece of code and a small aggregate result.
- [ ] A question that references something not present in the file (e.g. a non-existent column) triggers at least one retry with feedback from the failed attempt, and either self-corrects or cleanly gives up after the retry limit — it never crashes or hangs.
- [ ] Against a 1,000+ row fixture file engineered so a naive "first few rows" sample would produce a materially different number than the true full-dataset computation, the successful result matches the TRUE full-dataset computation — proving the analysis runs against the whole file, not a truncated sample.
- [ ] A simulated attempt that returns something shaped like raw data (not a small aggregate) is rejected and retried rather than accepted.
- [ ] The retry limit is configurable and is respected exactly — e.g., with the limit set to 1, the capability gives up after exactly one failed attempt, not zero and not two.
