@echo off
title VaultCall — Serveur
color 0A
echo.
echo  ========================================
echo   VaultCall - Communication E2EE
echo   USTHB - Projet de fin d'etudes 2026
echo  ========================================
echo.

:: Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    pause & exit /b 1
)

:: Installer les dependances serveur si besoin
echo [1/3] Installation des dependances...
pip install -r server\requirements_server.txt -q
echo       OK

:: Demarrer le serveur FastAPI
echo [2/3] Demarrage du serveur FastAPI sur http://localhost:8000
echo.
echo  Ctrl+C pour arreter le serveur.
echo  L'interface web s'ouvrira automatiquement dans 3 secondes...
echo.

:: Ouvrir le navigateur apres 3s
start /min cmd /c "timeout /t 3 /nobreak >nul && start http://localhost:8000"

:: Lancer uvicorn
cd server
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
pause
