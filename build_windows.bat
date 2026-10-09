@echo off
REM Build a Windows app folder:  dist\KnowledgeVault\KnowledgeVault.exe
python -m venv .venv || goto :err
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt || goto :err
python -m pytest -q || goto :err
pyinstaller knowledge_vault.spec --noconfirm --clean || goto :err
echo.
echo Built: dist\KnowledgeVault\KnowledgeVault.exe
echo Optional installer: open installer.iss in Inno Setup and press Compile.
goto :eof
:err
echo Build failed.
exit /b 1
