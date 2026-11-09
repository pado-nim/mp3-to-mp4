@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist "%~dp0ffmpeg.exe" ( echo 먼저 "1_install.bat" 를 실행해 주세요. & pause & exit /b 1 )
where pyw >nul 2>nul && ( start "" pyw -3 "%~dp0app.py" & exit /b 0 )
where pythonw >nul 2>nul && ( start "" pythonw "%~dp0app.py" & exit /b 0 )
python "%~dp0app.py"
