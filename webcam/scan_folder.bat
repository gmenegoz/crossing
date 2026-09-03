@echo off
REM Scan a folder of JPG photos of a white-rectangle/black-frame document,
REM correct perspective distortion, crop, resize and save as PNG.
REM The folder to scan is read from config.txt (next to this .bat), as a
REM line formatted: FOLDER=C:\path\to\folder
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "CONFIG_FILE=%SCRIPT_DIR%config.txt"

if exist "%SCRIPT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

if not exist "%CONFIG_FILE%" (
    echo Error: config.txt not found next to scan_folder.bat >&2
    echo Create it with a line: FOLDER=C:\path\to\folder >&2
    exit /b 2
)

set "FOLDER="
for /f "usebackq tokens=1,* delims==" %%A in ("%CONFIG_FILE%") do (
    if /i "%%A"=="FOLDER" set "FOLDER=%%B"
)

if not defined FOLDER (
    echo Error: config.txt has no FOLDER=... line >&2
    exit /b 2
)

if not exist "%FOLDER%\" (
    echo Error: '%FOLDER%' is not a directory >&2
    exit /b 2
)

set /a processed=0
set /a skipped_failed=0

for %%F in ("%FOLDER%\*.jpg") do (
    "%PYTHON%" "%SCRIPT_DIR%scan_card.py" "%%F"
    if !errorlevel! equ 0 (
        set /a processed+=1
    ) else (
        set /a skipped_failed+=1
    )
)

echo.
echo Done: %processed% processed, %skipped_failed% skipped ^(failed^)
