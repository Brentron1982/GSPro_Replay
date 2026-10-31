@echo off
setlocal
title GSPro Replay - setup
cd /d "%~dp0"

if not exist "%~dp0gspro_replay\gui.py" goto notunzipped

rem --- find Python (python on PATH, or the py launcher) ---
set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY goto nopython
echo Using:
%PY% --version
%PY% -c "import tkinter" >nul 2>nul || goto notk

echo.
echo [1/3] Installing GSPro Replay and its libraries (a few minutes)...
%PY% -m pip install --upgrade pip
%PY% -m pip install -e ".[lidar]"
if errorlevel 1 goto failed

echo.
echo [2/3] Downloading the browser used to render videos...
%PY% -m playwright install chromium
if errorlevel 1 echo    Browser download failed - you can still make videos with the Export MP4 button inside the replay.

echo.
echo [3/3] Creating a desktop shortcut...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Desktop')+'\GSPro Replay.lnk'); $s.TargetPath='%~dp0GSPro Replay.bat'; $s.WorkingDirectory='%~dp0'; $s.Save()"

echo.
echo ============================================================
echo  All done. Start it with the "GSPro Replay" desktop shortcut
echo  or by double-clicking "GSPro Replay.bat" in this folder.
echo ============================================================
pause
exit /b 0

:notunzipped
echo.
echo  This is running from inside the zip file.
echo.
echo  1. Close this window.
echo  2. Right-click gspro-replay.zip and choose "Extract All...".
echo  3. Open the extracted gspro-replay folder and run
echo     "Install (run once).bat" from there.
echo.
pause
exit /b 1

:nopython
echo.
echo  Python was not found.
echo  Install Python 3.12 from https://www.python.org/downloads/
echo  and on the first installer screen tick "Add python.exe to PATH".
echo  Then run this file again.
echo.
pause
exit /b 1

:notk
echo.
echo  This Python is missing tkinter, which the app window needs.
echo  Re-run the Python installer, choose "Modify", make sure
echo  "tcl/tk and IDLE" is ticked, then run this file again.
echo.
pause
exit /b 1

:failed
echo.
echo  Installation failed - scroll up to see the error.
echo  Copy the red/last lines and send them over for help.
echo.
pause
exit /b 1
