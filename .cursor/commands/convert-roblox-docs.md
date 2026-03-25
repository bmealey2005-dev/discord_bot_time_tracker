# Convert Roblox Documentation HTML to Cleaned HTML and Markdown

## Overview

Convert a Chrome-saved Roblox documentation HTML file into a cleaned HTML file and a Markdown file. The cleaned HTML contains only documentation content (scripts, styles, nav, buttons removed). The Markdown file contains the **source URL** from the original documentation at the top, followed by **all** text from the cleaned HTML, with structure inferred from the cleaned HTML (heading levels, bullet points, tables, code blocks, and other formatting).

## Usage

Type `/convert-roblox-docs` followed by one or more filenames, or a folder path. For example:

- `/convert-roblox-docs HttpService.html`
- `/convert-roblox-docs AvatarEditorService.html`
- `/convert-roblox-docs HttpService.html MarketplaceService.html Player.html`
- `/convert-roblox-docs html-files/` – converts all `.html` files in that folder (bulk conversion)
- `/convert-roblox-docs docs/Player.html`

If no filename or folder is provided, ask the user which HTML file(s) or folder to convert.

## Steps to Execute

1. **Identify the input file(s)**
   - Use the filename(s) or folder path provided after the command, or ask the user if none was given
   - Resolve paths relative to the workspace root
   - **If the argument is a folder (directory):** expand it to all `.html` files in that folder (non-recursive; only direct children). Pass these files to the script.
   - **If the argument is a file or files:** pass them directly to the script
   - Verify each file exists; if any are missing, report the error(s) and stop

2. **Ensure dependencies**
   - Check that `tools/roblox-docs/convert_roblox_docs.py` exists
   - Run `pip install -r tools/roblox-docs/requirements.txt` (or `pip install beautifulsoup4`) if needed

3. **Run the conversion**
   - Execute: `python tools/roblox-docs/convert_roblox_docs.py <file1> [file2] [file3] ...` (optionally `--docs-dir <path>`, `--cleaned-dir <path>`, `--original-dir <path>` to override defaults)
   - For each input file, the script:
     - Creates `tools/roblox-docs/html-files-cleaned/` and `tools/roblox-docs/html-files-original/` if they do not exist
     - Writes `<name>_cleaned.html` to `tools/roblox-docs/html-files-cleaned/` – stripped HTML with only doc content (scripts, styles, nav, buttons removed)
     - Writes `<page>.md` under `--docs-dir` (default: repo `docs/{path_from_source_url}/{page}.md`). **Canonical in-repo mirror** is `roblox-docs/en-us/`—pass e.g. `--docs-dir roblox-docs/en-us` so new pages land where Cursor rules expect. Markdown contains all text from the cleaned HTML; filename is derived from the source URL (last path segment, anchors excluded). Missing folders are created under the chosen base.
     - Moves the original `.html` file to `tools/roblox-docs/html-files-original/` after the `.md` file has been created

4. **Confirm completion**
   - Report the paths of all generated files (cleaned .html, .md, and original moved)
   - Note any errors if the conversion failed

## Requirements

- Python 3 with `beautifulsoup4` installed
- `tools/roblox-docs/convert_roblox_docs.py`
- Input file must be Chrome-saved HTML from Roblox Creator Hub (create.roblox.com) reference pages

## Output Directories

- **tools/roblox-docs/html-files-cleaned/** – Cleaned HTML files (scripts, styles, nav removed). Created automatically if missing.
- **tools/roblox-docs/html-files-original/** – Original HTML files are moved here after the corresponding `.md` file is created. Created automatically if missing.

## AI Instructions (when running or maintaining the converter)

- The Markdown file must contain the **source URL/link** from the original documentation at the top of the document (e.g. `**Source:** https://create.roblox.com/docs/reference/engine/classes/AvatarEditorService`). The converter extracts this from the Chrome "saved from url" HTML comment when present; otherwise it infers from the filename.
- The converter strips **same-page anchor links** from the output: links whose base URL matches the source page (e.g. `AvatarEditorService#MethodName` when converting AvatarEditorService) are replaced with plain text. Cross-page links (including anchors on other pages, e.g. `Instance#Archivable`) are preserved.
- The final `.md` file is placed under `--docs-dir` (default `docs/`) based on the source URL: that base maps to `https://create.roblox.com/docs` (each path segment is a folder; last segment is the page name). For this repo, prefer base `roblox-docs/en-us` so paths align with `docs-grounding.mdc`. Anchors are ignored. Missing folders are created automatically.
- The Markdown file must contain **all** text from the cleaned HTML.
- Use the structure of the cleaned HTML (typography classes, tables, lists, code blocks) to infer heading levels, bullet points, tables, and code formatting in the .md file.
- The **Inherited Members** section must be fully populated with all properties, methods, and events from each inherited class (Instance, Object, etc.), even when the page was saved with accordions collapsed. The converter extracts content from collapsed accordions (MuiCollapse-hidden) since the HTML contains it.
- When the collapsed data for Inherited Members is **not** included in the saved HTML (accordions were collapsed and content is absent), the converter outputs the inherited counts as **bullet points** (e.g. `- 57 inherited from [Instance](...)`) rather than sub-headings, to avoid confusing empty sub-headings.
- When inherited content **is** present (accordions expanded in saved HTML), inherited member sub-headings (**Properties**, **Methods**, **Events**) under each "X inherited from [Class]" heading must be one heading level below the parent (e.g. if the parent is h5, sub-headings must be h6).
- Tables with `<thead>` (Field/Type/Description) must output full markdown tables with all columns.
- Native h4/h5/h6 and Typography-h4/h5 headings must be preserved as section headings.
- API Reference method/event names must be one heading level below the Methods/Events section heading.
- Code sample titles must be one heading level below the Code Samples heading.
- Parameters and Returns sub-headings within method/event blocks must be one heading level below the method/event name.
- Code Samples heading must be at the same level as Parameters/Returns (one level below the method/event name). Individual code sample titles must be one level below Code Samples.
- All native HTML heading elements (h1-h6) and Typography-hN classes must be mapped to the correct heading level, including any future or unknown variants.

## Before Saving HTML

**Inherited Members:** The converter extracts the full list of inherited Instance/Object properties, methods, and events from the HTML when that content is present (accordion expanded or DOM includes collapsed content). If the saved HTML has accordions collapsed and the content is absent, the output will show inherited counts as bullet points (e.g. `- 57 inherited from Instance`) instead of sub-headings. To get full inherited member details in the .md file, expand the Inherited Members accordions before saving, or use "Save Page As" with "Webpage, Complete" if the site includes collapsed content in the DOM.
