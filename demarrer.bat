@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Lance d'abord les commandes d'installation du README.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" bot.py
pause
