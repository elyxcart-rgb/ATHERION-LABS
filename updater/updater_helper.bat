@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  SONIC AI — Update Helper (EXE mode)
REM
REM  Usage: updater_helper.bat <new_exe> <target_exe> <backup_dir>
REM
REM  1. Waits for SONIC-AI.exe to exit
REM  2. Backs up current EXE
REM  3. Copies new EXE over old one
REM  4. Launches new SONIC
REM ─────────────────────────────────────────────────────────────────────────
setlocal enabledelayedexpansion

set "NEW_EXE=%~1"
set "TARGET_EXE=%~2"
set "BACKUP_DIR=%~3"

echo [HELPER] New: %NEW_EXE%
echo [HELPER] Target: %TARGET_EXE%
echo [HELPER] Backup: %BACKUP_DIR%

REM ── Step 1: Wait for SONIC-AI.exe to exit ──────────────────────────────
echo [HELPER] Waiting for SONIC-AI to exit...
:wait_loop
tasklist /FI "IMAGENAME eq SONIC-AI.exe" 2>nul | find /I "SONIC-AI.exe" >nul
if %ERRORLEVEL% equ 0 (
    timeout /t 2 /nobreak >nul
    goto wait_loop
)
echo [HELPER] SONIC-AI has exited.

REM ── Step 2: Verify new EXE exists ─────────────────────────────────────
if not exist "%NEW_EXE%" (
    echo [HELPER] ERROR: New EXE not found: %NEW_EXE%
    exit /b 1
)

REM ── Step 3: Backup current EXE ────────────────────────────────────────
if not "%BACKUP_DIR%"=="" (
    if not exist "%BACKUP_DIR%" mkdir "%BACKUP_DIR%"
    if exist "%TARGET_EXE%" (
        copy /Y "%TARGET_EXE%" "%BACKUP_DIR%\SONIC-AI.exe" >nul 2>&1
        echo [HELPER] Old EXE backed up.
    )
)

REM ── Step 4: Replace EXE ──────────────────────────────────────────────
echo [HELPER] Installing new EXE...
copy /Y "%NEW_EXE%" "%TARGET_EXE%" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [HELPER] EXE replaced successfully.
    goto launch
)

REM Fallback: move trick
echo [HELPER] Direct copy failed, trying move trick...
if exist "%TARGET_EXE%.old" del /f /q "%TARGET_EXE%.old" 2>nul
move /Y "%TARGET_EXE%" "%TARGET_EXE%.old" >nul 2>&1
copy /Y "%NEW_EXE%" "%TARGET_EXE%" >nul 2>&1
if %ERRORLEVEL% equ 0 (
    del /f /q "%TARGET_EXE%.old" 2>nul
    echo [HELPER] EXE replaced via move trick.
    goto launch
)

REM Rollback
echo [HELPER] FAILED - rolling back...
move /Y "%TARGET_EXE%.old" "%TARGET_EXE%" >nul 2>&1
exit /b 1

:launch
REM ── Step 5: Launch new SONIC ──────────────────────────────────────────
echo [HELPER] Launching SONIC AI...
start "" "%TARGET_EXE%"
echo [HELPER] Update complete!
exit /b 0
