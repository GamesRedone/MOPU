@echo off
REM Run this once on Windows (with Python 3.10+ installed) to build the .exe.
REM The finished exe will appear in the "dist" folder as MO2ProfileUpdater.exe

python -m pip install --upgrade pip
python -m pip install pyinstaller

pyinstaller --onefile --noconsole --name MO2ProfileUpdater ^
  --icon=assets\mopu.ico ^
  --add-data "assets\mopu.ico;assets" ^
  --add-data "assets\mopu_logo_shadow.png;assets" ^
  --add-data "assets\fonts\EBGaramond-VariableFont_wght.ttf;assets\fonts" ^
  --add-data "assets\fonts\OFL.txt;assets\fonts" ^
  --add-data "assets\icons\file-text-blue.png;assets\icons" ^
  --add-data "assets\icons\upload-cloud-blue.png;assets\icons" ^
  --add-data "assets\icons\help-circle-blue.png;assets\icons" ^
  --add-data "assets\icons\FEATHER_LICENSE.txt;assets\icons" ^
  main.py

echo.
echo Done. Find your exe at dist\MO2ProfileUpdater.exe
pause
