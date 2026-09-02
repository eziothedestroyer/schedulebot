@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pyinstaller -r requirements.txt
if errorlevel 1 exit /b 1
py -m PyInstaller --clean --noconfirm ScheduleBot.spec
if errorlevel 1 exit /b 1
certutil -hashfile dist\ScheduleBot.exe SHA256 > dist\ScheduleBot.exe.sha256
if errorlevel 1 exit /b 1
echo Built: dist\ScheduleBot.exe
echo Checksum: dist\ScheduleBot.exe.sha256
