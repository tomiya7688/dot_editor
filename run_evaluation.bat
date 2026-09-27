@echo off
"%~dp0.venv\Scripts\python.exe" "%~dp0scripts\evaluate.py"
if errorlevel 1 exit /b %errorlevel%
pushd "%~dp0"
"%~dp0.venv\Scripts\python.exe" -m unittest discover -s tests
set result=%errorlevel%
popd
exit /b %result%
