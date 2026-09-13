@echo off
setlocal

set "APP_DIR=C:\Users\alfredo\Desktop\subitissimo"

cd /d "%APP_DIR%" || (
    echo Non trovo la cartella dell'app:
    echo %APP_DIR%
    pause
    exit /b 1
)

title Subitissimo - Monitor annunci
echo Monitor annunci in ascolto. Lascia questa finestra aperta.
echo Gli annunci nuovi li trovi su http://127.0.0.1:8000/monitor/
echo.

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 -u manage.py monitor
) else (
    python -u manage.py monitor
)

echo.
echo Il monitor si e' fermato.
pause
