@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "VENV=%~dp0.venv"
set "PY="

where py >nul 2>&1 && set "PY=py -3"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY goto :kein_python

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto :alte_version

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 goto :kein_tkinter

if not exist "%VENV%\Scripts\python.exe" (
    echo Richte die Arbeitsumgebung ein. Das dauert nur beim ersten Start ...
    %PY% -m venv "%VENV%"
    if errorlevel 1 goto :venv_fehler
)

set "MARKER=%VENV%\.abhaengigkeiten.txt"
set "INSTALL=1"
if exist "%MARKER%" (
    fc /b "%MARKER%" "requirements.txt" >nul 2>&1
    if not errorlevel 1 set "INSTALL=0"
)

if "!INSTALL!"=="1" (
    echo Installiere die benoetigten Pakete ...
    "%VENV%\Scripts\python.exe" -m pip install --upgrade pip --quiet
    "%VENV%\Scripts\python.exe" -m pip install -r requirements.txt --quiet
    if errorlevel 1 goto :pip_fehler
    copy /y "requirements.txt" "%MARKER%" >nul
)

"%VENV%\Scripts\python.exe" -c "import spotify_playlist_generator.gui.app" >nul 2>&1
if errorlevel 1 goto :start_fehler

start "" "%VENV%\Scripts\pythonw.exe" -m spotify_playlist_generator.gui
exit /b 0

:kein_python
echo.
echo   Python wurde nicht gefunden.
echo.
echo   Bitte Python 3.11 oder neuer von https://www.python.org/downloads/ installieren
echo   und beim Installieren den Haken bei "Add Python to PATH" setzen.
echo.
pause
exit /b 1

:alte_version
echo.
echo   Die installierte Python-Version ist zu alt.
echo   Dieses Programm benoetigt Python 3.11 oder neuer.
echo   Neuere Version: https://www.python.org/downloads/
echo.
pause
exit /b 1

:kein_tkinter
echo.
echo   Die Python-Installation enthaelt kein tkinter, das fuer die Oberflaeche noetig ist.
echo   Bitte Python von https://www.python.org/downloads/ neu installieren und dabei
echo   die Option "tcl/tk and IDLE" aktiviert lassen.
echo.
pause
exit /b 1

:venv_fehler
echo.
echo   Die Arbeitsumgebung konnte nicht angelegt werden.
echo   Pruefe, ob der Ordner beschreibbar ist, und starte erneut.
echo.
pause
exit /b 1

:pip_fehler
echo.
echo   Die benoetigten Pakete konnten nicht installiert werden.
echo   Pruefe deine Internetverbindung und starte erneut.
echo.
pause
exit /b 1

:start_fehler
echo.
echo   Das Programm konnte nicht gestartet werden.
echo   Die genaue Fehlermeldung lautet:
echo.
"%VENV%\Scripts\python.exe" -c "import spotify_playlist_generator.gui.app"
echo.
pause
exit /b 1
