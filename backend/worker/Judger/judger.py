import logging
import re
import time
import uuid
import logging
logging.basicConfig(level=logging.DEBUG)
from .docker_manager import DockerManager
from .file_utils import put_files_to_container, extract_file_from_container
from .result_mapper import map_exit_code
from .languages.base import TLEException
from .languages.cpp import CppLanguage
from .languages.python import PythonLanguage
from .languages.java import JavaLanguage

logger = logging.getLogger(__name__)



class SecurityViolationException(Exception):
    """Raised when source code contains forbidden patterns indicating malicious intent."""
    pass


def check_forbidden_patterns(language: str, src_code: str) -> None:
    """
    Performs static analysis on source code, identifying forbidden libraries or
    system calls that user code has no legitimate reason to execute.
    Raises SecurityViolationException if a forbidden pattern is found.
    """
    if not src_code:
        return

    forbidden_patterns = []
    if language == "py":
        forbidden_patterns = [
            "os.system", "subprocess", "eval", "exec", 
            "__import__", "open", "pty.spawn"
        ]
    elif language == "cpp":
        forbidden_patterns = [
            "<cstdlib>", "system(", "popen(", "fork(", "exec(", "clone("
        ]
    elif language == "java":
        forbidden_patterns = [
            "Runtime.getRuntime().exec", "ProcessBuilder", "System.exit"
        ]

    for pattern in forbidden_patterns:
        if re.search(r'\b' + re.escape(pattern) + r'\b', src_code):
            raise SecurityViolationException(f"Forbidden pattern detected: {pattern}")


def get_language_instance(language, container, time_limit, memory_limit):
    """
    Returns an instance of the language-specific class based on the provided language.
    """
    if language == 'cpp':
        return CppLanguage(container, time_limit, memory_limit)
    elif language == "py":
        return PythonLanguage(container, time_limit, memory_limit)
    elif language == "java":
        return JavaLanguage(container, time_limit, memory_limit)
    else:
        raise ValueError(f"Unsupported language: {language!r}")


def compare_outputs(expected: str, actual: str) -> bool:
    """
    Compare expected and actual output in a judge-friendly way:
      - Each line is right-stripped (trailing spaces don't count).
      - Leading and trailing blank lines are ignored.
      - Windows-style \\r\\n newlines are normalised.

    Returns True if the outputs are equivalent, False otherwise.
    """
    def normalise(text: str):
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        lines = [line.rstrip() for line in lines]
        while lines and lines[0] == '':
            lines.pop(0)
        while lines and lines[-1] == '':
            lines.pop()
        return lines

    return normalise(expected) == normalise(actual)



def run_judger(language, time_limit, memory_limit,
               src_code=None, test_cases=None):
    """
    Orchestrates the compilation and execution of the provided source code within an
    ephemeral Docker container using stream I/O, then compares the output.

    Returns a dict:
      { "verdict": str, "execution_time_ms": float, "peak_memory_mb": float }

    Verdict values: "AC", "WA", "TLE", "CE", "RE", "MLE", "SYSTEM_ERROR".
    Never raises — callers are guaranteed to receive a result dict.
    """
    submission_id = str(uuid.uuid4())
    total_time_ms: float = 0.0
    peak_memory_mb: float = 0.0

    def _result(verdict: str) -> dict:
        return {
            "verdict": verdict,
            "execution_time_ms": round(total_time_ms, 2),
            "peak_memory_mb": peak_memory_mb,
        }

    container = None
    try:
        check_forbidden_patterns(language, src_code)

        dm = DockerManager(submission_id, time_limit, memory_limit)
        container = dm.start_container()
        language_instance = get_language_instance(language, container, time_limit, memory_limit)

        # Write the source code once
        put_files_to_container(container, language, src_code, None, None)

        if language in ["cpp", "java"]:
            compile_exit_code, _ = language_instance.compile(submission_id=submission_id)
            if compile_exit_code == 1:
                return _result("CE")
                
        if not test_cases:
            return _result("AC")

        for i, tc in enumerate(test_cases):
            std_in = tc.get("input", "")
            expected_out = tc.get("expected_output", "")
            
            # Write just the I/O text files for this specific test case iteration
            put_files_to_container(container, language, None, std_in, expected_out)

            try:
                t_start = time.perf_counter()
                run_exit_code, _, isolate_time, isolate_mem = language_instance.run(submission_id=submission_id)
                elapsed_ms = isolate_time if isolate_time > 0 else (time.perf_counter() - t_start) * 1000.0
            except TLEException as e:
                logger.warning("[%s] Time limit exceeded on test case %d", submission_id, i+1)
                total_time_ms += float(time_limit)  # charge full TL
                peak_memory_mb = max(peak_memory_mb, getattr(e, "peak_memory_mb", 0.0))
                return _result("TLE")

            total_time_ms += elapsed_ms
            peak_memory_mb = max(peak_memory_mb, isolate_mem)

            if run_exit_code != 0:
                logger.warning("[%s] Non-zero exit code %s on test case %d", submission_id, run_exit_code, i+1)
                return _result(map_exit_code(run_exit_code))

            expected_op_data = extract_file_from_container(container, "/workspace/expected_op.txt")
            actual_op_data = extract_file_from_container(container, "/workspace/actual_op.txt")
            
            if not compare_outputs(expected_op_data, actual_op_data):
                logger.info("[%s] Wrong Answer on test case %d", submission_id, i+1)
                return _result("WA")

        return _result("AC")

    except SecurityViolationException as e:
        logger.warning("[%s] Security violation: %s", submission_id, str(e))
        return _result("CE")
    except Exception:
        logger.exception(
            "[%s] Unhandled error during judging (language=%s, time_limit=%s, memory_limit=%s)",
            submission_id, language, time_limit, memory_limit,
        )
        return _result("SYSTEM_ERROR")
    finally:
        if container:
            try:
                container.stop(timeout=1)
            except Exception:
                pass



def custom_run(language, time_limit, memory_limit,
               src_code=None, std_in=None):
    """
    Run code against a custom test case in an ephemeral container using stream I/O.

    Returns a dict with: {"verdict": ..., "output": ..., "execution_time_ms": ..., "peak_memory_mb": ...}
    verdict is one of: "AC", "TLE", "CE", "RE", "MLE", "SYSTEM_ERROR". Never raises.
    """
    submission_id = str(uuid.uuid4())
    container = None
    try:
        check_forbidden_patterns(language, src_code)

        dm = DockerManager(submission_id, time_limit, memory_limit)
        container = dm.start_container()
        language_instance = get_language_instance(language, container, time_limit, memory_limit)

        put_files_to_container(container, language, src_code, std_in)

        if language in ["cpp", "java"]:
            compile_exit_code, _ = language_instance.compile(submission_id=submission_id)
            if compile_exit_code == 1:
                return {"verdict": "CE", "output": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

        start_time = time.perf_counter()
        try:
            run_exit_code, _, isolate_time, isolate_mem = language_instance.run(submission_id=submission_id)
            elapsed_ms = isolate_time if isolate_time > 0 else (time.perf_counter() - start_time) * 1000.0
            peak_mb = isolate_mem
        except TLEException as e:
            logger.warning("[%s] Time limit exceeded — stopping container", submission_id)
            return {"verdict": "TLE", "output": "", "execution_time_ms": time_limit * 1000.0, "peak_memory_mb": getattr(e, "peak_memory_mb", 0.0)}

        run_output = extract_file_from_container(container, "/workspace/actual_op.txt")

        if run_exit_code == 0:
            return {"verdict": "AC", "output": run_output, "execution_time_ms": elapsed_ms, "peak_memory_mb": peak_mb}

        return {"verdict": map_exit_code(run_exit_code), "output": "", "execution_time_ms": elapsed_ms, "peak_memory_mb": peak_mb}

    except SecurityViolationException as e:
        logger.warning("[%s] Security violation in custom run: %s", submission_id, str(e))
        return {"verdict": "CE", "output": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
    except Exception:
        logger.exception(
            "[%s] Unhandled error during custom run (language=%s, time_limit=%s, memory_limit=%s)",
            submission_id, language, time_limit, memory_limit,
        )
        return {"verdict": "SYSTEM_ERROR", "output": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
    finally:
        if container:
            try:
                container.stop(timeout=1)
            except Exception:
                pass