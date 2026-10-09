param(
    [Parameter(Mandatory=$true)][string]$ComfyRoot,
    [string]$PythonExe
)
$ErrorActionPreference = 'Stop'
$comfyPath = (Resolve-Path -LiteralPath $ComfyRoot).Path
if (-not (Test-Path -LiteralPath (Join-Path $comfyPath 'main.py'))) {
    throw 'ComfyRoot must be the ComfyUI directory containing main.py.'
}
$nodesPath = Join-Path $comfyPath 'custom_nodes'
if (-not (Test-Path -LiteralPath $nodesPath)) { throw 'custom_nodes directory not found.' }
if (Test-Path -LiteralPath (Join-Path $nodesPath 'astra_trusted_surface')) {
    throw 'Development astra_trusted_surface detected. Do not load both packs; see README upgrade instructions.'
}
if (-not $PythonExe) {
    $candidates = @(
        (Join-Path $comfyPath 'venv\Scripts\python.exe'),
        (Join-Path (Split-Path -Parent $comfyPath) 'python_embeded\python.exe')
    )
    $PythonExe = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $PythonExe -or -not (Test-Path -LiteralPath $PythonExe)) {
    throw 'ComfyUI Python not found. Supply -PythonExe with its exact interpreter path.'
}
$destination = Join-Path $nodesPath 'astra_exterior_poisson'
$sourcePath = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$alreadyInPlace = $sourcePath -ieq $destination
if ((Test-Path -LiteralPath $destination) -and -not $alreadyInPlace) {
    throw 'Destination already exists. Back it up before installing; this script does not overwrite packs.'
}
& $PythonExe -m pip install -r (Join-Path $sourcePath 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed; package was not copied.' }
if (-not $alreadyInPlace) {
    Copy-Item -LiteralPath $sourcePath -Destination $destination -Recurse
}
$demoDirectory = Join-Path $comfyPath 'input\3d'
New-Item -ItemType Directory -Path $demoDirectory -Force | Out-Null
$demoTarget = Join-Path $demoDirectory 'Astra_Demo_Open_Skin.glb'
if (-not (Test-Path -LiteralPath $demoTarget)) {
    Copy-Item -LiteralPath (Join-Path $destination 'examples\Astra_Demo_Open_Skin.glb') -Destination $demoTarget
}
Write-Output 'Installed. Restart ComfyUI and import workflow/Astra_Exterior_Poisson_Demo.json.'
