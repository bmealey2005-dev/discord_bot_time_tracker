You are generating documentation for a script that was created earlier in this conversation.

The script to document is provided BELOW this prompt.

Your task is to create a NEW `.md` documentation file for this script.

# OUTPUT LOCATION AND FILENAME (REPOSITORY):
- Write the documentation file under the project-root folder **`script-docs/`** (create the folder if it does not exist).
- **Filename:** Same as the script file’s name **except** replace the script’s **file extension** (e.g. `.luau`, `.lua`, `.server.lua`, `.client.lua`) with **`.md`**. The doc is **not** named by appending `.md` after the full script name (so **not** `Foo.luau.md`).
  - Examples: `UI-Scaling.plugin.luau` → `script-docs/UI-Scaling.plugin.md`; `MyModule.server.lua` → `script-docs/MyModule.server.md`; `Foo.lua` → `script-docs/Foo.md`.
  - Preserve capitalization and any dots in the base name (e.g. `UI-Scaling.plugin` stays as-is before `.md`).

# IMPORTANT CONTEXT:
- This script was written in this conversation, so you have access to design decisions and reasoning that are NOT obvious from the code alone.
- Future AI agents will NOT have access to this conversation history — only this documentation and the script itself.
- Therefore, your goal is to preserve the "hidden context" behind the script.

# DO NOT:
- Do NOT simply explain what the code does line-by-line.
- Do NOT restate information that is immediately obvious from reading the script.

# DO:
Focus on documenting information that would NOT be inferable from the script alone, including:

1. Purpose & High-Level Intent
   - What problem this script solves
   - Where it fits into the larger system

2. Key Design Decisions
   - Why certain approaches were chosen over alternatives
   - Any tradeoffs that were considered

3. Non-Obvious Behavior
   - Logic that may look strange or unintuitive at first glance
   - Edge cases or special handling

4. Assumptions & Constraints
   - Any assumptions made during development
   - Limitations or known constraints

5. Architecture & Integration Notes
   - How this script interacts with other systems
   - Expected inputs/outputs or dependencies

6. Future Considerations
   - Things that may need to change later
   - Known areas for improvement or extension

# STYLE:
- Write in clear, structured Markdown
- Use headings and bullet points where appropriate
- Be thorough — do NOT optimize for brevity
- Prioritize clarity for another AI agent reading this later

# OUTPUT FORMAT:
- Persist the document at **`script-docs/<ScriptNameWithExtensionReplacedByMd>.md`** as specified above (in addition to any chat output if your environment requires it).
- When the instruction is to return content only: output ONLY the Markdown document body.
- Do NOT include explanations outside of the document