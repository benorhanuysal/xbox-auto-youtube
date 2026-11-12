@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python -m studyo %*
if errorlevel 1 (
  echo.
  echo [HATA] Yukaridaki mesaja bakin. "ffmpeg bulunamadi" ise bilgisayari yeniden baslatin.
)
pause