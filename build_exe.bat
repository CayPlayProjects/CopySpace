@echo off
setlocal
cd /d "%~dp0"

rem Find an available Python command. The py launcher is optional.
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
    echo [1/4] Creating build environment...
    %PYTHON_CMD% -m venv .venv
    if errorlevel 1 goto :venv_error
)

set "VENV_PY=.venv\Scripts\python.exe"
echo [2/4] Updating pip...
"%VENV_PY%" -m pip --version >nul 2>&1
if errorlevel 1 "%VENV_PY%" -m ensurepip --upgrade
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :install_error

echo [3/4] Installing CopySpace and PyInstaller dependencies...
"%VENV_PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :install_error
"%VENV_PY%" -m pip install --upgrade pyinstaller
if errorlevel 1 goto :install_error

echo [4/4] Building CopySpace.exe...
"%VENV_PY%" -m PyInstaller --noconfirm --clean --windowed --name CopySpace --collect-all PySide6 copyspace.py
if errorlevel 1 goto :build_error

echo.
echo Build completed successfully.
echo Executable: %CD%\dist\CopySpace\CopySpace.exe
echo You can copy the whole dist\CopySpace folder to another Windows computer.
echo.
pause
goto :end

:no_python
echo.
echo Python was not found on this computer.
echo Install Python 3.10 or newer from https://www.python.org/downloads/windows/
echo IMPORTANT: during installation, enable "Add python.exe to PATH".
echo Then close and reopen this window and run build_exe.bat again.
goto :finish_error

:venv_error
echo.
echo Could not create the build environment.
goto :finish_error

:install_error
echo.
echo Could not install build dependencies. Check your internet connection.
goto :finish_error

:build_error
echo.
echo PyInstaller could not build the application. Review the error above.
goto :finish_error

:finish_error
pause
:end
endlocal
