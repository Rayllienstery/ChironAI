param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

# Configure once, then launch without parameters:
#   .\start_codex_proxy_configured.ps1
$ConfiguredBaseUrl = "http://127.0.0.1:8080"
$ConfiguredModel = "your-build-id"
$ConfiguredOpenAiApiKey = "ollama"
$ConfiguredExtraArgs = @()

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$baseScript = Join-Path $scriptRoot "start_codex_proxy.ps1"
if (-not (Test-Path -LiteralPath $baseScript)) {
    Write-Error "Base script not found: $baseScript"
    exit 1
}

if (-not [string]::IsNullOrWhiteSpace($ConfiguredBaseUrl)) {
    $env:CHIRON_PROXY_BASE_URL = $ConfiguredBaseUrl
}
if (-not [string]::IsNullOrWhiteSpace($ConfiguredOpenAiApiKey)) {
    $env:OPENAI_API_KEY = $ConfiguredOpenAiApiKey
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

& $baseScript @launchArgs
exit $LASTEXITCODE
