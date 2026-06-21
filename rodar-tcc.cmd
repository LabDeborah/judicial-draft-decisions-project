@echo off
setlocal

set MODE=live
set ANALYSIS_MODE=local
set LIMIT=20
set ANALYSIS_LIMIT=20
set COMPILE_PDF=true
set GEMINI_MODEL=gemini-flash-lite-latest
set GEMINI_REQUESTS_PER_MINUTE=15
set GEMINI_REQUESTS_PER_DAY=500

if not "%~1"=="" set MODE=%~1
if not "%~2"=="" set ANALYSIS_MODE=%~2
if not "%~3"=="" set LIMIT=%~3
if not "%~4"=="" set ANALYSIS_LIMIT=%~4
if not "%~5"=="" set COMPILE_PDF=%~5
if not "%~6"=="" set GEMINI_MODEL=%~6
if not "%~7"=="" set GEMINI_REQUESTS_PER_MINUTE=%~7
if not "%~8"=="" set GEMINI_REQUESTS_PER_DAY=%~8

echo Executando pipeline...
echo   mode=%MODE%
echo   analysis-mode=%ANALYSIS_MODE%
echo   limit=%LIMIT%
echo   analysis-limit=%ANALYSIS_LIMIT%
echo   compile-pdf=%COMPILE_PDF%
echo   gemini-model=%GEMINI_MODEL%
echo   gemini-requests-per-minute=%GEMINI_REQUESTS_PER_MINUTE%
echo   gemini-requests-per-day=%GEMINI_REQUESTS_PER_DAY%
echo.

python -m app.cli.main --mode %MODE% --analysis-mode %ANALYSIS_MODE% --limit %LIMIT% --analysis-limit %ANALYSIS_LIMIT% --compile-pdf %COMPILE_PDF% --gemini-model %GEMINI_MODEL% --gemini-requests-per-minute %GEMINI_REQUESTS_PER_MINUTE% --gemini-requests-per-day %GEMINI_REQUESTS_PER_DAY%
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Falha na execucao. Codigo: %EXIT_CODE%
)

exit /b %EXIT_CODE%
