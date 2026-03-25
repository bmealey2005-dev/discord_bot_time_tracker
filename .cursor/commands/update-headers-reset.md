# Update Lua/Luau File Headers (Reset / Full Audit)

## Overview

Same as `/update-headers` but **audits every script** in scope, ignoring content-hash change detection. Use when you want to force a full re-audit of all headers (e.g. after changing header format, fixing manifest drift, or bulk updates).

**Base instructions:** Follow [`.cursor/commands/update-headers.md`](.cursor/commands/update-headers.md) for all logic, with the modification below.

## Modification

**Step 4 — Build "to check" list:** Instead of filtering by hash:

- Use the **filtered list** from step 1 as the "to check" list directly (i.e. audit every file in scope).
- Still remove manifest entries for files that no longer exist in the repo.

All other steps (1–3, 5–6) are unchanged: same path filtering, same header format, same audit rules, same manifest updates.

## Usage

- **No arguments:** Audit all tracked `.luau` and `.lua` files.
- **With path:** Audit only the specified file or files within the specified folder.

Examples:

- `/update-headers-reset` — full audit of every `.luau` and `.lua` file
- `/update-headers-reset src/ServerScriptService/services/data_service.luau` — audit single file
- `/update-headers-reset src/ServerScriptService/services/legacy_loader.lua` — audit single file
- `/update-headers-reset src/ServerScriptService/services/` — audit all `.luau` and `.lua` files in that folder (recursive)
