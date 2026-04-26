from .base import BaseLanguage


class JavaLanguage(BaseLanguage):
    """
    JavaLanguage handles compilation and execution of Java programs within a Docker container.
    """

    def __init__(self, container, time_limit, memory_limit):
        self.container = container
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def compile(self, submission_id):
        """
        Compile the Java source file.

        Returns:
            (exit_code, compile_output)
        """
        compile_cmd = "/bin/sh -c 'javac /workspace/Main.java -d /workspace'"
        exit_code, output = self.container.exec_run(compile_cmd)
        return exit_code, output.decode('utf-8') if output else ''

    def run(self, submission_id):
        """
        Run the compiled Java class with an explicit heap cap (-Xmx).
        Docker's mem_limit still enforces the container-level physical cap.

        Returns:
            (exit_code, "", execution_time_ms, peak_memory_mb, stderr)
        Raises:
            TLEException: if execution exceeds self.time_limit milliseconds.
        """
        # Leave a little headroom under the container mem_limit for JVM metaspace/native
        heap_mb = max(16, int(self.memory_limit) - 32)
        process_cmd = f"/usr/bin/java -Xmx{heap_mb}m -cp /workspace Main"
        return self.run_with_gvisor(process_cmd, self.time_limit, self.memory_limit)
