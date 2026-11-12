@echo off
rem Telegram kumandasi: BotFather jetonunu sorar, bota /start yazan hesabinla eslestirir (bir kez).
cd /d "%~dp0"
python -m studyo.telegram --kur
pause
