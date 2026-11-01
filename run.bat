@echo off
setlocal
cd /d "%~dp0"

rem Find an available Python command. Prefer the regular command over the py launcher.
set "PYTHON_CMD="
where python >nul 2>&1
if not errorlevel 1 (
    python --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (
    where python3 >nul 2>&1
    if not errorlevel 1 (
        python3 --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python3"
    )
)
if not defined PYTHON_CMD (
    where py >nul 2>&1
    if not errorlevel 1 (
        py --version >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=py"
    )
)

if not defined PYTHON_CMD goto :no_python

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating virtual environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :venv_error
)

 echo [2/3] Installing required packages...
".venv\Scripts\python.exe" -m pip --version >nul 2>&1
if errorlevel 1 ".venv\Scripts\python.exe" -m ensurepip --upgrade
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :install_error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error

echo [3/3] Starting CopySpace...
".venv\Scripts\python.exe" copyspace.py
if errorlevel 1 goto :run_error
goto :end

:no_python
echo.
echo Python was not found on this computer.
echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
echo IMPORTANT: during installation, enable "Add python.exe to PATH".
echo Then close and reopen this window and run run.bat again.
goto :finish_error

:venv_error
echo.
echo Could not create the virtual environment.
echo Check that Python 3.10 or newer is installed correctly.
goto :finish_error

:install_error
echo.
echo Could not install dependencies. Check your internet connection and try again.
goto :finish_error

:run_error
echo.
echo CopySpace stopped with an error. Review the message above.
goto :finish_error

:finish_error
pause
:end
endlocal
