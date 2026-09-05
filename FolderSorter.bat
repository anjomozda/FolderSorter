@echo off
rem Opens the FolderSorter window.
rem
rem Double-click it, or drop it into the Windows SendTo folder and a
rem right-clicked folder arrives here as %1. %~dp0 is this file's own
rem folder, so it works no matter where it is launched from.

where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "%~dp0gui.py" %*
) else (
    start "" python "%~dp0gui.py" %*
)
