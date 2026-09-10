@echo off
setlocal

set "APP_DIR=C:\Users\alfredo\Desktop\subitissimo"
set "APP_URL=http://127.0.0.1:8000/"

cd /d "%APP_DIR%" || (
    echo Non trovo la cartella dell'app:
    echo %APP_DIR%
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $client = New-Object Net.Sockets.TcpClient; $result = $client.BeginConnect('127.0.0.1', 8000, $null, $null); if ($result.AsyncWaitHandle.WaitOne(300)) { $client.EndConnect($result); $client.Close(); exit 0 } $client.Close(); exit 1 } catch { exit 1 }"

if %ERRORLEVEL% EQU 0 (
    start "" "%APP_URL%"
    exit /b 0
)

start "" powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process '%APP_URL%'"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 manage.py runserver 127.0.0.1:8000
) else (
    python manage.py runserver 127.0.0.1:8000
)

echo.
echo L'app si e' chiusa oppure c'e' stato un errore.
pause
