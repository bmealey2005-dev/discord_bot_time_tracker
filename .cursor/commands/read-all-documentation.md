# Read all relevant Roblox documentation (`/read-all-documentation`)

## Purpose

Append **`/read-all-documentation`** to the end of a prompt when you want the AI Agent to **deliberately read every piece of local Creator Hub–mirrored documentation** that plausibly applies to the feature or code change described in that prompt—**before** designing APIs, writing Luau, or refactoring.

This overrides the usual implicit tradeoff where agents may sample only a subset of docs. It does **not** mean “read every `.md` file under `roblox-docs/`”; it means **full coverage of everything that is in scope for the requested work**.

---

## Agent instructions (when this command is used)

1. **Infer scope from the user’s prompt**  
   Identify which Roblox **services, classes, members (methods, properties, events), data types, enums, globals, and libraries** the implementation will rely on—including transitive or “obvious” dependencies (e.g. `RemoteEvent` if networking is involved, `task`/`coroutine` if async is involved).

2. **Resolve paths using the repo mirror** (see **`roblox-docs/`** rules in `.cursor/rules/roblox-apis/docs-grounding.mdc`)  
   - Primary tree: **`roblox-docs/en-us/`**  
   - Map Creator Hub URLs to paths: `https://create.roblox.com/docs/<path>/<page>` → `roblox-docs/en-us/<path>/<page>.md`  
   - Also check **`roblox-docs/common/`** for hub/index pages when they clarify navigation or concepts tied to the feature.

3. **Read the documentation files**  
   For **each** API surface in scope, **read** the corresponding Markdown file(s) in the repo (use the read/search tools; do not skip “because it’s probably standard”).  
   - If a class has many members you will use, read the class page **and** any separate reference pages linked or clearly required (e.g. related data types, security notes).  
   - If documentation for a planned symbol is **missing** locally, say so explicitly and proceed with higher uncertainty—or suggest converting/adding docs per `convert-roblox-docs` / project workflow.

4. **Apply what you read**  
   - Align signatures, parameter names, return types, threading/async behavior, and security constraints with the docs.  
   - Call out contradictions between docs and older code in the repo.

5. **Do not**  
   - Treat **`docs/`** as the Creator Hub mirror when the same topic exists under **`roblox-docs/en-us/`** (per docs-grounding).  
   - Substitute memory for local docs when local docs exist for the APIs in scope.

---

## Usage (for humans)

- Add to the end of your prompt, e.g.:  
  `… implement X. /read-all-documentation`

---

## Relationship to the always-applied rule

The workspace rule **`docs-grounding`** already requires consulting `roblox-docs/` for accuracy. This command makes the expectation **stricter**: **exhaustive** reading of **all** locally available documentation that relates to the **feature as scoped by the prompt**, not an optional spot-check.
