@echo off
title VeciRed IA - Backend FastAPI
echo ===================================================
echo      INICIANDO BACKEND VECIRED IA (FASTAPI)
echo ===================================================
cd /d "%~dp0"
call .venv\Scripts\activate.bat
echo Servidor backend disponible en:
echo   - Local:     http://localhost:8000
echo   - Swagger:   http://localhost:8000/docs
echo   - Red local: http://192.168.1.33:8000
echo.
echo Presiona Ctrl + C para detener el servidor.
echo.
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
pause
