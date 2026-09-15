@echo off
chcp 65001 >nul
cd /d %~dp0
echo [1/2] Cleaning old build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
echo [2/2] Building PromptForge.exe ...
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name PromptForge ^
  --icon "assets\icon.ico" ^
  --add-data "assets\icon.ico;assets" ^
  --add-data "assets\icon.png;assets" ^
  --add-data "promptforge\strategies;promptforge\strategies" ^
  --add-data "promptforge\templates_builtin;promptforge\templates_builtin" ^
  run.py
if %errorlevel% neq 0 (
  echo BUILD FAILED
  exit /b 1
)
echo.
echo BUILD OK: dist\PromptForge.exe
dir dist\PromptForge.exe