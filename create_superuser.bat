@echo off
REM Script to create a Django superuser for Lore platform
REM Usage: create_superuser.bat

echo ===================================
echo Lore Platform - Create Superuser
echo ===================================
echo.

REM Check if virtual environment exists
if not exist "venv\Scripts\activate.bat" (
    echo Error: Virtual environment not found!
    echo Please create one with: python -m venv venv
    exit /b 1
)

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Run the management command
python manage.py create_superuser %*

REM Deactivate virtual environment
call deactivate

pause
