@echo off
REM ==========================================================================
REM  Borges Intelligence - instalar e abrir o painel no Windows
REM  De dois cliques neste arquivo. Na primeira vez ele baixa e instala tudo
REM  (alguns minutos). Nas proximas, atualiza e liga o painel.
REM  Precisa de: Git, Python 3.11+ e Node.js 20+ instalados.
REM ==========================================================================
setlocal
chcp 65001 >nul
title Borges Intelligence - instalacao
set "REPO=https://github.com/Eduardo1299759/borges-intelligence"
REM Contas do Windsor.ai que este painel pode ler, separadas por virgula. Vazio = todas.
set "ACCOUNTS="

echo.
echo  Borges Intelligence
echo  ===================
echo.

REM --- verificar programas necessarios -------------------------------------
where git >nul 2>nul
if errorlevel 1 goto :nogit
where node >nul 2>nul
if errorlevel 1 goto :nonode

REM Prefere versoes estaveis do Python quando houver mais de uma instalada.
set "PY="
for %%V in (3.13 3.12 3.14 3.11 3) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=py -%%V"
  )
)
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY goto :nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto :nopython

REM --- desligar versoes antigas: no Windows elas travam arquivos de .venv ----
echo  Desligando versoes antigas do painel e da API que ainda estejam abertas...
powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 3000,3001,8000 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*app.worker*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
timeout /t 3 /nobreak >nul

REM --- localizar ou baixar o projeto ---------------------------------------
if exist "%~dp0backend\pyproject.toml" (
  set "ROOT=%~dp0"
) else (
  set "ROOT=%~dp0borges-intelligence\"
)
if not exist "%ROOT%backend\pyproject.toml" (
  echo [1/6] Baixando o projeto do GitHub. Se pedir, faca login no GitHub na janela que abrir.
  git clone "%REPO%" "%~dp0borges-intelligence"
  if errorlevel 1 goto :fail
) else (
  echo [1/6] Projeto encontrado. Buscando atualizacoes...
  git -C "%ROOT%." pull --ff-only
)

REM --- backend -------------------------------------------------------------
cd /d "%ROOT%backend"
if not exist ".venv\Scripts\python.exe" (
  echo [2/6] Criando o ambiente Python...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
) else (
  echo [2/6] Ambiente Python encontrado.
)
echo [3/6] Instalando dependencias do backend - pode demorar na primeira vez...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check --prefer-binary --progress-bar off -e .
if errorlevel 1 goto :piperror
echo [4/6] Preparando configuracao e banco de dados...
".venv\Scripts\python.exe" -m app.cli init-env --accounts "%ACCOUNTS%" >nul
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m app.cli init-db
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m app.cli seed
if errorlevel 1 goto :fail
start "Borges API (nao feche)" /D "%ROOT%backend" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --port 8000"

REM --- frontend ------------------------------------------------------------
cd /d "%ROOT%frontend"
if not exist "node_modules\.bin\next.cmd" (
  echo [5/6] Instalando dependencias do painel - pode demorar na primeira vez...
  call npm ci --no-audit --no-fund
  if errorlevel 1 goto :fail
) else (
  echo [5/6] Dependencias do painel encontradas.
)
echo [6/6] Ligando o painel...
start "Borges Painel (nao feche)" /D "%ROOT%frontend" cmd /k "npm run dev"

cd /d "%ROOT%backend"
echo.
echo  Aguardando a API responder...
".venv\Scripts\python.exe" -m app.cli wait-api
if errorlevel 1 echo  [AVISO] A API nao respondeu. Veja se ha erro na janela "Borges API" e mande um print para o Claude.
start "Borges Automacoes (nao feche)" /D "%ROOT%backend" cmd /k ".venv\Scripts\python.exe -m app.worker"
echo.
".venv\Scripts\python.exe" -m app.cli login-info
echo.
echo  Pronto. O painel vai abrir no navegador: http://localhost:3000
echo  Para desligar, feche as janelas "Borges API", "Borges Painel" e "Borges Automacoes".
timeout /t 8 /nobreak >nul
start "" http://localhost:3000
echo.
pause
exit /b 0

REM --- mensagens de erro ---------------------------------------------------
:nogit
echo [ERRO] Git nao encontrado. Instale em https://git-scm.com/download/win e rode este arquivo de novo.
goto :fail

:nonode
echo [ERRO] Node.js nao encontrado. Instale a versao LTS em https://nodejs.org e rode este arquivo de novo.
goto :fail

:nopython
echo [ERRO] Python 3.11 ou mais novo nao encontrado.
echo        Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
goto :fail

:piperror
echo.
echo  Falha ao instalar as dependencias do Python.
echo  - Se o erro acima falar em arquivo "sendo usado por outro processo": reinicie o computador e rode de novo.
echo  - Se falar em "Microsoft Visual C++": instale o Python 3.13 em https://www.python.org/downloads/,
echo    apague a pasta "backend\.venv" e rode este arquivo de novo.
goto :fail

:fail
echo.
echo  A instalacao parou por causa do erro acima. Tire um print desta janela e mande para o Claude.
pause
exit /b 1
