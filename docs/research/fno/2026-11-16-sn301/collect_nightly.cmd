@echo off
rem SN330: the verified nightly archive of the tick recorder (read-only on Production; never prints money).
rem Registered as the Windows task "SentinelTickCollect" (weekdays 16:05). Remove: schtasks /Delete /TN SentinelTickCollect /F
cd /d "C:\Users\Urveesh\Desktop\trading-sentinel\docs\research\fno\2026-11-16-sn301"
if not exist logs mkdir logs
echo ==== %DATE% %TIME% >> logs\collect-nightly.log
"C:\Users\Urveesh\sentinel-ml-venv\Scripts\python.exe" fwd2.py collect >> logs\collect-nightly.log 2>&1
echo exit %ERRORLEVEL% >> logs\collect-nightly.log
