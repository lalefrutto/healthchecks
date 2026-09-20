from __future__ import annotations

from django.urls import path

from hc.mq import views

urlpatterns = [
    path("stats/", views.task_stats, name="hc-mq-task-stats"),
    path("<slug:name>/", views.run_task, name="hc-mq-run-task"),
    path("result/<str:task_id>/", views.task_result, name="hc-mq-task-result"),
]
