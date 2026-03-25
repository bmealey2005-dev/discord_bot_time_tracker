You are updating an existing Markdown documentation file for a script/system that has continued evolving during this conversation.

The relevant script and/or existing documentation will be provided BELOW this prompt.

Your task is to UPDATE the existing documentation so it reflects the script/system's current state.

# DOCUMENT LOCATION AND FILENAME (REPOSITORY):
- Canonical documentation for a script lives under **`script-docs/`** at the project root.
- **Filename:** Same as the script file’s name **except** replace the script’s **file extension** (e.g. `.luau`, `.lua`, `.server.lua`, `.client.lua`) with **`.md`**. Example: `UI-Scaling.plugin.luau` → `script-docs/UI-Scaling.plugin.md` (not `UI-Scaling.plugin.luau.md`).
- Update **that** path when editing on disk. If you are given an older path (e.g. under `docs/`) or a legacy name (e.g. `*.luau.md`), migrate content to the canonical `script-docs/` filename when you save.

# IMPORTANT CONTEXT:
- The script/system has been discussed and modified across this conversation.
- You may know design rationale, tradeoffs, rejected alternatives, and other context that is NOT obvious from the current code alone.
- Future AI agents will likely only have access to the script and this documentation, not this full conversation history.
- Therefore, the purpose of this update is to preserve the important context that would otherwise be lost.

# DO NOT:
- Do NOT rewrite the documentation from scratch unless necessary.
- Do NOT just summarize what the code currently does at face value.
- Do NOT produce line-by-line code explanation.
- Do NOT remove older rationale unless it is now outdated, incorrect, or irrelevant.

# DO:
Update the documentation to preserve and refine the non-obvious context behind the script/system, including where relevant:

1. Current Purpose & Scope
- What the script/system is responsible for now
- Any scope changes since the documentation was first created

2. Key Design Decisions
- Why the current implementation exists in its present form
- What alternatives were considered or rejected
- Why certain design choices may look unusual at first glance

3. Important Changes Since Prior Version
- New behavior, architectural shifts, renamed concepts, or changed assumptions
- Any previously documented details that are no longer true

4. Assumptions, Constraints, and Edge Cases
- Hidden assumptions
- Special cases being handled
- Engine/platform/tooling constraints that shaped the implementation

5. Integration / Architecture Notes
- Relationships with other scripts, systems, commands, configs, data formats, or workflows
- Anything a future AI agent would need in order to continue editing safely

6. Future Considerations
- Known weaknesses
- Expected future extensions
- Things intentionally deferred for later

# UPDATE BEHAVIOR:
- Preserve useful existing documentation
- Improve wording if needed for clarity
- Remove stale information
- Add any important missing context revealed during this conversation
- Keep the document well-structured and easy to skim

# STYLE:
- Write in clear, structured Markdown
- Prefer strong section headings
- Be thorough rather than minimal
- Optimize for handoff to a future AI agent

# OUTPUT FORMAT:
- Save/update the file at **`script-docs/<ScriptNameWithExtensionReplacedByMd>.md`** when writing to the repository (see DOCUMENT LOCATION AND FILENAME above).
- When the instruction is to return content only: output ONLY the updated Markdown document body.
- Do NOT include commentary outside of the document
