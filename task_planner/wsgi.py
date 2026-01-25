"""
WSGI config for task_planner project.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_planner.settings')

application = get_wsgi_application()