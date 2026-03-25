# /test — Generate Roblox Studio Test Scripts

You are generating **Roblox test scripts** for the Catalog-Game project. These scripts run **inside Roblox Studio** (not in Cursor). The developer will run them manually in Studio and copy the Output results back for analysis.

---

## Input Parsing

The user's input after `/test` determines the target:

| Format | Example | Behavior |
|--------|---------|----------|
| **Format 1** | `/test avatar cache` | Treat as **feature/system name**. Search the codebase to infer which scripts/modules implement it. |
| **Format 2** | `/test @Serializer` or `/test @ServerScriptService/DataCache` | Treat as **explicit path**. Target that folder or script directly. |

- If input starts with `@` → **Format 2** (explicit path)
- Otherwise → **Format 1** (feature inference)

---

## Format 1: Feature Inference

1. Use **semantic search** and **grep** to find modules implementing the feature.
2. Identify whether the code lives in:
   - `src/ServerScriptService/` (server-only)
   - `src/ReplicatedStorage/Client/` (client-only)
   - `src/ReplicatedStorage/` (shared)
3. Generate tests for the relevant module(s). If multiple modules are involved, prefer one focused test file per major component, or a single integration test if the feature is tightly coupled.

---

## Format 2: Explicit Path

1. Resolve the `@` path to actual file(s):
   - `@Serializer` → `src/ReplicatedStorage/modules/serializer.luau`
   - `@ServerScriptService/DataCache` → `src/ServerScriptService/` path for DataCache (search for it)
   - `@Modules/HumanoidDescriber` → `src/ReplicatedStorage/modules/` or similar
2. Determine run context (server vs client) from the target's location.
3. Generate tests targeting that exact module or folder.

---

## Output Location Rules

| Target Context | Test File Path |
|---------------|----------------|
| Server-side | `src/ServerScriptService/tests/{Name}Test.server.luau` |
| Client-side | `src/ReplicatedStorage/Client/tests/{name}_test.client.luau` |
| Shared module | `src/ServerScriptService/tests/{Name}Test.server.luau` (server can require shared) |

Use PascalCase for server test names (e.g. `SerializerTest`), snake_case for client (e.g. `decal_search_test`).

---

## Rojo / Require Paths

From `default.project.json`:
- `src/ServerScriptService` → `ServerScriptService.Server`
- `src/ReplicatedStorage/Client` → `ReplicatedStorage.Client`
- `src/ReplicatedStorage` → `ReplicatedStorage` (root)

**Require examples:**
- From `src/ServerScriptService/tests/`: `require(script.Parent.Parent.services.X)` or `require(ServerScriptService.Server.services.monetization_service.pending_purchase_store)`
- Shared module: `require(ReplicatedStorage.modules.serializer)` or `require(script.Parent.Parent.Parent.modules.serializer)` depending on depth

---

## Test Script Requirements

All generated tests MUST:

1. Use `--!strict`
2. Run in **Roblox Studio** (Play Solo for server tests)
3. Print **structured results to the Output window**
4. Include: test names, pass/fail status, error messages, summary statistics

---

## Output Format Template

Print results in this format:

```
[TEST] {Module/Feature Name}
------------------------
Test 1: {description} — PASS
Test 2: {description} — FAIL
  Expected: {expected}
  Received: {actual}
...
Summary:
Passed: N
Failed: M
```

---

## Test Design (Context-Aware)

Design tests based on what the module does:

| Module Type | Example Cases |
|-------------|---------------|
| **Serializer** | numbers, strings, booleans, tables, nested tables, empty tables, large tables, invalid types, cyclic references, mixed types |
| **Service** | mock dependencies, edge cases, error paths, init/cleanup |
| **Utility** | boundary values, nil inputs, empty inputs, invalid inputs |

Use `_test*` hooks if present (e.g. `DataService:_testInit()`, `ItemVerifier:_testInjectDetails()`). Otherwise mock at the test level.

---

## Reference Patterns

- **Server test structure**: `src/ServerScriptService/tests/MonetizationServiceTest.server.luau` — uses `TestPass(label, is_pass)`, pass/fail counts, `print(PREFIX .. label .. ": " .. (if is_pass then "PASS ✅" else "FAIL ❌"))`
- **Integration-style test**: `src/ServerScriptService/tests/sponsor_test.server.luau` — uses `print_separator()`, `print_test_header()`, config flags like `ENABLE_TESTS`

Prefer the simpler `TestPass` + summary pattern for unit tests. Use the integration pattern when the feature requires async setup or real services.

---

## Action

1. Parse the user's input (Format 1 or 2).
2. Locate the target module(s).
3. Read the target code to understand its API and behavior.
4. Generate one or more test scripts in the correct `src/ServerScriptService/tests/` or `src/ReplicatedStorage/Client/tests/` location.
5. Ensure the generated scripts print the required format to the Output window.
