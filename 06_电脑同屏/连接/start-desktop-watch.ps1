$ErrorActionPreference='Stop'
$project=Split-Path -Parent $PSScriptRoot
$python=Join-Path $project 'artifacts/cubes-training-20261028/windows-env/Scripts/python.exe'
$script=Join-Path $PSScriptRoot 'watch-desktop-connection.py'
# The watcher holds a Windows file lock; a second invocation exits immediately.
Start-Process -FilePath $python -ArgumentList @('-B','-X','utf8',('"'+$script+'"')) -WindowStyle Hidden | Out-Null
