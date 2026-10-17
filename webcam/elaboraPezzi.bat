@echo off
REM Scan a folder of JPG photos of a white-rectangle/black-frame document,
REM correct perspective distortion, crop, resize and save as PNG.
REM
REM FOLDER, INDEX and DESTINATION are read from config.txt (next to this
REM .bat). An optional command-line argument overrides FOLDER; INDEX and
REM DESTINATION always come from config.txt regardless.
setlocal

set "SCRIPT_DIR=%~dp0\script"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

"%PYTHON%" "%SCRIPT_DIR%scan_card.py" --config "%SCRIPT_DIR%config.txt" %1
