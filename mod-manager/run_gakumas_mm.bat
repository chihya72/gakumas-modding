@echo off
setlocal
cd /d "%~dp0"
dotnet run --project src\GakumasModManager\GakumasModManager.csproj
endlocal
