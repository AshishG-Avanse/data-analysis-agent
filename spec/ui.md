# UI

---

## UI Type

Single-page web app (chat-style) — one screen: upload area + Q&A thread. No routing/multiple pages needed.

## Views / Screens

### Screen: Upload / Session Start

**Purpose:** Let the user pick or drop the one file they want to analyze for this sitting, and see confirmation that it parsed correctly before asking anything.

**Key elements:**
- Drag-and-drop area + a "browse" button (real, Phase 1)
- Post-upload readout: filename, row count, column count, column names/types (real, Phase 1)
- A warnings banner area for malformed/skipped content (Phase 1: present but never populated — the backend only returns `warnings: []`; Phase 2: real, shows actual skipped-row/sheet warnings). **Labelled in Phase 1** as "File warnings will appear here" placeholder styling so it is never mistaken for a bug when it stays empty.

**Actions available:**
- Upload a file (replaces any existing session)
- Proceed to the Q&A thread once a file is loaded

### Screen: Q&A Thread (Chat)

**Purpose:** Let the user ask any number of plain-English questions about the uploaded file in this sitting and see each answer.

**Key elements:**
- Text input + submit button for a new question (real, Phase 1)
- A spinner shown while a question is processing — no step counter, no token streaming (real, Phase 1, matching the product's explicit "just a spinner" requirement)
- Chat bubbles, one per question/answer pair, growing downward (real, Phase 1)
- Collapsible "View code" toggle on each successful answer, showing the exact analysis code that produced it (real, Phase 1) — never shown on a failed/gave-up answer
- Chart placeholder area under each answer (Phase 1: a clearly labelled static box, e.g. "Chart — coming in Phase 2", non-functional; Phase 2: a real interactive chart rendered from `chart_spec`)
- Summary table placeholder area under each answer (Phase 1: clearly labelled static placeholder; Phase 2: a real table rendered from the aggregate result)
- Cost badge next to each answer (Phase 1: a clearly labelled "Cost: -- (coming in Phase 2)" placeholder; Phase 2: the real approximate `cost_estimate_usd`)

**Actions available:**
- Submit a new question
- Expand/collapse the code view on any past answer
- Upload a new file (returns to the Upload screen, clears the thread — a new session)

## Error States

- **Upload rejected (unsupported type / unreadable file):** an inline error message under the upload area naming the problem (e.g. "Unsupported file type — please upload a CSV or Excel file.") — the user stays on the Upload screen and can try again immediately.
- **Question submission failure (fatal infra error):** the chat bubble for that question shows a clear, generic error message (e.g. "Something went wrong answering that — try again.") instead of a spinner or a fabricated answer; the input remains usable for the next question.
- **Gave up after retries:** rendered as a normal chat answer bubble with the plain apology text — not styled as an error, since it is an expected, graceful outcome, not a bug.
- **Loading:** the single spinner described above; no partial/streaming content is ever shown mid-question.
- **Network/server unreachable:** a top-level banner ("Can't reach the server — is it running?") rather than a silently stuck spinner.

## Tech Stack

Next.js 15 + React 19, static export (`output: 'export'`, `basePath: '/app'`) served by the FastAPI backend at `/app/` (already scaffolded — see `spec/architecture.md` → Stack). Styling via Tailwind CSS v4 (already scaffolded). Charts via Recharts (added in Phase 2, see `spec/architecture.md`).

> **Assumed:** Phase 1's chat thread visually stacks every question/answer pair (so it already *looks* like a running conversation), but the backend does not feed prior turns into the prompt until Phase 2 (`spec/agent.md` → Memory & Context, `spec/capabilities/answer-synthesis-and-conversation.md`). This is a deliberate, explicit deferral matching the intake brief's own phase grouping (conversation history is listed as a Phase 2 deliverable alongside charts/tables/cost/logging) — not an oversight. A follow-up question in Phase 1 will be answered correctly on its own terms, just without awareness of the earlier question.
