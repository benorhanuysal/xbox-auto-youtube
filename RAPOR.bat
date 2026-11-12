@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Kanal performans raporu: izlenmeler, izlenme suresi, Claude'un yorumu ve kurguya aktarilan dersler.
python -m studyo.rapor
pause
