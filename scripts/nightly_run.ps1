# Swing Lab — Nightly Gate+Scan
# Runs via Windows Task Scheduler at 2am ET (Mon-Fri)
# Outputs results to results/ and pushes to GitHub for the remote review routine

$ErrorActionPreference = "Stop"
$repo = "H:\Other\Claude Projects\Swing Lab"
Set-Location $repo

$date    = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd")
$runAt   = [System.DateTime]::UtcNow.ToString("yyyy-MM-dd HH:mm:ss") + " UTC"
$logFile = "$repo\results\nightly.log"

function Log($msg) {
    $line = "[$([System.DateTime]::UtcNow.ToString('HH:mm:ss'))] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

# Clear log for this run
"=== Swing Lab Nightly Run — $runAt ===" | Out-File $logFile -Encoding UTF8

try {
    Log "Running gate..."
    $gate = & uv run swing-lab gate 2>&1
    $gate | Out-File "$repo\results\latest_gate.txt" -Encoding UTF8
    Log "Gate complete."

    Log "Running scan..."
    $scan = & uv run swing-lab scan 2>&1
    $scan | Out-File "$repo\results\latest_scan.txt" -Encoding UTF8
    Log "Scan complete."

    # Metadata file for the review routine to verify freshness
    @"
run_date=$date
completed_at=$runAt
gate_lines=$($gate.Count)
scan_lines=$($scan.Count)
"@ | Out-File "$repo\results\latest_meta.txt" -Encoding UTF8

    Log "Committing to GitHub..."
    & git add results/latest_gate.txt results/latest_scan.txt results/latest_meta.txt
    & git commit -m "auto: gate+scan $date"
    & git push origin main
    Log "Pushed to GitHub. Done."

} catch {
    Log "ERROR: $_"
    # Write error file so review routine can detect failure
    "ERROR: $_`nRun attempted: $runAt" | Out-File "$repo\results\latest_meta.txt" -Encoding UTF8
    & git add results/latest_meta.txt
    & git commit -m "auto: gate+scan ERROR $date" 2>$null
    & git push origin main 2>$null
    exit 1
}
