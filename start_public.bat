@echo off
chcp 65001 >nul
cd /d "%~dp0"
set GALAXY_PORTABLE=1
set GALAXY_DATA_DIR=%~dp0workspace
runtime\python\python.exe portable_launcher.py public
pause
