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
        compile_cmd = (
            "/bin/sh -c 'javac /workspace/Main.java'"
        )
        exit_code, output = self.container.exec_run(compile_cmd)
        return exit_code, output.decode('utf-8') if output else ''

    def run(self, submission_id):
        """
        Run the compiled Java class.
        """
        run_cmd = "/usr/bin/java Main"
        # JVM needs unlimited threads (GC, JIT) and no --mem (it maps huge virtual address space)
        return self.run_with_isolate(run_cmd, self.time_limit, self.memory_limit,
                                     use_mem_limit=False, max_processes=0)
