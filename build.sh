#!/usr/bin/env bash
# Exit on error
set -o errexit


pip install -r requirements.txt

# Convert static asset files
python manage.py collectstatic --no-input
python manage.py makemigrations
python manage.py makemigrations base
python manage.py migrate
python manage.py migrate base

