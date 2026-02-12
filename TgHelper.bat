@echo off
setlocal
cd /d %~dp0
set TGHELPER_DEV=1
"%~dp0.venv\Scripts\python.exe" TgHelper.py %*
