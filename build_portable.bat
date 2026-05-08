@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\build_portable.ps1" -CloudflaredPath "C:\Users\26043\Desktop\cloudflared-windows-amd64.exe"
pause
