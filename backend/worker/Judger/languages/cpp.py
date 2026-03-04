from .base import BaseLanguage


class CppLanguage(BaseLanguage):
    """
    CppLanguage handles compilation and execution of C++ programs within a Docker container.
    """

    def __init__(self, container, time_limit, memory_limit):
        self.container = container
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def compile(self, submission_id):
        """
        Compile the C++ source file.

        Returns:
            (exit_code, compile_output)
        """
        compile_cmd = (
            f"/bin/sh -c 'g++ -O2 -o /workspace/UserProgram /workspace/main.cpp'"
        )
        exit_code, output = self.container.exec_run(compile_cmd)
        return exit_code, output.decode('utf-8') if output else ''

    def run(self, submission_id):
        """
        Run the compiled binary, feeding /workspace/input.txt as stdin and
        writing stdout to /workspace/actual_op.txt.

        Uses BaseLanguage.run_with_timeout for a Python-level deadline.

        Returns:
            (exit_code, run_output)
        Raises:
            TLEException: if execution exceeds self.time_limit seconds.
        """
        # The UserProgram is mapped into Isolate's root.
        run_cmd = "./UserProgram"
        return self.run_with_isolate(run_cmd, self.time_limit, self.memory_limit)
