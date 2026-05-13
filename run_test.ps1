#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pinterest Automation Test Runner — PowerShell
    Runs: test_product_and_video_pins.py with proper environment setup
#>

$ErrorActionPreference = "Continue"

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "     PINTEREST AUTOMATION — PRODUCT & VIDEO PIN TEST" -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Check if venv exists
if (-not (Test-Path "venv")) {
    Write-Host "[ERROR] Virtual environment not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run this first:" -ForegroundColor Yellow
    Write-Host "  python -m venv venv"
    Write-Host "  venv\Scripts\Activate.ps1"
    Write-Host "  pip install -r requirements.txt"
    Write-Host ""
    exit 1
}

# Activate venv
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& "venv\Scripts\Activate.ps1"

# Check if .env exists
if (-not (Test-Path ".env")) {
    Write-Host "[ERROR] .env file not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Create .env file with:" -ForegroundColor Yellow
    Write-Host "  PINTEREST_EMAIL=your_email@gmail.com"
    Write-Host "  PINTEREST_PASSWORD=your_password"
    Write-Host "  SHOPIFY_STORE_URL=https://meeeshop.myshopify.com"
    Write-Host "  SHOPIFY_ACCESS_TOKEN=shpat_xxxxx"
    Write-Host "  STORE_BASE_URL=https://us.meeeshop.com"
    Write-Host "  GEMINI_API_KEY=AIza..."
    Write-Host ""
    exit 1
}

Write-Host "[OK] Environment ready" -ForegroundColor Green
Write-Host ""
Write-Host "Starting test: test_product_and_video_pins.py" -ForegroundColor Cyan
Write-Host ""

# Run test
python test_product_and_video_pins.py

# Capture exit code
$exitCode = $LASTEXITCODE

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {
    Write-Host "     ✅ TEST PASSED" -ForegroundColor Green
} else {
    Write-Host "     ❌ TEST FAILED (exit code: $exitCode)" -ForegroundColor Red
}
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Check test results:" -ForegroundColor Yellow
Write-Host "  - Console output above"
Write-Host "  - test_pins_run.log (detailed log)"
Write-Host "  - test_results_latest.json (structured results)"
Write-Host ""

exit $exitCode
