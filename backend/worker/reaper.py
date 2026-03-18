"""
Lightweight background daemon that reaps orphaned judger containers.
Replaces the previous Celery-based cron job with a plain Python loop,
eliminating the Celery/celery-beat dependency entirely.

Run alongside the workers:
    python reaper.py &
"""
import time
import docker
import logging
from datetime import datetime, timezone, timedelta

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Containers older than this threshold that are still alive are considered orphans
ORPHAN_AGE_MINUTES = 10
REAP_INTERVAL_SECONDS = 300  # 5 minutes


def reap_orphaned_containers():
    """
    Stop and remove any judger-* containers that have been running for longer
    than ORPHAN_AGE_MINUTES. These are containers whose judger.py process
    crashed before reaching the finally block.
    """
    client = docker.from_env()
    containers = client.containers.list(all=True, filters={"name": "judger-"})
    threshold = datetime.now(timezone.utc) - timedelta(minutes=ORPHAN_AGE_MINUTES)

    reaped = 0
    for container in containers:
        try:
            created_str = container.attrs["Created"]
            # Docker timestamp format: 2024-03-20T12:00:00.000000000Z
            created_time = datetime.fromisoformat(created_str.split(".")[0]).replace(
                tzinfo=timezone.utc
            )

            if created_time < threshold:
                logger.info("Reaping orphaned container: %s (created %s)", container.name, created_str)
                container.stop(timeout=1)
                container.remove(force=True)
                reaped += 1
        except Exception as e:
            logger.error("Failed to reap %s: %s", container.name, e)

    if reaped:
        logger.info("Reaper cycle complete — removed %d orphaned container(s)", reaped)


if __name__ == "__main__":
    logger.info("Starting background container reaper (interval=%ds, threshold=%dmin)...",
                REAP_INTERVAL_SECONDS, ORPHAN_AGE_MINUTES)
    while True:
        reap_orphaned_containers()
        time.sleep(REAP_INTERVAL_SECONDS)
