@echo off
title VeciRed IA - Backend FastAPI
echo ===================================================
echo      INICIANDO BACKEND VECIRED IA (FASTAPI)
echo ===================================================
cd /d "%~dp0"

if not exist .venv (
    echo [1/2] Creando entorno virtual de Python (.venv)...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo [2/2] Instalando librerias requeridas...
    pip install -r requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

echo.
echo ===================================================
echo Servidor backend disponible en:
echo   - Local PC:    http://localhost:8000
echo   - Celular/Red: http://192.168.0.175:8000
echo   - Swagger API: http://192.168.0.175:8000/docs
echo ===================================================
echo.
echo Presiona Ctrl + C para detener el servidor.
echo.
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
