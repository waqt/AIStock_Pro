@echo off
TITLE AIStock_Pro Backend Service
echo [*] Starting AIStock_Pro Backend...

:: 1. Define Conda Env Path (Automatic Detection)
set CONDA_ENV_PATH=D:\develop_env\python_related\anaconda\Anaconda3\envs\aiteacher

:: 2. Set Environment Variables
set PYTHONNOUSERSITE=1
set PYTHONPATH=%PYTHONPATH%;%~dp0backend

:: 3. Change Directory to Backend
cd /d %~dp0backend

:: 4. Start using the ABSOLUTE path to the environment's python
echo [+] Using Python: %CONDA_ENV_PATH%\python.exe
echo [+] System is starting on http://127.0.0.1:8000
"%CONDA_ENV_PATH%\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload 2> logs/startup_error.log

:: If failed, show log
if %ERRORLEVEL% NEQ 0 (
    echo [!] Startup failed. Error details:
    type logs\startup_error.log
)

pause
