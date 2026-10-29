@echo off
setlocal
cd /d "%~dp0"
echo OpsPilot: verified GitHub publishing launcher
echo Will publish a PUBLIC repository as chinmaygit-lab/OpsPilot.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0PUBLISH_TO_GITHUB.ps1"
set "STATUS=%ERRORLEVEL%"
echo.
if not "%STATUS%"=="0" (
  echo Publishing did not finish. See the reason above.
) else (
  echo Publisher finished successfully. Verify the SUCCESS GitHub link above.
)
echo Press any key to close this window.
pause >nul
exit /b %STATUS%
