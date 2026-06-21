@echo off
setlocal
rem Build a standalone, single-file aread.exe (no Python needed to run it).
rem Output: dist\aread.exe  -- the artifact you upload to a GitHub Release.

set "REPO_DIR=%~dp0"

echo Installing/refreshing PyInstaller...
py -3 -m pip install --quiet --upgrade pyinstaller
if errorlevel 1 (
  echo Failed to install PyInstaller. Is Python/pip available?
  exit /b 1
)

echo Building aread.exe ...
py -3 -m PyInstaller ^
  --onefile ^
  --console ^
  --name aread ^
  --paths "%REPO_DIR%src" ^
  --collect-submodules ai_assistant_reader ^
  --distpath "%REPO_DIR%dist" ^
  --workpath "%REPO_DIR%build" ^
  --specpath "%REPO_DIR%build" ^
  --noconfirm ^
  "%REPO_DIR%aread_entry.py"
if errorlevel 1 (
  echo Build failed.
  exit /b 1
)

rem Ship a default config.toml next to the exe so users can edit it.
if exist "%REPO_DIR%config.toml" copy /Y "%REPO_DIR%config.toml" "%REPO_DIR%dist\config.toml" >nul

echo.
echo Built: %REPO_DIR%dist\aread.exe
echo A copy of config.toml was placed next to it (edit to change model/endpoint).
echo Upload dist\aread.exe (and optionally config.toml) to a GitHub Release.
endlocal
