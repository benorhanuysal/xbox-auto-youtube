@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Bekciyi bu pencerede calistirir (ne yaptigini gormek icin). Kapatinca durur.
rem Windows acilisinda arka planda calismasi icin: python -m studyo.izle --kur
python -m studyo.izle
pause
