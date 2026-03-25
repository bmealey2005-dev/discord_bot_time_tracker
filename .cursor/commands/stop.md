Stop the tasks started by /setup (formerly /setup-restart) (Studio tree bridge and Rojo).

Run this command in the terminal:

```powershell
$bridgePid = (Get-NetTCPConnection -LocalPort 3838 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($bridgePid) { Stop-Process -Id $bridgePid -Force; Write-Host "Stopped bridge (port 3838)" } else { Write-Host "No bridge process on port 3838" }

$rojoPid = (Get-NetTCPConnection -LocalPort 34872 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess)
if ($rojoPid) { Stop-Process -Id $rojoPid -Force; Write-Host "Stopped Rojo (port 34872)" } else { Write-Host "No Rojo process on port 34872" }
```

Report what was stopped (bridge, Rojo, both, or neither).
