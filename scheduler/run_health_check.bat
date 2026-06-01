@echo off
REM ======================================================================
REM  Spark Expense Engine — Drive auth health check wrapper
REM  Wired to run daily. Emails Brandon if the Drive token is dead, so a
REM  revoked/expired token surfaces BEFORE the Friday 4pm processor run.
REM ======================================================================

set PROJECT_DIR=c:\Users\impro\Brandon_Claude playground\3.0 spark-expenses
set PYTHON=C:\Users\impro\AppData\Local\Programs\Python\Python312-arm64\python.exe
set LOGDIR=%PROJECT_DIR%\scheduler\logs
set LOGFILE=%LOGDIR%\health_check.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo. >> "%LOGFILE%"
echo [%DATE% %TIME%] === Health check starting === >> "%LOGFILE%"

cd /d "%PROJECT_DIR%"
"%PYTHON%" -m scheduler.health_check >> "%LOGFILE%" 2>&1

echo [%DATE% %TIME%] === Finished with exit code %ERRORLEVEL% === >> "%LOGFILE%"
