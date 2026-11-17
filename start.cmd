@echo off
setlocal
set "MEMO_PYTHONW="
if defined VIRTUAL_ENV if exist "%VIRTUAL_ENV%\Scripts\pythonw.exe" set "MEMO_PYTHONW=%VIRTUAL_ENV%\Scripts\pythonw.exe"
if not defined MEMO_PYTHONW for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined MEMO_PYTHONW set "MEMO_PYTHONW=%%P"
if not defined MEMO_PYTHONW if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe" set "MEMO_PYTHONW=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
if defined MEMO_PYTHONW (
  start "" "%MEMO_PYTHONW%" "%~dp0ake_memo.py"
  exit /b 0
)
py -3 "%~dp0ake_memo.py"
if errorlevel 1 (
  echo Install Python 3.10+ with Tcl/Tk support, then run this launcher again.
  pause
)
