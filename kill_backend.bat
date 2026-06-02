@echo off
echo [*] Finding zombie processes on port 8000...
set "found="
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do (
    echo [*] Found PID: %%a, killing process tree...
    taskkill /F /T /PID %%a
    set "found=1"
)
if not defined found (
    echo [!] No processes found on port 8000.
) else (
    echo [+] Cleaned up successfully.
)
echo.
pause
