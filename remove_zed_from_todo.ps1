# PowerShell script to remove all Zed-related content from TODO.md

$content = Get-Content c:\Users\Raylee\AI\TODO.md -Raw

# Remove the entire section 11 and all Cursor-like Zed Infrastructure content
# Find the pattern from "## 11. Senior iOS Assistant" to the end before "## 3. Доступ в интернет" in the last section

$lines = Get-Content c:\Users\Raylee\AI\TODO.md
$output = @()
$skip = $false
$skipStarted = $false

for ($i = 0; $i -lt $lines.Length; $i++) {
    $line = $lines[$i]
    
    # Start skipping at section 11
    if ($line -match '^## 11\. Senior iOS Assistant \(Zed integration\)') {
        $skip = $true
        $skipStarted = $true
        Write-Host "Found section 11 at line $i, starting skip..."
        continue
    }
    
    # Stop skipping when we hit the next major section that's NOT part of Zed content
    # Look for pattern like "## 3. Доступ в интернет" which appears after all Zed content
    if ($skip -and $line -match '^## 3\. Доступ в интернет \(web search\)') {
        $skip = $false
        Write-Host "Found end marker at line $i, stopping skip"
    }
    
    if (-not $skip) {
        # Also remove "настройка Zed" from README line
        $line = $line -replace ', настройка Zed', ''
        $output += $line
    }
}

# Save the result
$output | Set-Content c:\Users\Raylee\AI\TODO.md -Encoding UTF8
Write-Host "Done! Removed all Zed-related content."
