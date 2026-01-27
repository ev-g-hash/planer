"""
WSGI config for task_planner project.
"""

import os

from django.core.wsgi import get_wsgi_application
from whitenoise import WhiteNoise
from pathlib import Path

# Определяем корень проекта
BASE_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_planner.settings')

application = get_wsgi_application()
application = WhiteNoise(application, root=str(BASE_DIR / 'staticfiles'))