# Sync Changes Log (Retroactive)

## Overview

Use this command to **retroactively populate** the AI Agent changes log from the current chat. Invoke this in conversations that occurred **before** the `ai-agent-changes-log` rule existed, so past changes can be recorded.

## Usage

Type `/sync-changes-log` (no arguments).

## Steps to Execute

1. **Read the full chat history** of this conversation from start to finish.

2. **Identify all changes** the AI Agent made:
   - File edits (create, modify, delete)
   - Configuration changes
   - Any other code or system modifications

3. **Extract for each change:**
   - Files affected (paths)
   - Summary: what changed (1–2 sentences)
   - Rationale: why it was done (from context or inferred)

4. **Open and edit** `.cursor/rules/general/ai-agent-changes-log.mdc`.

5. **Add entries** into the "Entries (newest first)" section using the rule's format:
   - `**YYYY-MM-DD** — *Files:* \`path/to/file\` | *Summary:* ... | *Rationale:* ...`

6. **Deduplication:** If the chat made multiple edits to the same logical change, consolidate into one entry.

7. **Date handling:** Use today's date for retroactive entries. If the date is ambiguous, use today.

8. **Remove the placeholder** `*(No entries yet — add entries as changes are made.)*` when adding the first real entry.

## Output

After updating the rule, confirm to the user:
- How many entries were added
- A brief list of what was recorded
