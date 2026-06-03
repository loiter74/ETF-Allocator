@echo off
title ETF Allocator
cd /d "%~dp0"

echo ================================================
echo   ETF Allocator v1.2
echo   API:   http://localhost:8000
echo   Panel: http://localhost:5173
echo ================================================
echo.

python start.py
pause
