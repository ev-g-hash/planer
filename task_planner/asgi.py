"""
ASGI config for task_planner project.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_planner.settings')

application = get_asgi_application()