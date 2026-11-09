@echo off
chcp 65001 >nul
title MP3 to MP4 변환기 설치
cd /d "%~dp0"
echo.
echo  ===== MP3 → MP4 변환기 설치 =====
echo.

rem 1) 파이썬 찾기
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if defined PY (
  %PY% -c "import sys; sys.exit(0 if sys.version_info>=(3,9) else 1)" >nul 2>nul || set "PY="
)
if not defined PY (
  echo  [1/3] 파이썬이 없어서 설치합니다...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  if errorlevel 1 (
    echo.
    echo  자동 설치에 실패했어요. python.org 에서 파이썬을 설치한 뒤
    echo  설치 첫 화면에서 "Add python.exe to PATH" 를 꼭 체크하고 다시 실행해 주세요.
    start https://www.python.org/downloads/
    pause & exit /b 1
  )
  echo.
  echo  파이썬 설치 완료. 이 창을 닫고 "1_install.bat" 를 한 번 더 실행해 주세요.
  pause & exit /b 0
)
echo  [1/3] 파이썬 확인 완료

rem 2) 필요한 패키지
echo  [2/3] 필요한 패키지 설치 중...
%PY% -m pip install --upgrade --quiet pillow
if errorlevel 1 ( echo  패키지 설치 실패. 인터넷 연결을 확인해 주세요. & pause & exit /b 1 )
%PY% -c "import tkinter" >nul 2>nul || ( echo  파이썬에 tkinter 가 없어요. python.org 설치 파일로 다시 설치해 주세요. & pause & exit /b 1 )

rem 3) ffmpeg (영상 만드는 도구) - 이 폴더 안에 받아 둠
if exist "%~dp0ffmpeg.exe" (
  echo  [3/3] ffmpeg 이미 있음
) else (
  echo  [3/3] ffmpeg 받는 중... ^(약 100MB, 1~2분^)
  powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue';" ^
    "try { Invoke-WebRequest 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile ff.zip }" ^
    "catch { Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile ff.zip };" ^
    "Expand-Archive ff.zip -DestinationPath ff_tmp -Force;" ^
    "Copy-Item (Get-ChildItem ff_tmp -Recurse -Filter ffmpeg.exe | Select-Object -First 1).FullName '.\ffmpeg.exe';" ^
    "Remove-Item ff.zip, ff_tmp -Recurse -Force"
  if not exist "%~dp0ffmpeg.exe" ( echo  ffmpeg 받기 실패. 인터넷 연결을 확인하고 다시 실행해 주세요. & pause & exit /b 1 )
)

rem 바탕화면 바로가기
for /f "delims=" %%i in ('%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"') do set "PYW=%%i"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'MP3 to MP4 변환기.lnk'));" ^
  "$s.TargetPath='%PYW%'; $s.Arguments='\"%~dp0app.py\"'; $s.WorkingDirectory='%~dp0'; $s.Save()" >nul 2>nul

echo.
echo  ===== 설치 완료! =====
echo  바탕화면의 "MP3 to MP4 변환기" 또는 이 폴더의 "2_run.bat" 로 켜세요.
echo.
pause
