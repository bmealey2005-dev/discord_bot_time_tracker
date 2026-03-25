Run a full local restart for Studio integration (snapshot bridge + Rojo) from the workspace root (project folder) using the steps below.

1) Stop existing listeners to avoid port conflicts:

```powershell
$bridgePid = (Get-NetTCPConnection -LocalPort 3838 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($bridgePid) { Stop-Process -Id $bridgePid -Force }

$rojoPid = (Get-NetTCPConnection -LocalPort 34872 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($rojoPid) { Stop-Process -Id $rojoPid -Force }
```

2) Set bridge environment variables for this terminal session:

Use the **literal** `your-long-random-token` below unless you changed `DEFAULT_TOKEN` in `tools/bridge-plugin/studio-tree-plugin/ExplorerSnapshot.plugin.luau` and rebuilt the Studio plugin. **Do not** substitute a random GUID here: ExplorerSnapshot sends this same default via `Bearer`, so a mismatched bridge token causes HTTP 401 on `/snapshot`.

```powershell
$workspaceRoot = (Resolve-Path ".").Path
$env:STUDIO_TREE_TOKEN="your-long-random-token"
$env:STUDIO_TREE_PORT="3838"
$env:STUDIO_TREE_OUTPUT_DIR=(Join-Path $workspaceRoot "tools\bridge-plugin\place-file-data")
```

3) Start the bridge:

```powershell
npm --prefix (Join-Path $workspaceRoot "tools\bridge-plugin\studio-tree-bridge") run start
```

4) Start Rojo:

```powershell
rojo serve (Join-Path $workspaceRoot "default.project.json")
```

5) Verify both endpoints:

```powershell
Invoke-RestMethod http://127.0.0.1:3838/health
Invoke-WebRequest http://127.0.0.1:34872/ -UseBasicParsing
```

After running, report success or failure for each step (stop old processes, start bridge, start Rojo, bridge health check, Rojo check), including any error output.
