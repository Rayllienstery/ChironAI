param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$CliArgs
)

$defaultBaseUrl = "http://127.0.0.1:8080"
if ([string]::IsNullOrWhiteSpace($env:CHIRON_PROXY_BASE_URL)) {
    $env:CHIRON_PROXY_BASE_URL = $defaultBaseUrl
}

$env:ANTHROPIC_BASE_URL = $env:CHIRON_PROXY_BASE_URL
if ([string]::IsNullOrWhiteSpace($env:ANTHROPIC_AUTH_TOKEN)) {
    $env:ANTHROPIC_AUTH_TOKEN = "ollama"
}
$env:ANTHROPIC_API_KEY = ""

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Error "claude CLI was not found in PATH. Install Claude Code CLI first."
    exit 1
}

Write-Host "Starting Claude Code via ChironAI proxy..."
Write-Host "Base URL: $($env:ANTHROPIC_BASE_URL)"
Write-Host "Tip: pass --model <your-build-id> to route through an LLM Proxy build."

& claude @CliArgs
exit $LASTEXITCODE
