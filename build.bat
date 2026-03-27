@echo off
echo =========================================
echo Compiling DABMAN i200 Control to .exe
echo =========================================

REM Clean up old build folders to ensure a fresh compile
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM Run PyInstaller
REM --noconfirm: Overwrite output directory without asking
REM --onefile: Bundle everything into a single .exe
REM --windowed: Hide the background command prompt console
REM --icon: Set the executable's favicon
REM --name: Set the output file name

pyinstaller --noconfirm --onefile --windowed --icon "icon.ico" --name "DABMAN_Control" "src\main.py"

echo =========================================
echo Build Complete!
echo Your executable is located in the "dist" folder.
echo =========================================
pause
