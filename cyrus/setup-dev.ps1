Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$ErrorMessage
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw $ErrorMessage
    }
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $repoRoot

Write-Host "Preparing Cyrus development environment..." -ForegroundColor Cyan

$envFiles = @(
    @{ Source = ".env.example"; Destination = ".env" },
    @{ Source = "apps/api/.env.example"; Destination = "apps/api/.env" },
    @{ Source = "apps/admin/.env.example"; Destination = "apps/admin/.env" },
    @{ Source = "apps/live/.env.example"; Destination = "apps/live/.env" },
    @{ Source = "apps/web/.env.example"; Destination = "apps/web/.env" }
)

foreach ($file in $envFiles) {
    if (-not (Test-Path $file.Destination)) {
        Copy-Item $file.Source $file.Destination
        Write-Host "Created $($file.Destination)" -ForegroundColor Green
    } else {
        Write-Host "Keeping existing $($file.Destination)" -ForegroundColor Yellow
    }
}

$apiEnvPath = Join-Path $repoRoot "apps/api/.env"
$apiEnvContent = Get-Content $apiEnvPath -Raw
if ($apiEnvContent -notmatch "(?m)^SECRET_KEY=") {
    $secretKey = -join ((48..57) + (97..122) | Get-Random -Count 50 | ForEach-Object { [char]$_ })
    Add-Content -Path $apiEnvPath -Value "`r`nSECRET_KEY=`"$secretKey`""
    Write-Host "Added SECRET_KEY to apps/api/.env" -ForegroundColor Green
}

if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    Invoke-CheckedCommand -Command { python -m venv .venv } -ErrorMessage "Failed to create Python virtual environment."
}

$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"

Write-Host "Installing Python dependencies..." -ForegroundColor Cyan
Invoke-CheckedCommand -Command { & $pythonExe -m pip install --upgrade pip } -ErrorMessage "Failed to upgrade pip."

$windowsRequirementsPath = Join-Path ([System.IO.Path]::GetTempPath()) "plane-local-windows-requirements.txt"
$baseRequirements = Get-Content "apps/api/requirements/base.txt" | Where-Object { $_ -notmatch "^psycopg-c==" }
$localRequirements = Get-Content "apps/api/requirements/local.txt" | Where-Object { $_ -notmatch "^-r\s+base\.txt$" }
Set-Content -Path $windowsRequirementsPath -Value @(
    $baseRequirements
    ""
    $localRequirements
)
Invoke-CheckedCommand -Command { & $pythonExe -m pip install -r $windowsRequirementsPath } -ErrorMessage "Failed to install Python requirements."
Remove-Item $windowsRequirementsPath -ErrorAction SilentlyContinue

Write-Host "Installing pnpm workspace dependencies..." -ForegroundColor Cyan
Invoke-CheckedCommand -Command { cmd /c corepack pnpm install } -ErrorMessage "Failed to install pnpm workspace dependencies."

$dockerAvailable = $null -ne (Get-Command docker -ErrorAction SilentlyContinue)
if ($dockerAvailable) {
    Write-Host "Docker detected. You can start services with:" -ForegroundColor Green
    Write-Host "  docker compose -f docker-compose-local.yml up" -ForegroundColor White
} else {
    Write-Warning "Docker is not on PATH yet. Install/start Docker Desktop before launching the local stack."
}

Write-Host ""
Write-Host "Environment bootstrap complete." -ForegroundColor Green
Write-Host "Backend venv: .venv" -ForegroundColor White
Write-Host "Start apps with: cmd /c corepack pnpm dev" -ForegroundColor White
