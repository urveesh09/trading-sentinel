<#
Round-3 untouched scoring, one shot (owner authorised for October 5, 2026 after 16:30 IST).

1. Waits (until 21:00) for a same-day Kite token in Production's data volume (read-only).
2. Downloads Kite January-July 2026 history (Momentum 15-minute + NIFTY 50, Penny minute)
   inside the Production engine image, reading the token from the volume mounted :ro and
   writing only into Dev docs/research/kite/*/_local. The token is never copied or printed.
3. Freezes momentum-smart-t3 and penny-noise-t3, commits and pushes the freezes.
4. Scores each study once and commits and pushes results.json.

Read-only for Production: the volume is mounted :ro and no Production file is written.
Log: docs/research/kite/2026-10-05-round3-run.log (git-ignored _local is not used for the log
so the owner can find it; it holds no credentials).
#>
# Native tools (docker, git, python) report through $LASTEXITCODE; PowerShell 5.1
# would otherwise turn their stderr lines into terminating errors.
$ErrorActionPreference = 'Continue'
$Dev = 'C:\Users\Urveesh\Desktop\trading-sentinel'
$ProdEnv = 'C:\Users\Urveesh\Desktop\Production_Trading-sentinel\.env'
$Image = 'production_trading-sentinel-python-engine:latest'
$Volume = 'production_trading-sentinel_trading_data'
$Py = Join-Path $Dev 'python-engine\winvenv\Scripts\python.exe'
$Kite = Join-Path $Dev 'docs\research\kite'
$Log = Join-Path $Kite '2026-10-05-round3-run.log'
$Branch = 'codex/production-correction-hedge-p0'
$Trailer = "`n`nCo-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`nClaude-Session: https://claude.ai/code/session_015nJ1dM85rM3Kin6rcgqED2"

New-Item -ItemType Directory -Force $Kite | Out-Null
function Log($msg) { "$(Get-Date -Format s) $msg" | Tee-Object -FilePath $Log -Append }
Set-Location $Dev

function TokenDate {
    $out = docker run --rm -v "${Volume}:/data:ro" --entrypoint python $Image -c `
        "import json;print(json.load(open('/data/kite_token.json')).get('saved_date_ist',''))" 2>$null
    return ($out | Select-Object -Last 1)
}

$today = (Get-Date).ToString('yyyy-MM-dd')
$deadline = (Get-Date).Date.AddHours(21)
while ((TokenDate) -ne $today) {
    if ((Get-Date) -ge $deadline) { Log "no same-day Kite token by 21:00; stopped, nothing downloaded"; exit 2 }
    Log "waiting for today's Kite login (token not from $today yet)"
    Start-Sleep -Seconds 900
}
Log "same-day Kite token present"

function Acquire($tickers, $interval, $index, $folder) {
    $out = Join-Path $Kite "$folder\_local"
    if (Test-Path (Join-Path $out 'validated-kite.sqlite')) { Log "$folder already acquired"; return }
    New-Item -ItemType Directory -Force $out | Out-Null
    Log "acquiring $folder ($interval)"
    docker run --rm --env-file $ProdEnv -v "${Volume}:/data:ro" -v "${Dev}:/repo:ro" -v "${out}:/out" `
        -w /repo --entrypoint python $Image scripts/acquire_kite_history.py `
        --tickers-from $tickers --start 2026-01-01 --end 2026-07-31 --interval $interval `
        "--index=$index" --token-file /data/kite_token.json --out /out/validated-kite.sqlite 2>&1 |
        Where-Object { $_ -notmatch 'token ' } | ForEach-Object { Log "  $_" }
    if ($LASTEXITCODE -ne 0) { Log "acquisition failed for $folder"; exit 3 }
}

Acquire '/repo/docs/research/yahoo/2026-10-04-momentum-thesis-t2/freeze.json' '15minute' 'NIFTY 50' '2026-10-05-momentum-h1'
Acquire '/repo/docs/research/yahoo/2026-10-04-penny-trader-oos/freeze.json' 'minute' '' '2026-10-05-penny-h1'

$studies = @(
    @{ name = 'momentum-smart-t3'; out = 'docs\research\kite\2026-10-05-momentum-smart-t3' },
    @{ name = 'penny-noise-t3';    out = 'docs\research\kite\2026-10-05-penny-noise-t3' }
)
foreach ($s in $studies) {
    if (-not (Test-Path (Join-Path $s.out 'freeze.json'))) {
        & $Py scripts\run_preregistered_study.py freeze $s.name --out $s.out 2>&1 | ForEach-Object { Log "  $_" }
        if ($LASTEXITCODE -ne 0) { Log "freeze failed for $($s.name)"; exit 4 }
    }
}
git add -- 'docs/research/kite/2026-10-05-momentum-smart-t3/freeze.json' 'docs/research/kite/2026-10-05-penny-noise-t3/freeze.json'
git commit -m "research: freeze round-3 studies on untouched Kite Jan-Jul 2026$Trailer" -- `
    'docs/research/kite/2026-10-05-momentum-smart-t3/freeze.json' 'docs/research/kite/2026-10-05-penny-noise-t3/freeze.json' 2>&1 | ForEach-Object { Log "  $_" }
git push origin $Branch 2>&1 | ForEach-Object { Log "  $_" }
Log "freezes committed and pushed"

foreach ($s in $studies) {
    if (Test-Path (Join-Path $s.out 'results.json')) { Log "$($s.name) already scored"; continue }
    Log "scoring $($s.name)"
    & $Py scripts\run_preregistered_study.py run $s.name --out $s.out --jobs 3 2>&1 | ForEach-Object { Log "  $_" }
    if ($LASTEXITCODE -ne 0) { Log "scoring failed for $($s.name)"; continue }
    $res = "docs/research/kite/2026-10-05-$($s.name)/results.json"
    git add -- $res
    git commit -m "research: score $($s.name) once on untouched Kite data$Trailer" -- $res 2>&1 | ForEach-Object { Log "  $_" }
    git push origin $Branch 2>&1 | ForEach-Object { Log "  $_" }
}
Log "round-3 scoring finished"
