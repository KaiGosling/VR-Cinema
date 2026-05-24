@echo off
title VR Cinema - Setup
color 0B
echo.
echo  ============================================
echo   VR CINEMA - Setup Installer
echo  ============================================
echo.

:: Store script directory without trailing backslash
set SCRIPTDIR=%~dp0
set SCRIPTDIR=%SCRIPTDIR:~0,-1%

:: ── Install Spacedesk Driver ─────────────────────────────────────────────────
echo  [1/8] Spacedesk DRIVER...

set MSI_NAME=spacedesk_driver_Win_11_64_v2219.msi
set MSI_PATH=%SCRIPTDIR%\%MSI_NAME%

reg query "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "spacedesk" >nul 2>&1
if %errorlevel% == 0 (
    echo       Already installed — skipping.
    goto :python
)

reg query "HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall" /s /f "spacedesk" >nul 2>&1
if %errorlevel% == 0 (
    echo       Already installed — skipping.
    goto :python
)

if not exist "%MSI_PATH%" (
    echo  [!] Spacedesk MSI not found: %MSI_PATH%
    echo      Make sure %MSI_NAME% is in the same folder as this script.
    echo.
    pause
    exit /b 1
)

echo       Found MSI — running silent install...
msiexec /i "%MSI_PATH%" /qn /norestart
if %errorlevel% neq 0 (
    echo  [!] Spacedesk install failed (exit code: %errorlevel%)
    echo      Try running this script as Administrator.
    echo.
    pause
    exit /b 1
)
echo       Spacedesk installed successfully!

:: ── Find Python ──────────────────────────────────────────────────────────────
:python
echo.
echo  [2/8] Looking for Python...

py --version >nul 2>&1
if %errorlevel% == 0 (
    set PYCMD=py
    for /f "tokens=*" %%i in ('py --version') do set PYVER=%%i
    echo       Found: %PYVER%
    goto :pip
)

python --version >nul 2>&1
if %errorlevel% == 0 (
    set PYCMD=python
    for /f "tokens=*" %%i in ('python --version') do set PYVER=%%i
    echo       Found: %PYVER%
    goto :pip
)

echo.
echo  [!] Python not found on this PC.
echo      Please install Python first: https://www.python.org/downloads/
echo      During install, tick "Add Python to PATH"
echo.
pause
start https://www.python.org/downloads/
exit /b 1

:: ── Upgrade pip ──────────────────────────────────────────────────────────────
:pip
echo.
echo  [3/8] Upgrading pip...
%PYCMD% -m pip install --upgrade pip --quiet
echo       Done.

:: ── Install packages ─────────────────────────────────────────────────────────
echo.
echo  [4/8] Checking Python packages...
echo.

call :ensure pillow     Pillow
call :ensure pywin32    pywin32
call :ensure numpy      numpy
call :ensure screeninfo screeninfo
call :ensure mss        mss

:: pywin32 post-install
echo.
echo  [5/8] Running pywin32 post-install...
for /f "delims=" %%L in ('%PYCMD% -c "import sys; print(sys.prefix)"') do set PYPREFIX=%%L
%PYCMD% "%PYPREFIX%\Scripts\pywin32_postinstall.py" -install >nul 2>&1
echo       Done.

:: ── Install PyInstaller ──────────────────────────────────────────────────────
echo.
echo  [6/8] Installing PyInstaller...
%PYCMD% -m pip install pyinstaller --quiet
echo       Done.

:: ── Build EXE ────────────────────────────────────────────────────────────────
echo.
echo  [7/8] Building VR Cinema.exe ...
echo       This may take a minute, please wait...
echo.

:: Remove old EXE first so the launcher always runs the fresh build
if exist "%SCRIPTDIR%\VR Cinema.exe" (
    echo       Removing old VR Cinema.exe...
    del /f /q "%SCRIPTDIR%\VR Cinema.exe"
)
:: Also clear old build cache so PyInstaller recompiles cleanly
if exist "%SCRIPTDIR%\build" (
    rmdir /s /q "%SCRIPTDIR%\build"
)

for /f "delims=" %%P in ('%PYCMD% -c "import sys,os; print(os.path.join(sys.prefix, chr(83)+chr(99)+chr(114)+chr(105)+chr(112)+chr(116)+chr(115), chr(112)+chr(121)+chr(105)+chr(110)+chr(115)+chr(116)+chr(97)+chr(108)+chr(108)+chr(101)+chr(114)+chr(46)+chr(101)+chr(120)+chr(101)))"') do set PYINST=%%P

if not exist "%PYINST%" (
    set PYINST=%LOCALAPPDATA%\Python\pythoncore-3.14-64\Scripts\pyinstaller.exe
)

if not exist "%PYINST%" (
    echo  [!] Could not find pyinstaller.exe — skipping EXE build.
    goto :done
)

"%PYINST%" --noconsole --onefile --name "VR Cinema" --icon="%SCRIPTDIR%\assets\icon.ico" --add-data "%SCRIPTDIR%\assets;assets" --distpath "%SCRIPTDIR%" --workpath "%SCRIPTDIR%\build" --specpath "%SCRIPTDIR%" "%SCRIPTDIR%\vr_cinema.py"

if %errorlevel% neq 0 (
    echo.
    echo  [!] EXE build failed. You can still run:  py vr_cinema.py
    goto :done
)
echo.
echo       VR Cinema.exe built successfully!
echo       Location: %SCRIPTDIR%\VR Cinema.exe

:: ── Done ─────────────────────────────────────────────────────────────────────
:done
echo.
echo  [8/8] All components ready!
echo.
echo  ============================================
echo   Setup complete!
echo  ============================================
echo.
echo   Spacedesk   - virtual display driver
echo   Pillow      - screen image processing
echo   pywin32     - game window capture
echo   numpy       - faster frame rendering
echo   screeninfo  - monitor detection
echo   mss         - screen capture
echo   PyInstaller - app compiler
echo.
echo   EXE location:  VR Cinema.exe (same folder)
echo   Or run directly:  py vr_cinema.py
echo.
pause

choice /C YN /M "  Launch VR Cinema now?"
if %errorlevel% == 1 (
    if exist "%SCRIPTDIR%\VR Cinema.exe" (
        start "" "%SCRIPTDIR%\VR Cinema.exe"
    ) else (
        %PYCMD% "%SCRIPTDIR%\vr_cinema.py"
    )
)
exit /b 0

:: ── Subroutine ───────────────────────────────────────────────────────────────
:ensure
%PYCMD% -c "import %~1" >nul 2>&1
if %errorlevel% == 0 (
    echo       %~2 already installed — skipping.
    exit /b 0
)
echo       Installing %~2...
%PYCMD% -m pip install %~2 --quiet
if %errorlevel% neq 0 (
    echo.
    echo  [!] Failed to install %~2
    echo      Try right-clicking setup.bat and Run as Administrator.
    echo.
    pause
    exit /b 1
)
echo       %~2 installed OK.
exit /b 0