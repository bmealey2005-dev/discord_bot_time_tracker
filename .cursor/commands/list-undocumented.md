# /list-undocumented — Find Documentation Links Without Local Files

## Overview

Read through all `.md` files under **`roblox-docs/`** (the local Creator Hub mirror) and compile a list of documentation links that point to pages that do **not** have a corresponding local `.md` file. These unresolved links indicate missing local documentation. Output the missing links ordered from **most ubiquitous** (linked from the most files) to **least ubiquitous**.

---

## What to Detect

1. **External Roblox docs links** — `https://create.roblox.com/docs/...` URLs. Map to local path: `roblox-docs/en-us/` + path after `/docs/` + `.md` (strip anchors).
2. **Relative internal links** — `[text](path/to/page.md)` or `[text](../sibling.md)` or `[text](path)` without `.md`. Resolve relative to the linking file and normalize to `roblox-docs/`-relative paths.
3. **Links that are resolved** — If the target `.md` file exists under `roblox-docs/`, the link is documented. Do **not** include it in the missing list.

---

## Steps to Execute

1. **Collect all `.md` files** in `roblox-docs/` (recursive).
2. **Parse each file** for links:
   - Markdown: `[text](url)` or `[text](path)`
   - Also check raw URLs in text (e.g. `https://create.roblox.com/docs/...`).
3. **Resolve each link to a local mirror path:**
   - `https://create.roblox.com/docs/foo/bar` → `roblox-docs/en-us/foo/bar.md`
   - `../luau/strings.md` from `roblox-docs/en-us/reference/engine/classes/X.md` → resolve relative to that file and normalize
   - `../../../luau/strings.md` → resolve and normalize
4. **Check existence:** For each resolved path, verify the file exists under `roblox-docs/`.
5. **Count references:** For each missing path, count how many distinct `.md` files link to it.
6. **Sort and output:** List missing links from highest reference count to lowest.

---

## Output Format

Output the result as a **Markdown table** so that URLs are easy to copy and paste. Columns: `#` | `URL` | `References`. Order by reference count (highest first):

```markdown
## Missing Documentation (most → least referenced)

| # | URL | References |
|---|-----|------------|
| 1 | https://create.roblox.com/docs/studio/properties | 12 |
| 2 | https://create.roblox.com/docs/studio/explorer | 5 |
| 3 | ../luau/control-structures.md (relative) | 4 |
...
```

- **External Roblox links:** Output the full URL: `https://create.roblox.com/docs/...` (no `.md` suffix).
- **Relative internal links:** Output the href as it appears in the source (e.g. `../luau/strings.md`) or the resolved `roblox-docs/`-relative path, with "(relative)" to distinguish.
- **References** = number of distinct `.md` files under `roblox-docs/` that link to that URL.

---

## Exclusions

- **Source URLs** — Lines like `**Source:** https://...` or `source_url: "..."` at the top of a file are metadata, not cross-references. Exclude them from the link scan.
- **Non-docs links** — Links to `create.roblox.com/dashboard`, `roblox.com`, or other non-`/docs/` URLs. Exclude (or list separately if useful).
- **Anchors** — `#section` anchors on the same page or another page. Resolve the base path only; if `roblox-docs/en-us/foo/bar.md` exists, the link is resolved even if the anchor differs.
- **Repo `docs/`** — Project runbooks under `docs/` are out of scope for this scan unless you run a separate pass.
