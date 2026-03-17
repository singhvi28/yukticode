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
        Run the compiled Java class.

        use_mem_limit=False: the JVM maps huge virtual address space for JIT/GC
        which would trigger the Docker mem limit incorrectly. Docker's mem_limit
        handles the actual physical cap at the container level.

        Returns:
            (exit_code, "", execution_time_ms, peak_memory_mb, stderr)
        Raises:
            TLEException: if execution exceeds self.time_limit milliseconds.
        """
        process_cmd = "/usr/bin/java -cp /workspace Main"
        return self.run_with_gvisor(
            process_cmd, self.time_limit, self.memory_limit,
            use_mem_limit=False, max_processes=0
        )
