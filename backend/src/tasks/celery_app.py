"""Celery application configuration"""
from celery import Celery
from celery.schedules import crontab
from src.config import get_settings

settings = get_settings()

# Create Celery app
celery_app = Celery(
    'heatmap',
    broker=settings.get_celery_broker(),
    backend=settings.get_celery_backend(),
    include=[
        'src.tasks.analysis_tasks',
        'src.tasks.scheduled_tasks',
    ]
)

# Configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3000,  # 50 minutes soft limit
    worker_prefetch_multiplier=1,  # Disable prefetching for better control
    worker_max_tasks_per_child=100,  # Restart worker after 100 tasks
)

# Scheduled tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    'weekly-refresh': {
        'task': 'src.tasks.scheduled_tasks.scheduled_refresh_task',
        'schedule': crontab(day_of_week='sunday', hour=2, minute=0),  # Every Sunday at 2 AM
    },
}
