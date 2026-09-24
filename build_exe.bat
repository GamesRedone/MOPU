@echo off
REM Run this once on Windows (with Python 3.10+ installed) to build the .exe.
REM The finished exe will appear in the "dist" folder as MOPU.exe

REM Pinned to a specific, already-reviewed PyInstaller release rather than
REM "pip install pyinstaller" -- an unpinned install pulls whatever is newest on
REM PyPI at build time, which means a compromised/typosquatted release could run
REM arbitrary code on the build machine and taint every .exe built afterward.
REM Bump this version deliberately (and re-review) rather than leaving it floating.
python -m pip install --upgrade pip
python -m pip install pyinstaller==6.22.3

pyinstaller --onefile --noconsole --name MOPU ^
  --icon=assets\mopu.ico ^
  --add-data "assets\mopu.ico;assets" ^
  --add-data "assets\mopu_logo_shadow.png;assets" ^
  --add-data "assets\fonts\EBGaramond-VariableFont_wght.ttf;assets\fonts" ^
  --add-data "assets\fonts\OFL.txt;assets\fonts" ^
  --add-data "assets\icons\file-text-blue.png;assets\icons" ^
  --add-data "assets\icons\upload-cloud-blue.png;assets\icons" ^
  --add-data "assets\icons\help-circle-blue.png;assets\icons" ^
  --add-data "assets\icons\refresh-loop-blue.png;assets\icons" ^
  --add-data "assets\icons\FEATHER_LICENSE.txt;assets\icons" ^
  main.py

echo.
echo Done. Find your exe at dist\MOPU.exe
pause
