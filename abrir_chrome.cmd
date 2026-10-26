@echo off
setlocal

REM Chrome com depuracao somente local e perfil ISOLADO do perfil pessoal.
set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not exist "%CHROME%" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if not exist "%CHROME%" (
    echo ERRO: Google Chrome nao encontrado.
    echo Consulte o README para instalar o navegador.
    pause
    exit /b 1
)

set "PERFIL=%LOCALAPPDATA%\SOMA_SANTANDER_DEBUG"
echo Abrindo o Chrome para login manual no Santander...
echo Porta: 9222 - somente localhost
start "Chrome Santander" "%CHROME%" --remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir="%PERFIL%" --no-first-run "https://www.parceirosantander.com.br/spa-base/"

if errorlevel 1 (
    echo Nao foi possivel iniciar o Chrome.
    pause
    exit /b 1
)
echo.
echo Faca o login e o 2FA no Chrome e execute python main.py em outro terminal.
endlocal
