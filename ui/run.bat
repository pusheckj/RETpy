@echo off
setlocal

rem Retirement Monte Carlo - UI launcher (Windows)

echo ======================================================================
echo   Retirement Monte Carlo
echo ======================================================================

python -c "import streamlit" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Streamlit is not installed. Install with:
    echo     pip install -r ui\requirements-ui.txt
    echo.
    exit /b 1
)

cd /d "%~dp0.."
streamlit run ui\app.py %*
