import docker

class DockerManager:
    def __init__(self, submission_id, time_limit, memory_limit):
        self.client = docker.from_env()
        self.image_name = "judger-runtime-img"
        self.container_name = f"judger-{submission_id}"
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def start_container(self):
        try:
            image = self.client.images.get(self.image_name)
        except docker.errors.ImageNotFound:
            import os
            dockerfile_path = os.path.join(os.path.dirname(__file__), "judger_dockerfile")
            print(f" [*] Image {self.image_name} not found. Building...")
            image, logs = self.client.images.build(
                path=dockerfile_path, tag=self.image_name, forcerm=True
            )

        container = self.client.containers.run(
            image=image.id,
            name=self.container_name,
            runtime="runsc",        # Strict gVisor kernel interception
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

        return container
