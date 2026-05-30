# Swing Lab - Pre-Market Review
# Runs via Windows Task Scheduler at 7am ET (Mon-Fri)
# Runs swing-lab review so dashboard shows today's review before market open

$ErrorActionPreference = "Stop"
$repo = "H:\Other\Claude Projects\Swing Lab"
Set-Location $repo

$runAt   = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd HH:mm:ss") + " UTC"
$logFile = Join-Path $repo "results\premarket.log"

function Log($msg) {
    $line = "[" + [System.DateTime]::UtcNow.ToString("HH:mm:ss") + "] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

("=== Swing Lab Pre-Market Run - " + $runAt + " ===") | Out-File $logFile -Encoding UTF8

try {
    Log "Running review..."
    $review = & uv run swing-lab review 2>&1
    $review | ForEach-Object { Log $_ }
    Log "Review complete."

} catch {
    Log "ERROR: $_"
    exit 1
}
