from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hc.settings")

app = Celery("hc")
app.config_from_object("hc.celeryconfig")
app.autodiscover_tasks()
