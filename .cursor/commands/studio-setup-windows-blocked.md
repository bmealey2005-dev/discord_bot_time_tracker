# Studio Setup When Windows Blocks Applications

Use this command when Windows Application Control (WDAC/AppLocker) blocks the Rust bridge build or the studio-tree-codec binary. It instructs the AI Agent to run the necessary terminal commands.

## Context

- **Rust bridge** (`tools/bridge-plugin/studio-tree-bridge-rust/`): Single binary, no subprocess. May be blocked during `cargo build` (build scripts).
- **Node bridge** (`tools/bridge-plugin/studio-tree-bridge/`): Runs via Node. If it spawns `studio-tree-codec.exe`, that subprocess can be blocked.
- **Fallback**: Use the Node bridge with ScreenGui export disabled (`STUDIO_TREE_ENABLE_SCREEN_GUI_EXPORT=0`). Snapshots and instance paths still work.

## Instructions for the AI Agent 

When the user reports Windows blocking (e.g. "Application Control policy has blocked this file", os error 4551, or spawn UNKNOWN), run these commands in order from the workspace root.

### 1) Stop existing listeners

```powershell
$bridgePid = (Get-NetTCPConnection -LocalPort 3838 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($bridgePid) { Stop-Process -Id $bridgePid -Force; Write-Host "Stopped bridge" } else { Write-Host "No bridge on 3838" }

$rojoPid = (Get-NetTCPConnection -LocalPort 34872 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($rojoPid) { Stop-Process -Id $rojoPid -Force; Write-Host "Stopped Rojo" } else { Write-Host "No Rojo on 34872" }
```

### 2) Set environment variables

```powershell
$workspaceRoot = (Resolve-Path ".").Path
$env:STUDIO_TREE_TOKEN="your-long-random-token"
$env:STUDIO_TREE_PORT="3838"
$env:STUDIO_TREE_OUTPUT_DIR=(Join-Path $workspaceRoot "tools\bridge-plugin\place-file-data")
# Disable ScreenGui export when codec is blocked (snapshots still work):
$env:STUDIO_TREE_ENABLE_SCREEN_GUI_EXPORT="0"
```

### 3) Try Rust bridge first (may fail if build scripts are blocked)

```powershell
cargo build --release --manifest-path (Join-Path $workspaceRoot "tools\bridge-plugin\studio-tree-bridge-rust\Cargo.toml")
```

If that succeeds, start the bridge:

```powershell
$workspaceRoot = (Resolve-Path ".").Path
$env:STUDIO_TREE_TOKEN="your-long-random-token"
$env:STUDIO_TREE_PORT="3838"
$env:STUDIO_TREE_OUTPUT_DIR=(Join-Path $workspaceRoot "tools\bridge-plugin\place-file-data")
npm --prefix (Join-Path $workspaceRoot "tools\bridge-plugin\studio-tree-bridge") run start
```

### 4) If Rust build fails, use Node bridge with ScreenGui disabled

```powershell
$workspaceRoot = (Resolve-Path ".").Path
$env:STUDIO_TREE_TOKEN="your-long-random-token"
$env:STUDIO_TREE_PORT="3838"
$env:STUDIO_TREE_OUTPUT_DIR=(Join-Path $workspaceRoot "tools\bridge-plugin\place-file-data")
$env:STUDIO_TREE_ENABLE_SCREEN_GUI_EXPORT="0"
npm --prefix (Join-Path $workspaceRoot "tools\bridge-plugin\studio-tree-bridge") run start:node
```

Run the bridge in the background. Then start Rojo:

```powershell
rojo serve (Join-Path $workspaceRoot "default.project.json")
```

### 5) Verify

```powershell
Invoke-RestMethod http://127.0.0.1:3838/health
Invoke-WebRequest http://127.0.0.1:34872/ -UseBasicParsing
```

## Summary for the AI

1. Stop old processes (ports 3838, 34872).
2. Set env vars; include `STUDIO_TREE_ENABLE_SCREEN_GUI_EXPORT=0` when codec/binary is blocked.
3. Try `cargo build` for Rust bridge. If it succeeds, use `npm run start`. If it fails, use `npm run start:node` with the env var above.
4. Start Rojo in a separate terminal.
5. Verify both endpoints.

Report success/failure for each step.
