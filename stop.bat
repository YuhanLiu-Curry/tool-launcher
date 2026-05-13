@echo off
taskkill /f /im python.exe 2>nul
echo 工具箱已停止
timeout /t 2 >nul
