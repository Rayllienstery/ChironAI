param(
    [string]$ProjectDir = (Get-Location).Path,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

# Configure once, then launch without parameters:
#   .\start_codex_proxy_configured.ps1
$ConfiguredBaseUrl = "http://127.0.0.1:8080"
$ConfiguredModel = "Hard-worker"
$ConfiguredOpenAiApiKey = "ChironAI"
$ConfiguredExtraArgs = @()

if (-not [string]::IsNullOrWhiteSpace($ConfiguredBaseUrl)) {
    $env:CHIRON_PROXY_BASE_URL = $ConfiguredBaseUrl
}
$env:OPENAI_BASE_URL = $env:CHIRON_PROXY_BASE_URL
$env:OPENAI_API_BASE = $env:CHIRON_PROXY_BASE_URL
if (-not [string]::IsNullOrWhiteSpace($ConfiguredOpenAiApiKey)) {
    $env:OPENAI_API_KEY = $ConfiguredOpenAiApiKey
}

if (-not (Get-Command codex -ErrorAction SilentlyContinue)) {
    Write-Error "codex CLI was not found in PATH. Install Codex CLI first."
    exit 1
}

Write-Host "Starting Codex via ChironAI proxy..."
Write-Host "Base URL: $($env:OPENAI_BASE_URL)"
Write-Host "Project dir: $ProjectDir"

try {
    $ResolvedProjectDir = (Resolve-Path -LiteralPath $ProjectDir -ErrorAction Stop).Path
} catch {
    Write-Error "Project directory not found: $ProjectDir"
    exit 1
}

$launchArgs = @()
if (-not [string]::IsNullOrWhiteSpace($ResolvedProjectDir)) {
    $launchArgs += "--cd"
    $launchArgs += $ResolvedProjectDir
}
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

& codex @launchArgs
exit $LASTEXITCODE
