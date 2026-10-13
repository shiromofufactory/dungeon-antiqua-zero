@echo off
setlocal
python -B "%~dp0scripts\build_windows.py" %*
exit /b %errorlevel%
