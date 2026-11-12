@echo off
rem Kick yayin adresi ve anahtarini OBS'e yazar (bir kez). Anahtar ekranda gorunmez.
cd /d "%~dp0"
python -m studyo.yayin --kur
pause
