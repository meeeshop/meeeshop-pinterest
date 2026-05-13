@echo off
REM Pinterest Automation Test Runner — Windows Batch
REM Run: test_product_and_video_pins.py with proper environment setup

REM Colors for output
setlocal enabledelayedexpansion

echo.
echo ================================================================
echo     PINTEREST AUTOMATION — PRODUCT & VIDEO PIN TEST
echo ================================================================
echo.

REM Check if venv exists
if not exist "venv\" (
    echo [ERROR] Virtual environment not found!
    echo.
    echo Run this first:
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo.
    exit /b 1
)

REM Activate venv
call venv\Scripts\activate.bat

REM Check if .env exists
if not exist ".env" (
    echo [ERROR] .env file not found!
    echo.
    echo Create .env file with:
    echo   PINTEREST_EMAIL=your_email@gmail.com
    echo   PINTEREST_PASSWORD=your_password
    echo   SHOPIFY_STORE_URL=https://meeeshop.myshopify.com
    echo   SHOPIFY_ACCESS_TOKEN=shpat_xxxxx
    echo   STORE_BASE_URL=https://us.meeeshop.com
    echo   GEMINI_API_KEY=AIza...
    echo.
    exit /b 1
)

echo [OK] Environment ready
echo.
echo Starting test: test_product_and_video_pins.py
echo.

REM Run test
python test_product_and_video_pins.py

REM Capture exit code
set EXIT_CODE=%ERRORLEVEL%

echo.
echo ================================================================
if %EXIT_CODE% equ 0 (
    echo     ✅ TEST PASSED
) else (
    echo     ❌ TEST FAILED (exit code: %EXIT_CODE%)
)
echo ================================================================
echo.
echo Check test results:
echo   - Console output above
echo   - test_pins_run.log (detailed log)
echo   - test_results_latest.json (structured results)
echo.

exit /b %EXIT_CODE%
