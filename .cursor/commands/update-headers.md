# Update Lua/Luau File Headers

## Overview

Audit Lua/Luau file headers using content-hash change detection. Only process files that have changed since the last audit, reducing AI resource usage. Uses `git hash-object` for accurate change detection (catches edits that don't change line count).

## Usage

- **No arguments:** Audit all tracked `.luau` and `.lua` files (full audit).
- **With path:** Audit only the specified file or files within the specified folder.

Examples:

- `/update-headers` — full audit
- `/update-headers src/ServerScriptService/services/data_service.luau` — audit single file
- `/update-headers src/ServerScriptService/services/legacy_loader.lua` — audit single file
- `/update-headers src/ServerScriptService/services/` — audit all `.luau` and `.lua` files in that folder (recursive)

## Header Format

Headers must include (see `.cursor/rules/general/luau-file-conventions.mdc`):

- **What the module does** — Brief description of purpose and key responsibilities
- **Which system/feature it belongs to** — e.g., "Catalog system", "Monetization service", "Pose editor"
- **Runtime scope** — Whether it's server-only, client-only, or shared (both)

## AI Tags and Human Preservation

- AI-created headers use `-- [AI_HEADER_START]` and `-- [AI_HEADER_END]`.
- When auditing: only replace content between these tags.
- If the file has a header but no AI tags, add the AI header above the human header (do not replace or remove the human header).

## Manifest

- **Path:** `tools/header-manifest.json`
- **Format:** `{ "path/to/file.luau": "sha1hash", "path/to/file.lua": "sha1hash", ... }`
- **Purpose:** Stores content hash per file; only files with different hash (or new files) are audited.

## Steps to Execute

1. **List tracked `.luau` and `.lua` files to audit**
   - Run: `git ls-files "**/*.luau" "**/*.lua"`
   - Use repo-relative paths (forward slashes) for consistency
   - **If a path was provided:** Filter the list:
     - **File path** (ends with `.luau` or `.lua`): Include only that file if it exists in the list
     - **Folder path:** Include files whose path starts with the folder (add `/` if missing; e.g. `src/ServerScriptService/services` or `src/ServerScriptService/services/` matches `src/ServerScriptService/services/foo.luau`, `src/ServerScriptService/services/sub/bar.lua`)
   - **If no path was provided:** Use the full list (full audit)
   - Retain the full list for step 4 (cleanup of deleted files); use the filtered list for steps 2–5 when a path was provided

2. **Get content hash for each file**
   - Run: `git hash-object <path>` for each file
   - Returns 40-char SHA-1 hash

3. **Load manifest**
   - Read `tools/header-manifest.json`
   - If missing or invalid, use `{}`

4. **Build "to check" list**
   - Files where current hash differs from manifest
   - Files not in manifest (new files)
   - Remove manifest entries for files that no longer exist in the repo

5. **Audit each file in "to check"**
   - Read the file
   - If file has no header: create header with `[AI_HEADER_START]` and `[AI_HEADER_END]` tags at the top
   - If file has AI tags: replace only the content between `[AI_HEADER_START]` and `[AI_HEADER_END]` with updated system, purpose, scope
   - If file has header but no AI tags: add AI header with `[AI_HEADER_START]` and `[AI_HEADER_END]` above the human header (preserve human header below it)
   - Update manifest entry with new hash (run `git hash-object` again after editing)

6. **Save manifest**
   - Write updated `tools/header-manifest.json`

## Notes

- **Path argument:** Resolve relative to workspace root. Use forward slashes.
- **Windows:** Use forward slashes in paths; `git ls-files` returns repo-relative paths.
- **First run:** Manifest is empty; all files are audited and manifest is populated.
- **Shared manifest:** Commit `tools/header-manifest.json` so the team shares audit state.
