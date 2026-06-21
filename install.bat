@echo off
setlocal

set "INTERACTIVE="
set "ACTION=%~1"
set "REPO_DIR=%~dp0"
set "BIN_DIR=%LOCALAPPDATA%\Microsoft\WindowsApps"
set "EXE_SRC=%REPO_DIR%dist\aread.exe"
set "EXE_DST=%BIN_DIR%\aread.exe"
set "CFG_DST=%BIN_DIR%\config.toml"
set "LEGACY_CMD=%BIN_DIR%\aread.cmd"

if "%ACTION%"=="" (
  set "INTERACTIVE=1"
  goto menu
)

if /I "%ACTION%"=="install" goto install
if /I "%ACTION%"=="uninstall" goto uninstall
if /I "%ACTION%"=="status" goto status
goto usage

:menu
echo AI Assistant Reader Installer
echo.
echo This installs the standalone aread.exe so the command works from any
echo shell -- cmd, PowerShell, AND Git Bash (a real .exe resolves everywhere;
echo a .cmd shim does not resolve from Git Bash).
echo.
echo Choose an option:
echo   1. Install or repair global command
echo   2. Uninstall global command
echo   3. Show install status
echo   4. Exit
echo.
choice /C 1234 /N /M "Enter choice [1-4]: "
if errorlevel 4 goto done
if errorlevel 3 set "ACTION=status" & goto status
if errorlevel 2 set "ACTION=uninstall" & goto uninstall
set "ACTION=install"
goto install

:install
rem Build the standalone exe first if it isn't there yet.
if not exist "%EXE_SRC%" (
  echo No dist\aread.exe found -- building it now...
  call "%REPO_DIR%build-exe.bat"
  if errorlevel 1 (
    echo Could not build aread.exe. See messages above.
    goto fail
  )
)
if not exist "%EXE_SRC%" (
  echo Build did not produce "%EXE_SRC%".
  goto fail
)

if not exist "%BIN_DIR%" mkdir "%BIN_DIR%"

copy /Y "%EXE_SRC%" "%EXE_DST%" >nul
if errorlevel 1 (
  echo Failed to copy aread.exe into "%BIN_DIR%".
  goto fail
)

rem A frozen exe reads config.toml from beside itself; ship one if absent so the
rem user can edit model/endpoint without overwriting an existing custom config.
if exist "%REPO_DIR%config.toml" if not exist "%CFG_DST%" copy /Y "%REPO_DIR%config.toml" "%CFG_DST%" >nul

rem Retire the old python .cmd shim (superseded by the exe; invisible to bash).
if exist "%LEGACY_CMD%" del "%LEGACY_CMD%"

echo Installed global command:
echo   aread   (standalone aread.exe)
echo.
echo Installed into:
echo   %BIN_DIR%
echo.
echo config.toml location (edit to change model/endpoint):
echo   %CFG_DST%
echo.
echo This folder is on your Windows user PATH and resolves in cmd, PowerShell,
echo and Git Bash. Open a new terminal if it does not see the command yet.
echo Try:
echo   aread help
goto done

:uninstall
if exist "%EXE_DST%" del "%EXE_DST%"
if exist "%LEGACY_CMD%" del "%LEGACY_CMD%"
if exist "%CFG_DST%" del "%CFG_DST%"
echo Removed aread.exe (and legacy shim / config) from "%BIN_DIR%".
goto done

:status
echo Installer location:
echo   %REPO_DIR%
echo.
echo Install directory:
echo   %BIN_DIR%
echo.
if exist "%EXE_DST%" (
  echo aread.exe: installed
) else (
  echo aread.exe: not installed
)
if exist "%EXE_SRC%" (
  echo built dist\aread.exe: present
) else (
  echo built dist\aread.exe: not built yet ^(run build-exe.bat^)
)
if exist "%LEGACY_CMD%" echo legacy aread.cmd shim also present: %LEGACY_CMD%
echo.
where aread 2>nul
goto done

:usage
echo Usage:
echo   install.bat install
echo   install.bat uninstall
echo   install.bat status
goto fail

:done
if defined INTERACTIVE (
  echo.
  pause
)
exit /b 0

:fail
if defined INTERACTIVE (
  echo.
  pause
)
exit /b 1
