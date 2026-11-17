@echo off
cd /d "%~dp0"
title Estoque Facil - Inicializacao
where py >nul 2>nul
if %errorlevel% equ 0 (
    py -3 iniciar.py
) else (
    python iniciar.py
)
if errorlevel 1 (
    echo.
    echo Nao foi possivel iniciar. Confira a mensagem acima.
    echo Se Python nao foi encontrado, instale Python 3.12 ou superior.
    pause
)
