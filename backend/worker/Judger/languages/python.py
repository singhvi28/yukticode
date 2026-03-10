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
        writing stdout to /workspace/actual_op.txt.

        Uses BaseLanguage.run_with_timeout for a Python-level deadline.

        Returns:
            (exit_code, run_output)
        Raises:
            TLEException: if execution exceeds self.time_limit seconds.
        """
        # Isolate runs in its own root, the workspace files are mapped into the current 
        # working directory of Isolate (the box directory).
        run_cmd = "/usr/bin/python3 main.py"
        return self.run_with_isolate(run_cmd, self.time_limit, self.memory_limit)
