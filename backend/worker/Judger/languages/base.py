import threading
from abc import ABC, abstractmethod


class TLEException(Exception):
    """Raised when a submission exceeds its time limit."""
    def __init__(self, message, peak_memory_mb=0.0):
        super().__init__(message)
        self.peak_memory_mb = peak_memory_mb


class BaseLanguage(ABC):
    """
    Abstract base class for language-specific compile/run helpers.
    Provides `run_with_gvisor` which uses POSIX `timeout` + `/usr/bin/time`
    for resource tracking inside the container — no Isolate dependency.
    """

    @abstractmethod
    def compile(self, submission_id):
        """Compile the source code. Returns (exit_code, output_str)."""
        pass

    @abstractmethod
    def run(self, submission_id):
        """Run the compiled/interpreted code. Returns (exit_code, stdout, time_ms, mem_mb, stderr)."""
        pass

    def run_with_gvisor(self, process_cmd: str, time_limit: int, memory_limit: int,
                        use_mem_limit: bool = True, max_processes: int = 1):
        """
        Executes `process_cmd` inside the gVisor container using POSIX tools:
          - `timeout`: enforces a hard wall-clock deadline and exits with code 124.
          - `/usr/bin/time -f`: captures peak RSS (MEM) and CPU time (USR+SYS).

        Input  is read from /workspace/input.txt
        Output is written to /workspace/actual_op.txt
        Stderr is written to /workspace/error_log.txt
        Metrics are written to /workspace/time.txt

        Returns:
            (exit_code, "", execution_time_ms, peak_memory_mb, stderr_str)
        Raises:
            TLEException if wall-clock or CPU time exceeds time_limit.
            RuntimeError  if the Docker exec_run call itself fails.
        """
        # 1. Clear stale outputs from the previous test case
        self.container.exec_run(
            'rm -f /workspace/actual_op.txt /workspace/error_log.txt /workspace/time.txt'
        )

        time_limit_sec = time_limit / 1000.0
        # Small startup buffer so the container has time to load the runtime
        wall_time_sec = time_limit_sec + 0.5

        # 2. Build the shell command:
        #    /usr/bin/time records: MEM:<peak_rss_kb> CPU:<user+sys_seconds>
        #    timeout --preserve-status keeps the original process exit code
        run_cmd = (
            f"sh -c '/usr/bin/time -f \"MEM:%M CPU:%U+%S\" -o /workspace/time.txt "
            f"timeout --preserve-status {wall_time_sec:.3f}s "
            f"{process_cmd} < /workspace/input.txt > /workspace/actual_op.txt "
            f"2> /workspace/error_log.txt'"
        )

        result = {}

        def _run():
            try:
                ec, out = self.container.exec_run(run_cmd)
                result['exit_code'] = ec
            except Exception as exc:
                result['error'] = exc

        # 3. Run in a daemon thread so we can impose a hard Python-level deadline
        #    in case the Docker API itself hangs (e.g. gVisor scheduler bug).
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        thread.join(timeout=wall_time_sec + 2.0)

        if thread.is_alive():
            # Docker API is hung — stop the container so the thread unblocks
            try:
                self.container.stop(timeout=1)
            except Exception:
                pass
            raise TLEException(f"Execution exceeded wall-clock limit of {time_limit_sec}s")

        if 'error' in result:
            raise RuntimeError(f"Docker exec_run failed: {result['error']}") from result['error']

        exit_code = result.get('exit_code', 1)

        # 4. Parse metrics from /usr/bin/time output
        _, time_out = self.container.exec_run("cat /workspace/time.txt")
        time_str = time_out.decode('utf-8', errors='replace').strip() if time_out else ""

        peak_memory_mb = 0.0
        execution_time_ms = 0.0

        if "MEM:" in time_str and "CPU:" in time_str:
            try:
                parts = time_str.split()
                mem_kb = float(parts[0].split(':')[1])
                peak_memory_mb = mem_kb / 1024.0

                cpu_parts = parts[1].split(':')[1].split('+')
                execution_time_ms = (float(cpu_parts[0]) + float(cpu_parts[1])) * 1000.0
            except (ValueError, IndexError):
                pass

        # 5. Handle resource-limit verdicts
        # exit 137 = SIGKILL from Docker OOM killer; peak stays at limit
        if exit_code == 137 and peak_memory_mb == 0.0:
            peak_memory_mb = float(memory_limit)

        # exit 124 = timeout's own code; exit 143 = SIGTERM from --preserve-status TLE
        if exit_code in (124, 143) or execution_time_ms > time_limit:
            raise TLEException("Time Limit Exceeded", peak_memory_mb=peak_memory_mb)

        # 6. Capture stderr for RE diagnostics
        _, stderr_out = self.container.exec_run("cat /workspace/error_log.txt")
        stderr_str = stderr_out.decode('utf-8', errors='replace') if stderr_out else ''

        return exit_code, "", execution_time_ms, peak_memory_mb, stderr_str
