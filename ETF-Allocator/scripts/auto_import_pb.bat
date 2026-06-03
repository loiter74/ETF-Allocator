@echo off
chcp 65001 >nul
title PB Auto Import - Tushare
echo ============================================
echo   PB Auto Import (1 req/hour, ~4.5 hours)
echo ============================================
echo.
python "%~dp0auto_import_pb.py"
echo.
pause
