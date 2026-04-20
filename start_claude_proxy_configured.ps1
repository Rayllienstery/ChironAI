param(
    [string]$ProjectDir = (Get-Location).Path,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

# Configure once, then launch without parameters:
#   .\start_claude_proxy_configured.ps1
$ConfiguredBaseUrl = "http://127.0.0.1:8080"
$ConfiguredModel = "Hard-worker"
$ConfiguredAuthToken = "ChironAI"
$ConfiguredExtraArgs = @()

if (-not [string]::IsNullOrWhiteSpace($ConfiguredBaseUrl)) {
    $env:CHIRON_PROXY_BASE_URL = $ConfiguredBaseUrl
}
$env:ANTHROPIC_BASE_URL = $env:CHIRON_PROXY_BASE_URL
if (-not [string]::IsNullOrWhiteSpace($ConfiguredAuthToken)) {
    $env:ANTHROPIC_AUTH_TOKEN = $ConfiguredAuthToken
}
$env:ANTHROPIC_API_KEY = ""

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "claude CLI was not found in PATH. Install Claude Code CLI first."
    exit 1
}

Write-Host "Starting Claude Code via ChironAI proxy..."
Write-Host "Base URL: $($env:ANTHROPIC_BASE_URL)"
Write-Host "Project dir: $ProjectDir"

try {
    $ResolvedProjectDir = (Resolve-Path -LiteralPath $ProjectDir -ErrorAction Stop).Path
} catch {
    Write-Error "Project directory not found: $ProjectDir"
    exit 1
}

$launchArgs = @()
if (-not [string]::IsNullOrWhiteSpace($ConfiguredModel)) {
    $launchArgs += "--model"
    $launchArgs += $ConfiguredModel
}
if ($ConfiguredExtraArgs) {
    $launchArgs += $ConfiguredExtraArgs
}
if ($CliArgs) {
    $launchArgs += $CliArgs
}

Push-Location -LiteralPath $ResolvedProjectDir
try {
    & claude @launchArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
