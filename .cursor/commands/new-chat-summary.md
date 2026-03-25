# New Chat Summary (Context Handoff)

## Overview

Use this when the current chat is getting too long and you want to continue in a **fresh Cursor chat** without losing important context.

When invoked, the AI Agent must produce a **compact, copy‑pasteable handoff summary** of the current conversation so the user can paste it into a new chat and continue seamlessly.

## Usage

Type `/new-chat-summary` optionally followed by a focus note:

- `/new-chat-summary`
- `/new-chat-summary focus: inventory + trading`
- `/new-chat-summary focus: finish election system + tests`

If a focus note is provided, prioritize that area in the summary.

## Required Output Format (single message)

Return **exactly one** response formatted as **normal Markdown** using the headings below, designed to be **pasted as the first message in a new chat**.

- Do **not** add any text before the first heading.
- Do **not** wrap the output in triple backticks.

Template to follow:

```md
## CONTEXT (from previous chat; read-only)

### Goal
- ...

### Current Status
- What’s implemented, what’s partially done, what’s blocked

### Key Decisions / Constraints
- Architectural decisions, conventions, APIs chosen, Roblox constraints, performance/security constraints

### Files Changed / Added
- `path/to/file`: what changed + why (1 line each)

### Important Commands / How to Run
- Exact commands (Rojo, tests, build steps, etc.)

### Known Issues / Errors
- Current bugs, failing tests, lints, runtime errors, logs to look for

### Next Steps (most important first)
1. ...
2. ...
3. ...

### Open Questions / Assumptions
- Questions to ask the user next OR assumptions the agent made

---

## NEW INSTRUCTIONS (start here)
_User: write your next instructions below this heading. Everything above is prior context._
```

## Rules for the AI Agent

- **Do not** restate the entire conversation. Summarize only what’s needed to continue work.
- **Support multi-hop handoffs (2+ chats)**:
  - If this chat began with a previously generated handoff block (look for an initial `## CONTEXT (from previous chat; read-only)` section), treat that as **prior context**.
  - When producing the new handoff, **carry forward** any points from that prior context that are **still true and still useful**, merging them into the relevant sections (Goal/Status/Decisions/Files/Commands/Issues/Next Steps).
  - **Do not blindly copy** the old summary. Remove items that are no longer relevant, and update items that have progressed.
  - If something from the old summary is now finished or invalidated, either omit it or note it briefly as **resolved** in Current Status (keep this terse).
- **Be specific and actionable**: include concrete filenames, function/module names, and exact next steps.
- **Include state that isn’t obvious**: e.g., “server starts but replication missing”, “feature X implemented but not wired”, “PR not created”, “uncommitted changes”.
- **If code was written/edited**: list the exact files and what changed; do not paste large code blocks.
- **If Roblox APIs were used**: mention the relevant pages under `roblox-docs/` (file paths) that were relied on or should be checked next.
- **If there are multiple threads**: separate them in Next Steps and Current Status.
- **Do not** run tools/commands or make code changes. After outputting the summary, **stop** (do not continue implementing anything).
