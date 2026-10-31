@echo off
setlocal
title GSPro Replay
cd /d "%~dp0"

if not exist "%~dp0gspro_replay\gui.py" goto notunzipped

set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY goto nopython

rem --- make sure everything is installed ---
%PY% -c "import tkinter, numpy, scipy, shapely, PIL, gspro_replay.gui" 2> "%TEMP%\gspro_replay_check.txt"
if errorlevel 1 goto notinstalled

rem --- run the app; this window stays open if anything goes wrong ---
echo Starting GSPro Replay... (keep this window open; it closes with the app)
%PY% -m gspro_replay gui
if errorlevel 1 (
  echo.
  echo  GSPro Replay stopped with an error - see the messages above.
  echo  Please copy them and send them over.
  echo.
  pause
)
exit /b 0

:notunzipped
echo.
echo  This is running from inside the zip file.
echo  Right-click gspro-replay.zip, choose "Extract All...", then open
echo  the extracted folder and run "Install (run once).bat" first.
echo.
pause
exit /b 1

:nopython
echo.
echo  Python was not found. Install Python 3.12 from python.org
echo  (tick "Add python.exe to PATH"), then run "Install (run once).bat".
echo.
pause
exit /b 1

:notinstalled
echo.
echo  GSPro Replay isn't fully installed yet. The problem was:
echo.
type "%TEMP%\gspro_replay_check.txt"
echo.
echo  Run "Install (run once).bat" in this folder, then try again.
echo.
pause
exit /b 1
