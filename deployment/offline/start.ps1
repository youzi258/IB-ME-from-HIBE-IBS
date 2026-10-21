param(
    [ValidateRange(1024,65535)][int]$Port = 8765,
    [string]$Name = 'cacr2026t4pmr7-web',
    [string]$Docker = 'docker'
)
$ErrorActionPreference = 'Stop'
$manifest = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'runtime-image.json') -Raw | ConvertFrom-Json
if (-not (Get-Command $Docker -ErrorAction SilentlyContinue)) {
    $candidate = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (Test-Path -LiteralPath $candidate) { $Docker = $candidate }
    else { throw 'Docker was not found. Restart the terminal after installation, or pass -Docker <path>.' }
}
# Docker Desktop's credential helper must be on this process's PATH as well.
$dockerPath = (Get-Command $Docker).Source
$env:PATH = (Split-Path -Parent $dockerPath) + [IO.Path]::PathSeparator + $env:PATH
$os = & $Docker info --format '{{.OSType}}'
if ($LASTEXITCODE -ne 0 -or $os -ne 'linux') { throw 'Start Docker Desktop with the Linux container engine first.' }
if ($manifest.archive -ne [IO.Path]::GetFileName($manifest.archive)) { throw 'Invalid image archive name.' }
$archive = Join-Path $PSScriptRoot $manifest.archive
Write-Host 'Verifying offline image...'
$stream = [IO.File]::OpenRead($archive)
$hasher = [Security.Cryptography.SHA256]::Create()
try { $actualHash = [BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
finally { $stream.Dispose(); $hasher.Dispose() }
if ($actualHash -ne $manifest.sha256) {
    throw 'Image checksum mismatch. Extract the supporting ZIP again.'
}
$present = $false
try {
    $installed = & $Docker image inspect $manifest.image_id --format '{{.Id}}' 2>$null
    $present = $LASTEXITCODE -eq 0 -and $installed -eq $manifest.image_id
} catch {
    # Windows PowerShell 5 can promote native stderr to a terminating error.
    $present = $false
}
if (-not $present) {
    & $Docker load --input $archive
    if ($LASTEXITCODE -ne 0) { throw 'Docker image import failed.' }
}
$installed = & $Docker image inspect $manifest.image_id --format '{{.Id}}'
if ($LASTEXITCODE -ne 0 -or $installed -ne $manifest.image_id) { throw 'Imported image ID differs from release manifest.' }
$existing = & $Docker container ls -a --filter "name=^/$Name`$" --format '{{.Names}}'
if ($existing) { throw "Container '$Name' already exists. Use another -Name, or explicitly stop/remove that container before restarting." }
& $Docker run --detach --pull=never --init --name $Name --shm-size=256m `
    --publish "127.0.0.1:${Port}:8765" $manifest.image_id web
if ($LASTEXITCODE -ne 0) { throw 'Container could not start; check the port and Docker resources.' }
for ($attempt = 0; $attempt -lt 90; $attempt++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 -Uri "http://127.0.0.1:$Port/api/jobs"
        if ($response.StatusCode -eq 200) {
            Write-Host "Open http://127.0.0.1:$Port/"
            Write-Host "Stop: $Docker stop $Name"
            Write-Host "Remove after stopping: $Docker rm $Name"
            exit 0
        }
    } catch { }
    $running = & $Docker inspect --format '{{.State.Running}}' $Name
    if ($running -ne 'true') { & $Docker logs $Name; throw 'Container exited during startup.' }
    Start-Sleep -Seconds 1
}
& $Docker logs $Name
throw 'Startup timed out; inspect Docker resources and container logs.'
