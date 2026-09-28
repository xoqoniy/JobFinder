@echo off
title JobFinder - Autonomous Job Application System
cd /d "%~dp0"
echo ===================================================
echo           Starting JobFinder Dashboard
echo ===================================================
echo.
echo Dashboard URL: http://localhost:5000
echo.
python run.py %*
pause
