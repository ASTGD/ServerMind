"""Celery application — durable background execution (Update 15).

Run a worker with:  celery -A app.celery_app worker --loglevel=info
Broker + result backend are Redis (REDIS_URL).
"""
from __future__ import annotations

from celery import Celery

from app.config import settings

celery = Celery(
    "servermind",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    # Task modules the worker must import on startup.
    imports=["app.workers.playbook_tasks"],
)
