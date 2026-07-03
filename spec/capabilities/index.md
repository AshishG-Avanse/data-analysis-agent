# Capabilities Index

---

## What Is a Capability?

A capability is a single, discrete action or behavior the agent performs.

## Capabilities in This Project

| Capability | File | Primary phase |
|-----------|------|----------------|
| File Ingestion | [file-ingestion.md](file-ingestion.md) | Phase 1 (baseline parse + schema); Phase 2 (best-effort malformed-file handling) |
| Iterative Code Execution | [iterative-code-execution.md](iterative-code-execution.md) | Phase 1 (fully real — the retry loop is core to Phase 1) |
| Answer Synthesis & Conversation | [answer-synthesis-and-conversation.md](answer-synthesis-and-conversation.md) | Phase 1 (baseline single-turn answer); Phase 2 (conversation memory, cost estimate, local log) |
| Result Presentation | [result-presentation.md](result-presentation.md) | Phase 1 (collapsible code only); Phase 2 (charts + summary tables) |

See `spec/roadmap.md` → "Phases of Development" for exactly which part of each capability ships in which phase, and why.

## How to Add a New Capability

Run `/zero-shot-build [description]` on the existing spec. The spec-writer sub-agent will:
1. Create a new file in this directory (`<name>.md`, no number prefix)
2. Update this index
3. Flag any dependencies on existing capabilities
4. Self-review that it fits the architecture and data model before returning

## Capability File Template

Each capability file should answer:
- **What it does** (one sentence)
- **Inputs** (what data it receives)
- **Outputs** (what it produces)
- **External calls** (APIs, LLMs, databases it touches)
- **Business rules** (constraints that always hold)
- **Success criteria** (how we test it)
