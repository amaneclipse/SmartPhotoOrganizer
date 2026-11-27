@echo off
setlocal
if not exist ".venv\Scripts\python.exe" (
  echo Create a virtual environment first: python -m venv .venv
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python -m PyInstaller --clean --noconfirm pyinstaller.spec
if errorlevel 1 exit /b 1
echo Build complete: dist\SmartPhotoOrganizer\SmartPhotoOrganizer.exe
