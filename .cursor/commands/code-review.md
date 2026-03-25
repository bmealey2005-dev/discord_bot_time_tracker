# /code-review — Review Code Without Making Changes

You are performing a **read-only code review** for the Catalog-Game project. Review the specified feature, system, or script and report issues. **Do not change any code.**

---

## Input Parsing

The user's input after `/code-review` determines the target. Use the **same parsing rules as `/test`**:

| Format | Example | Behavior |
|--------|---------|----------|
| **Format 1** | `/code-review avatar cache` | Treat as **feature/system name**. Search the codebase to infer which scripts/modules implement it. |
| **Format 2** | `/code-review @Serializer` or `/code-review @ServerScriptService/DataCache` | Treat as **explicit path**. Target that folder or script directly. |

- If input starts with `@` → **Format 2** (explicit path)
- Otherwise → **Format 1** (feature inference)

---

## Format 1: Feature Inference

1. Use **semantic search** and **grep** to find modules implementing the feature.
2. Identify all relevant files (may span `src/ServerScriptService/`, `src/ReplicatedStorage/Client/`, `src/ReplicatedStorage/`).
3. Review the **entire** feature/system — all related scripts and modules.

---

## Format 2: Explicit Path

1. Resolve the `@` path to actual file(s):
   - `@Serializer` → `src/ReplicatedStorage/modules/serializer.luau`
   - `@ServerScriptService/DataCache` → `src/ServerScriptService/` path for DataCache (search for it)
   - `@Modules/HumanoidDescriber` → `src/ReplicatedStorage/modules/` or similar
2. If the path points to a folder, review all scripts in that folder and its subfolders.
3. If the path points to a single script, review that script and any modules it directly depends on that are part of the same feature.

---

## Scope

Review the **entire** script/system/feature that was specified. Include:

- The main module(s) and any closely coupled helpers
- Error handling, edge cases, and nil safety
- Type annotations and `--!strict` usage
- Security (e.g. server/client trust boundaries, validation)
- Performance (e.g. unnecessary loops, expensive operations)
- Maintainability (naming, structure, duplication)
- Roblox best practices (see `roblox-docs/` for Creator Hub mirror; `docs/` for project runbooks when relevant)

---

## Output Format

Report back a **list of issues** ordered by **urgency** (most critical first, least critical last).

For each issue, include:

1. **Urgency** — Critical / High / Medium / Low
2. **Location** — File path and line number(s) if applicable
3. **Description** — What the issue is
4. **Suggestion** — How to fix it (optional, but helpful)

Example structure:

```
## Code Review: {Feature/Module Name}

### Critical
1. **[path:line]** — Description of critical issue. Suggestion: ...

### High
2. **[path:line]** — Description of high-priority issue.

### Medium
3. **[path:line]** — Description of medium-priority issue.

### Low
4. **[path:line]** — Description of low-priority issue.

---
No issues found. — (if the code is clean)
```

---

## Urgency Guidelines

| Urgency | Examples |
|---------|----------|
| **Critical** | Security vulnerabilities, data loss risks, crashes, incorrect business logic |
| **High** | Missing error handling, type safety issues, memory leaks, race conditions |
| **Medium** | Code duplication, unclear naming, missing edge-case handling |
| **Low** | Style inconsistencies, minor optimizations, documentation gaps |

---

## Action

1. Parse the user's input (Format 1 or 2).
2. Locate and read all relevant code.
3. Review the code thoroughly.
4. Do **not** make any edits.
5. Report issues in order of urgency (highest → lowest). If no issues are found, say so clearly.
