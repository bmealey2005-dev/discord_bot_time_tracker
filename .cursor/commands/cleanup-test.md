# /cleanup-test — Remove Test Scripts Created by /test

You are **removing test scripts** that were created for the Catalog-Game project. This command undoes the setup from a previous `/test` invocation by deleting the generated test file(s).

---

## Input Parsing

The user's input after `/cleanup-test` determines what to remove:

| Format | Example | Behavior |
|--------|---------|----------|
| **No input** | `/cleanup-test` | Infer from **recent context**: the last test file(s) created in this conversation, or the most recently added test file(s) in `src/ServerScriptService/tests/` or `src/ReplicatedStorage/Client/tests/`. |
| **Format 1** | `/cleanup-test avatar cache` | Treat as **feature/system name**. Find the test file(s) that target the module(s) implementing this feature and delete them. |
| **Format 2** | `/cleanup-test @Serializer` or `/cleanup-test @SerializerTest` | Treat as **explicit path or test name**. Resolve to the corresponding test file(s) and delete them. |

- If input is empty or whitespace → infer from context
- If input starts with `@` → **Format 2** (explicit path/name)
- Otherwise → **Format 1** (feature inference)

---

## What to Remove

1. **Test scripts only** — Delete files in `src/ServerScriptService/tests/` or `src/ReplicatedStorage/Client/tests/` that were generated for the target.
2. **Do NOT modify production code** — The `/test` command creates new test files only. Cleanup removes those test files; it does not revert changes to services, modules, or other source files.

---

## How to Find Test Files

### Format 1 (feature name)

1. Use semantic search and grep to find the module(s) implementing the feature.
2. Infer the test file name from the target:
   - Server/shared → `src/ServerScriptService/tests/{Name}Test.server.luau` (PascalCase)
   - Client → `src/ReplicatedStorage/Client/tests/{name}_test.client.luau` (snake_case)
3. Search for matching test files and delete them.

### Format 2 (explicit path)

1. Resolve the path:
   - `@Serializer` → test is likely `SerializerTest.server.luau` in `src/ServerScriptService/tests/`
   - `@SerializerTest` → `src/ServerScriptService/tests/SerializerTest.server.luau`
   - `@ServerScriptService/DataCache` → search for a test targeting DataCache
2. Delete the matching test file(s).

### No input (context inference)

1. Check recent conversation: did we just create a test file? Delete it.
2. Or list `src/ServerScriptService/tests/` and `src/ReplicatedStorage/Client/tests/` and identify the most recently added file(s) that look like generated tests (e.g. `*Test.server.luau`, `*_test.client.luau`).
3. When ambiguous, ask the user which test to remove.

---

## Action

1. Parse the user's input (empty, Format 1, or Format 2).
2. Identify the test file(s) to remove.
3. Delete those files.
4. Confirm what was removed (e.g. "Removed `src/ServerScriptService/tests/SerializerTest.server.luau`").
