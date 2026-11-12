@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === xbox-auto-youtube kurulum ===

python --version >nul 2>nul
if errorlevel 1 (
  echo Python kuruluyor...
  winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  echo.
  echo Python kuruldu. Bu pencereyi kapatip KUR.bat'i TEKRAR calistirin.
  pause
  exit /b
)

ffmpeg -version >nul 2>nul
if errorlevel 1 (
  echo ffmpeg kuruluyor...
  winget install -e --id Gyan.FFmpeg --accept-source-agreements --accept-package-agreements
)

python -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto hata

if not exist ayarlar.json copy ayarlar.ornek.json ayarlar.json >nul
echo.
echo [OK] Kurulum bitti. Acilan ayarlar.json'a OBS kayit klasorunu ve LunaTranslator userconfig yolunu yazip kaydedin.
echo      Yollarda \ yerine \\ yazin. Ornek: "C:\\Users\\ad\\Videos"
notepad ayarlar.json
pause
exit /b

:hata
echo.
echo [HATA] Kutuphaneler kurulamadi. Internet baglantisini kontrol edip tekrar deneyin.
pause