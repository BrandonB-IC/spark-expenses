@echo off
REM ======================================================================
REM  Spark Expense Engine — Windows Task Scheduler wrapper
REM  Wired to run weekly: Friday at 4:00 PM
REM  See README.md for the schtasks command that creates the task entry.
REM ======================================================================

set PROJECT_DIR=c:\Users\impro\Brandon_Claude playground\3.0 spark-expenses
set PYTHON=C:\Users\impro\AppData\Local\Programs\Python\Python312-arm64\python.exe
set LOGDIR=%PROJECT_DIR%\scheduler\logs
set LOGFILE=%LOGDIR%\expense_processor.log

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo. >> "%LOGFILE%"
echo [%DATE% %TIME%] === Spark Expense Engine starting === >> "%LOGFILE%"

cd /d "%PROJECT_DIR%"
"%PYTHON%" scheduler\expense_processor.py >> "%LOGFILE%" 2>&1

echo [%DATE% %TIME%] === Finished with exit code %ERRORLEVEL% === >> "%LOGFILE%"
