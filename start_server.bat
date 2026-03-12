@echo off
echo ============================================
echo   Killing old Python/Flask servers...
echo ============================================
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo.
echo ============================================
echo   Starting SmartCam Shield on port 5001...
echo ============================================
cd /d "%~dp0"
call venv\Scripts\activate.bat
python app.py
pause
