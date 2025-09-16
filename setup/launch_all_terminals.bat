@echo off
setlocal enabledelayedexpansion

for /L %%i in (1,1,32) do (
    set "folder=C:\MQ45\Terminals\T%%i"
    start "" "!folder!\terminal64.exe" /portable
    timeout /nobreak /t 1 >nul
)
