@echo off
pip install -r requirements.txt
pyinstaller --noconsole --onefile --name MyAssistant --add-data "avatars;avatars" assistant.py
echo Done. Your app is in the dist\ folder: dist\MyAssistant.exe
pause
