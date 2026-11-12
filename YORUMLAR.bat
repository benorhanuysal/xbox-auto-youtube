@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Cevaplanmamis YouTube yorumlari: Claude taslak yazar, sen onaylarsin (Enter = gonder).
python -m studyo.yorumlar
pause
