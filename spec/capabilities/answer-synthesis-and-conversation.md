# Capability: Answer Synthesis & Conversation

## What It Does

Turns a successful aggregate result into a plain-language answer with key numbers, remembers the running conversation for this sitting so follow-up questions have context, estimates the approximate cost of answering, and records every question/answer to a local log.

## Inputs

| Input | Type | Source | Required |
|-------|------|--------|----------|
| Aggregate result (on success) OR give-up signal (on retry exhaustion) | structured data / status | Iterative Code Execution | Yes |
| Original question | text | User | Yes |
| Prior conversation turns (this sitting) | list of question/answer text pairs | This capability's own running session memory | No — empty for the first question |
| LLM usage for the question | token counts | Iterative Code Execution's and this capability's own LLM calls | Yes |

## Outputs

| Output | Type | Destination |
|--------|------|-------------|
| Plain-language answer | text | Returned to the user (chat thread) |
| Updated conversation history | list of question/answer text pairs | Kept for the rest of this sitting; used by the next question |
| Approximate cost estimate | currency amount (USD) | Returned to the user, displayed alongside the answer |
| Log entry | one structured record per question | Appended to a local log file |

## External Calls

| System | Operation | On Failure |
|--------|-----------|------------|
| Gemini API | Turn the aggregate result into a plain-language answer | Treated as fatal for this one question — the user sees a clear, generic error, never a silently invented answer |

## Business Rules

- On retry exhaustion (no successful result), the output is ONLY a plain apology/failure message — no code, no partial numbers, no hint of the failed attempts.
- On success, the answer must be grounded in the actual computed numbers from the aggregate result — it is not permitted to invent figures that aren't present in that result.
- Conversation memory is scoped to the current sitting only: it resets whenever a new file is uploaded and is gone entirely if the server restarts — never persisted across days.
- A follow-up question is answered with awareness of the prior question(s) and answer(s) in the same sitting, so the user does not have to re-state context already given.
- The cost estimate is explicitly approximate (labeled as such wherever shown) — exact billing-accuracy is not required.
- Every question asked — whether it succeeds, gives up, or hits an infrastructure error — produces exactly one new entry in the local log, so the user always has a plain record of what was asked and what happened, without needing a full audit-trail system.

## Success Criteria

- [ ] A successful aggregate result produces an answer that contains at least one of the actual computed numbers from that result.
- [ ] A follow-up question that only makes sense in light of a prior answer in the same sitting (e.g. "and just for the top category?") is answered using that prior context, not as if it were the first question ever asked.
- [ ] A retries-exhausted question returns a plain apology/failure message with no code and no fabricated numbers.
- [ ] Every question asked during a sitting produces exactly one corresponding new line in the local log file.
- [ ] A successful question's log entry and displayed cost estimate are both positive, non-zero values; a failed question's log entry still records the attempt (with its own cost, if any Gemini calls were made).

> **Assumed:** Conversation memory (using prior turns to inform new answers) is real starting Phase 2, not Phase 1 — see `spec/roadmap.md` and the `> Assumed:` note in `spec/ui.md` for the explicit reasoning (Phase 1's gate only requires one question to be answered correctly; wiring history is grouped with the other Phase 2 capabilities so it lands as a coherent, testable unit rather than a rushed half-feature in Phase 1).
