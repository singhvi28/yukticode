import docker

class DockerManager:
    """
    DockerManager handles Docker operations such as building images and creating containers.
    """

    def __init__(self, submission_id, time_limit, memory_limit):
        """
        Initializes DockerManager with the Docker client and task-specific constraints.
        Removing judger_vol_path as it relies entirely on Docker archive streams now.
        """
        self.client = docker.from_env()
        self.image_name = "judger-runtime-img"
        self.container_name = f"judger-{submission_id}"
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def start_container(self):
        """
        Creates and starts a new ephemeral container for the task in the background.

        Returns:
        - container: The running Docker container.
        """
        try:
            image = self.client.images.get(self.image_name)
        except docker.errors.ImageNotFound:
            import os
            dockerfile_path = os.path.join(os.path.dirname(__file__), "judger_dockerfile")
            print(f" [*] Image {self.image_name} not found. Building... at {dockerfile_path}")
            image, logs = self.client.images.build(
                path=dockerfile_path, tag=self.image_name, forcerm=True
            )

        container = self.client.containers.run(
            image=image.id,
            name=self.container_name,
            detach=True,
            tty=True, # Critical to keep it alive while injecting archives
            mem_limit=f'{self.memory_limit}m',
            network_disabled=True,
            cap_add=["SYS_ADMIN", "NET_ADMIN"],   # Required for Isolate namespaces
            security_opt=["apparmor=unconfined"], # Required for Isolate bind mounts
            stderr=True,
            stdout=True,
            auto_remove=True,
        )

        return container
