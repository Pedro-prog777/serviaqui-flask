@echo off
setlocal
cd /d "%~dp0"

echo 
echo   ServiAqui - Inicializacao local Windows
echo 

if not exist ".venv" (
    echo Criando ambiente virtual...
    py -m venv .venv
)

call .venv\Scripts\activate
if errorlevel 1 (
    echo Falha ao ativar o ambiente virtual.
    pause
    exit /b 1
)

echo Atualizando o pip...
python -m pip install --upgrade pip

echo Instalando dependencias...
pip install -r requirements.txt
if errorlevel 1 (
    echo Falha ao instalar dependencias.
    pause
    exit /b 1
)

if not exist "instance" mkdir instance

echo Iniciando o site...
start "Servidor ServiAqui" cmd /k "cd /d %~dp0 && call .venv\Scripts\activate && python app.py"
timeout /t 5 /nobreak >nul
start "" http://127.0.0.1:8000
endlocal
