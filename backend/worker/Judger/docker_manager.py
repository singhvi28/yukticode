import hashlib
import logging
import os
from pathlib import Path

import docker

logger = logging.getLogger(__name__)

_runtime_warned = False


def _dockerfile_path() -> Path:
    return Path(__file__).resolve().parent / "judger_dockerfile" / "Dockerfile"


def _image_tag() -> str:
    """Tag derived from Dockerfile contents so edits force a rebuild."""
    digest = hashlib.sha256(_dockerfile_path().read_bytes()).hexdigest()[:12]
    return f"judger-runtime-img:{digest}"


def _ensure_image(client) -> str:
    """
    Return the image tag for the current Dockerfile, building it if missing.
    """
    tag = _image_tag()
    try:
        client.images.get(tag)
        return tag
    except docker.errors.ImageNotFound:
        dockerfile_dir = str(_dockerfile_path().parent)
        print(f" [*] Image {tag} not found. Building...")
        client.images.build(path=dockerfile_dir, tag=tag, forcerm=True)
        return tag


def _resolve_runtime(client) -> str | None:
    """
    Pick the container runtime. JUDGER_RUNTIME env overrides auto-detection.
    Returns None to use Docker's default (runc) when gVisor is unavailable.
    """
    global _runtime_warned

    configured = os.getenv("JUDGER_RUNTIME", "auto").strip()
    if configured and configured.lower() not in ("auto", "default", "runc"):
        return configured

    try:
        runtimes = client.info().get("Runtimes", {})
        if "runsc" in runtimes:
            return "runsc"
    except Exception:
        pass

    if not _runtime_warned:
        _runtime_warned = True
        logger.warning(
            "gVisor runtime (runsc) is not available; falling back to the "
            "default Docker runtime. Isolation is weaker than production. "
            "Install gVisor or set JUDGER_RUNTIME=runsc once it is configured."
        )
    return None


class DockerManager:
    def __init__(self, submission_id, time_limit, memory_limit):
        self.client = docker.from_env()
        self.image_name = _image_tag()
        self.container_name = f"judger-{submission_id}"
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def start_container(self):
        tag = _ensure_image(self.client)
        self.image_name = tag
        image = self.client.images.get(tag)

        run_kwargs = dict(
            image=image.id,
            name=self.container_name,
            detach=True,
            tty=True,               # Keep container alive while injecting archives
            mem_limit=f'{self.memory_limit}m',
            network_disabled=True,
            pids_limit=64,          # Prevent fork-bomb PID table exhaustion
            stderr=True,
            stdout=True,
            # Removed: cap_add=["SYS_ADMIN", "NET_ADMIN"]  — not needed without Isolate
            # Removed: security_opt=["apparmor=unconfined"] — not needed without Isolate
            # Removed: auto_remove=True                     — judger.py finally calls remove(force=True)
        )
        runtime = _resolve_runtime(self.client)
        if runtime:
            run_kwargs["runtime"] = runtime

        container = self.client.containers.run(**run_kwargs)

        return container
