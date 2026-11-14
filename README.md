@echo off
setlocal
cd /d "%~dp0"

if not exist avatars mkdir avatars

echo === 1/3  Installing libraries ===
python -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo === 2/3  Building MyAssistant ===
python -m PyInstaller --noconfirm --clean --noconsole --onedir --name MyAssistant ^
  --add-data "avatars;avatars" ^
  --hidden-import comtypes --hidden-import pycaw --hidden-import screen_brightness_control ^
  --hidden-import pyttsx3.drivers --hidden-import pyttsx3.drivers.sapi5 ^
  --hidden-import pywhatkit --hidden-import speech_recognition ^
  assistant.py
if errorlevel 1 goto :fail

echo === 3/3  Making a zip you can share ===
copy /y README_USERS.txt dist\MyAssistant\README.txt >nul
powershell -NoProfile -Command "Compress-Archive -Path 'dist\MyAssistant' -DestinationPath 'dist\MyAssistant.zip' -Force"

echo.
echo DONE.
echo   Run it:    dist\MyAssistant\MyAssistant.exe
echo   Share it:  dist\MyAssistant.zip
pause
exit /b 0

:fail
echo.
echo BUILD FAILED. Scroll up and read the red error text.
pause
exit /b 1
