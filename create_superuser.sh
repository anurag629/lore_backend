#!/bin/bash
# Script to create a Django superuser for Lore platform
# Usage: ./create_superuser.sh

echo "==================================="
echo "Lore Platform - Create Superuser"
echo "==================================="
echo ""

# Activate virtual environment
if [ -d "venv/bin" ]; then
    source venv/bin/activate
elif [ -d "venv/Scripts" ]; then
    source venv/Scripts/activate
else
    echo "Error: Virtual environment not found!"
    echo "Please create one with: python -m venv venv"
    exit 1
fi

# Run the management command
python manage.py create_superuser "$@"

# Deactivate virtual environment
deactivate
