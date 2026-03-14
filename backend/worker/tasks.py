import os

import docker
from celery import Celery
from datetime import datetime, timezone, timedelta

# Use existing environment variables for the broker
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
app = Celery("tasks", broker=REDIS_URL)

app.conf.beat_schedule = {
    "reap-every-5-minutes": {
        "task": "worker.tasks.reap_orphaned_containers",
        "schedule": 300.0,  # seconds
    },
}


@app.task
def reap_orphaned_containers():
    client = docker.from_env()
    # Filter for containers with your specific prefix
    containers = client.containers.list(all=True, filters={"name": "judger-"})

    threshold = datetime.now(timezone.utc) - timedelta(minutes=10)

    for container in containers:
        # Check creation time
        created_str = container.attrs["Created"]
        # Docker timestamp format: 2024-03-20T12:00:00.000000000Z
        created_time = datetime.fromisoformat(created_str.split(".")[0]).replace(
            tzinfo=timezone.utc
        )

        if created_time < threshold:
            try:
                print(f"Reaping orphaned container: {container.name}")
                container.stop(timeout=1)
                container.remove(force=True)
            except Exception as e:
                print(f"Failed to reap {container.name}: {e}")
