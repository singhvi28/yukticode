import threading
from abc import ABC, abstractmethod


class TLEException(Exception):
    """Raised when a submission exceeds its time limit."""
    def __init__(self, message, peak_memory_mb=0.0):
        super().__init__(message)
        self.peak_memory_mb = peak_memory_mb


class BaseLanguage(ABC):
    """
    BaseLanguage is an abstract base class for different programming languages.
    Provides a `run_with_timeout` helper that enforces a Python-level deadline
    on Docker exec_run calls, independent of shell-level `timeout` commands.
    """

    @abstractmethod
    def compile(self, submission_id):
        """Abstract method to compile the source code."""
        pass

    @abstractmethod
    def run(self, submission_id):
        """Abstract method to run the compiled code."""
        pass

    def run_with_isolate(self, process_cmd: str, time_limit: int, memory_limit: int):
        """
        Executes `process_cmd` securely inside Isolate's sandbox. It handles:
        1. isolate --init (creating the box)
        2. Copying workspace files to the sandbox box directory
        3. Executing isolate with cgroup constraints and time limits
        4. Copying output back to /workspace/actual_op.txt
        5. isolate --cleanup

        Returns:
            (exit_code: int, output: str) on success.
        Raises:
            TLEException: if execution exceeds time_limit.
        """
        # 1. Initialize Isolate Box
        exit_code, output = self.container.exec_run("isolate --init")
        if exit_code != 0:
            raise Exception(f"Failed to initialize isolate: {output.decode('utf-8')}")
        
        box_dir = output.decode('utf-8').strip()

        # 2. Prepare Sandbox environment (copy files from /workspace to the box)
        self.container.exec_run(f"/bin/sh -c 'cp -r /workspace/* {box_dir}/'")
        
        # 3. Execute using Isolate
        # Time limit is passed as fractional seconds in Isolate. We allow a little extra wall time.
        # Memory limit is passed in KB (Docker had MB). Isolate ensures tight bounds.
        memory_limit_kb = memory_limit * 1024
        
        # We redirect stdin and stdout within the isolate environment.
        # --meta captures the execution statistics.
        isolate_cmd = (
            f"/bin/sh -c 'isolate --cg -M /workspace/meta.txt "
            f"--time={time_limit} --wall-time={time_limit + 1} "
            f"--mem={memory_limit_kb} "
            f"--run -- {process_cmd} < {box_dir}/input.txt > {box_dir}/actual_op.txt'"
        )

        result = {}
        def _run():
            ec, out = self.container.exec_run(isolate_cmd)
            result['exit_code'] = ec
            result['output'] = out.decode('utf-8') if out else ''

        # Use daemon thread to enforce hard timeout just in case isolate hangs entirely 
        # (though isolate itself has wall-time bounds).
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=time_limit + 2)

        if thread.is_alive():
            self._cleanup_isolate()
            raise TLEException(f"Execution exceeded time limit of {time_limit}s")

        # 4. Read meta file to determine if TLE occurred gracefully from Isolate
        # and extract actual resource usage.
        _, meta_out = self.container.exec_run("cat /workspace/meta.txt")
        meta_str = meta_out.decode('utf-8') if meta_out else ""
        
        peak_memory_mb = 0.0
        execution_time_ms = 0.0

        for line in meta_str.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith("time:"):
                # Isolate records CPU time in seconds with fractional parts
                try:
                    execution_time_ms = float(line.split(':')[1]) * 1000.0
                except ValueError:
                    pass
            elif line.startswith("max-rss:") or line.startswith("cg-mem:"):
                # max-rss / cg-mem are in KB, we want MB
                try:
                    peak_memory_mb = float(line.split(':')[1]) / 1024.0
                except ValueError:
                    pass

        # Time Out status is "status:TO" (Time Out) or "status:SG" (Killed by Signal usually 9 for OOM/TLE)
        if "status:TO" in meta_str or "status:SG" in meta_str:
            # If we see TO, it's definitely a timeout.
            # If SG, we check if memory exceeded, if so it could be MLE, but we treat it as TLE for now 
            # or handle it in judger.py.
            if "status:TO" in meta_str:
                self._cleanup_isolate()
                raise TLEException("Isolate reported Time Limit Exceeded", peak_memory_mb=peak_memory_mb)

        # 5. Bring output back to /workspace/actual_op.txt so file_utils can get it
        self.container.exec_run(f"/bin/sh -c 'cp {box_dir}/actual_op.txt /workspace/actual_op.txt'")
        
        self._cleanup_isolate()

        # Isolate returns non-zero if the sandboxed process exits non-zero
        return result['exit_code'], result['output'], execution_time_ms, peak_memory_mb

    def _cleanup_isolate(self):
        self.container.exec_run("isolate --cleanup")
