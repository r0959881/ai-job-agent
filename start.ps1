# Start the AI Job Agent web UI.
#   .\start.ps1              build the UI if needed, start on 127.0.0.1 and open the browser
#   .\start.ps1 -Dev         API only, then run `npm run dev` in web\ for hot reload
#   .\start.ps1 -Rebuild     force a fresh frontend build
param(
    [switch]$Dev,
    [switch]$Rebuild,
    [switch]$NoBrowser,
    [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
# The project path contains ')' and spaces, so every path below is quoted.
$root = $PSScriptRoot
Set-Location -LiteralPath $root

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPython) {
    $python = $venvPython
} else {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Error "Python was not found. Create the virtual environment first: python -m venv .venv"
    }
}

$serveArgs = @("serve.py", "--port", "$Port")
if ($Dev) { $serveArgs += "--dev" }
if ($Rebuild) { $serveArgs += "--rebuild" }
if ($NoBrowser) { $serveArgs += "--no-browser" }

& "$python" @serveArgs
exit $LASTEXITCODE
