@echo off
set LOGFILE="C:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\scheduler\logs\git_autocommit.log"
if not exist "C:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\scheduler\logs" mkdir "C:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\scheduler\logs"
echo [%DATE% %TIME%] Starting spark-expenses git autocommit >> %LOGFILE%
cd /d "C:\Users\impro\Brandon_Claude playground\3.0 spark-expenses"
"C:\Users\impro\AppData\Local\Programs\Python\Python312-arm64\python.exe" "C:\Users\impro\Brandon_Claude playground\3.0 spark-expenses\scheduler\git_autocommit.py" >> %LOGFILE% 2>&1
echo [%DATE% %TIME%] Finished with exit code %ERRORLEVEL% >> %LOGFILE%
