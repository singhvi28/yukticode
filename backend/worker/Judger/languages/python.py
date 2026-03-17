from .base import BaseLanguage


class PythonLanguage(BaseLanguage):
    """
    PythonLanguage handles execution of Python programs within a Docker container.
    """

    def __init__(self, container, time_limit, memory_limit):
        self.container = container
        self.time_limit = time_limit
        self.memory_limit = memory_limit

    def compile(self, submission_id=None):
        """Python requires no compilation."""
        return 0, "No compilation needed for Python"

    def run(self, submission_id):
        """
        Run the Python script, feeding /workspace/input.txt as stdin and
        writing stdout to /workspace/actual_op.txt via run_with_gvisor.

        Returns:
            (exit_code, "", execution_time_ms, peak_memory_mb, stderr)
        Raises:
            TLEException: if execution exceeds self.time_limit milliseconds.
        """
        process_cmd = "/usr/bin/python3 /workspace/main.py"
        return self.run_with_gvisor(process_cmd, self.time_limit, self.memory_limit)
