param([string]$OutputDirectory, [string]$Docker = 'docker', [switch]$TestControls)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)
$materials = Split-Path -Parent $PSScriptRoot
$runtimeDirectories = @(Get-ChildItem -LiteralPath $materials -Directory | Where-Object { $_.Name -like '06_*' })
if ($runtimeDirectories.Count -ne 1) { throw 'Expected one 06 runtime directory next to this directory.' }
$runtime = $runtimeDirectories[0].FullName
$manifest = Get-Content -LiteralPath (Join-Path $runtime 'runtime-image.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not (Get-Command $Docker -ErrorAction SilentlyContinue)) {
    $candidates = @(Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe')
    foreach ($desktop in @(Get-Process -Name 'Docker Desktop' -ErrorAction SilentlyContinue | Where-Object Path)) {
        $candidates += Join-Path (Split-Path -Parent $desktop.Path) 'resources\bin\docker.exe'
    }
    $candidate = $candidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($candidate) { $Docker = $candidate }
    else { throw 'Docker not found; restart the terminal or pass -Docker <docker.exe path>.' }
}
$dockerPath = (Get-Command $Docker).Source
$env:PATH = (Split-Path -Parent $dockerPath) + [IO.Path]::PathSeparator + $env:PATH
$engine = & $Docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $engine -ne 'linux') { throw 'Start the Docker Linux engine first.' }
$present = $false
try { $found = & $Docker image inspect $manifest.image_id --format '{{.Id}}' 2>$null; $present = $LASTEXITCODE -eq 0 -and $found -eq $manifest.image_id } catch { }
if (-not $present) {
    $archive = Join-Path $runtime $manifest.archive
    $stream = [IO.File]::OpenRead($archive); $hasher = [Security.Cryptography.SHA256]::Create()
    try { $actual = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
    finally { $stream.Dispose(); $hasher.Dispose() }
    if ($actual -ne $manifest.sha256) { throw 'Offline image checksum mismatch.' }
    & $Docker load --input $archive
    if ($LASTEXITCODE -ne 0) { throw 'Offline image load failed.' }
}
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path (Split-Path -Parent $materials) ((Split-Path -Leaf $materials) + '-recomputed-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
}
$outputPath = [IO.Path]::GetFullPath($OutputDirectory)
$inputPath = [IO.Path]::GetFullPath($materials)
if ($outputPath -eq $inputPath -or $outputPath.StartsWith($inputPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Output must be outside the submitted materials.'
}
New-Item -ItemType Directory -Path $outputPath -Force | Out-Null
if (@(Get-ChildItem -LiteralPath $outputPath -Force).Count -ne 0) { throw 'Output directory must be empty.' }
$containerScript = '/submission/' + (Split-Path -Leaf $PSScriptRoot) + '/recompute.py'
$dockerArguments = @('run','--rm','--pull=never','--network','none','--read-only','--tmpfs','/tmp:rw,exec,size=1g',
    '--mount',"type=bind,source=$inputPath,target=/submission,readonly",'--mount',"type=bind,source=$outputPath,target=/output",
    $manifest.image_id,'python',$containerScript,'--materials','/submission','--output','/output')
if ($TestControls) { $dockerArguments += '--self-test' }
& $Docker @dockerArguments
if ($LASTEXITCODE -ne 0) { throw 'Recomputation failed; see the error above.' }
Write-Host "Recomputed results: $outputPath"
