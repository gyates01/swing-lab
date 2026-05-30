# Swing Lab - Nightly Gate+Scan
# Runs via Windows Task Scheduler at 2am ET (Mon-Fri)
# Outputs results to results/ and pushes to GitHub for the remote review routine

$ErrorActionPreference = "Stop"
$repo = "H:\Other\Claude Projects\Swing Lab"
Set-Location $repo

$date   = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd")
$runAt  = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd HH:mm:ss") + " UTC"
$logFile = Join-Path $repo "results\nightly.log"

function Log($msg) {
    $line = "[" + [System.DateTime]::UtcNow.ToString("HH:mm:ss") + "] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

("=== Swing Lab Nightly Run - " + $runAt + " ===") | Out-File $logFile -Encoding UTF8

try {
    Log "Running gate..."
    $gate = & uv run swing-lab gate 2>&1
    $gate | Out-File (Join-Path $repo "results\latest_gate.txt") -Encoding UTF8
    Log "Gate complete."

    Log "Running scan..."
    $scan = & uv run swing-lab scan 2>&1
    $scan | Out-File (Join-Path $repo "results\latest_scan.txt") -Encoding UTF8
    Log "Scan complete."

    $meta = "run_date=$date`ncompleted_at=$runAt`ngate_lines=" + $gate.Count + "`nscan_lines=" + $scan.Count
    $meta | Out-File (Join-Path $repo "results\latest_meta.txt") -Encoding UTF8

    Log "Committing to GitHub..."
    & git add "results/latest_gate.txt" "results/latest_scan.txt" "results/latest_meta.txt"
    & git commit -m "auto: gate+scan $date"
    & git push origin main
    Log "Pushed to GitHub. Done."

} catch {
    Log "ERROR: $_"
    ("ERROR: " + $_ + "`nRun attempted: $runAt") | Out-File (Join-Path $repo "results\latest_meta.txt") -Encoding UTF8
    & git add "results/latest_meta.txt" 2>$null
    & git commit -m "auto: gate+scan ERROR $date" 2>$null
    & git push origin main 2>$null
    exit 1
}
