import time
import uuid
import logging

from .docker_manager import DockerManager
from .file_utils import put_files_to_container, extract_file_from_container, MAX_READ_BYTES
from .result_mapper import map_exit_code
from .languages.base import TLEException, SandboxError
from .languages.cpp import CppLanguage
from .languages.python import PythonLanguage
from .languages.java import JavaLanguage

logger = logging.getLogger(__name__)


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
    Compare expected and actual output in a judge-friendly way using a
    memory-efficient line-by-line generator to avoid loading full strings.
      - Each line is right-stripped (trailing spaces don't count).
      - Leading and trailing blank lines are ignored.
      - Windows-style \\r\\n newlines are normalised.

    Returns True if the outputs are equivalent, False otherwise.
    """
    def normalise_lines(text: str):
        """Generator yielding non-empty, rstripped lines (leading/trailing blanks stripped)."""
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        # strip leading blank lines
        start = 0
        while start < len(lines) and lines[start].rstrip() == '':
            start += 1
        # strip trailing blank lines
        end = len(lines) - 1
        while end >= start and lines[end].rstrip() == '':
            end -= 1
        for i in range(start, end + 1):
            yield lines[i].rstrip()

    # Guard against pathologically large strings that slipped through extract cap
    if len(expected) > MAX_READ_BYTES or len(actual) > MAX_READ_BYTES:
        logger.warning("compare_outputs: output exceeds max size — treating as WA")
        return False

    return list(normalise_lines(expected)) == list(normalise_lines(actual))


def run_judger(language, time_limit, memory_limit,
               src_code=None, test_cases=None):
    """
    Orchestrates the compilation and execution of the provided source code within an
    ephemeral Docker container using stream I/O, then compares the output.

    Returns a dict:
      { "verdict": str, "execution_time_ms": float, "peak_memory_mb": float }

    Verdict values: "AC", "WA", "TLE", "CE", "RE", "MLE", "SYSTEM_ERROR".
    Never raises — callers are guaranteed to receive a result dict.

    Security note: expected output is kept in worker memory and never written
    into the container. Only actual_op.txt is extracted for comparison.
    """
    submission_id = str(uuid.uuid4())
    total_time_ms: float = 0.0
    peak_memory_mb: float = 0.0

    def _result(verdict: str, msg: str = "") -> dict:
        return {
            "verdict": verdict,
            "execution_time_ms": round(total_time_ms, 2),
            "peak_memory_mb": peak_memory_mb,
            "message": msg[:2000],  # cap message length
        }

    container = None
    try:
        dm = DockerManager(submission_id, time_limit, memory_limit)
        container = dm.start_container()
        language_instance = get_language_instance(language, container, time_limit, memory_limit)

        # Write the source code once (no expected output goes into the container)
        put_files_to_container(container, language, src_code, None)

        if language in ["cpp", "java"]:
            compile_exit_code, compile_output = language_instance.compile(submission_id=submission_id)
            if compile_exit_code != 0:
                return _result("CE", compile_output)

        if not test_cases:
            return _result("AC")

        for i, tc in enumerate(test_cases):
            std_in = tc.get("input", "")
            # expected_out is kept in worker memory — never sent to the container
            expected_out = tc.get("expected_output", "")

            # Write only the input for this test case
            put_files_to_container(container, language, None, std_in)

            try:
                t_start = time.perf_counter()
                run_exit_code, _, isolate_time, isolate_mem, run_stderr = language_instance.run(submission_id=submission_id)
                elapsed_ms = isolate_time if isolate_time > 0 else (time.perf_counter() - t_start) * 1000.0
            except TLEException as e:
                logger.warning("[%s] Time limit exceeded on test case %d", submission_id, i+1)
                total_time_ms += float(time_limit)  # charge full TL
                peak_memory_mb = max(peak_memory_mb, getattr(e, "peak_memory_mb", 0.0))
                return _result("TLE")
            except SandboxError as e:
                logger.error("[%s] Sandbox fault on test case %d: %s", submission_id, i+1, e)
                return _result("SYSTEM_ERROR", str(e))

            total_time_ms += elapsed_ms
            peak_memory_mb = max(peak_memory_mb, isolate_mem)

            if run_exit_code != 0:
                logger.warning("[%s] Non-zero exit code %s on test case %d", submission_id, run_exit_code, i+1)
                return _result(map_exit_code(run_exit_code), run_stderr)

            # Only extract the user's actual output — expected stays in memory
            actual_op_data = extract_file_from_container(container, "/workspace/actual_op.txt")

            if not compare_outputs(expected_out, actual_op_data):
                logger.info("[%s] Wrong Answer on test case %d", submission_id, i+1)
                return _result("WA")

        return _result("AC")

    except SandboxError as e:
        logger.error("[%s] Sandbox fault during judging: %s", submission_id, e)
        return _result("SYSTEM_ERROR", str(e))
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
            try:
                container.remove(force=True)
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
        dm = DockerManager(submission_id, time_limit, memory_limit)
        container = dm.start_container()
        language_instance = get_language_instance(language, container, time_limit, memory_limit)

        put_files_to_container(container, language, src_code, std_in)

        if language in ["cpp", "java"]:
            compile_exit_code, compile_output = language_instance.compile(submission_id=submission_id)
            if compile_exit_code != 0:
                return {"verdict": "CE", "output": "", "message": compile_output[:2000], "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

        start_time = time.perf_counter()
        try:
            run_exit_code, _, isolate_time, isolate_mem, run_stderr = language_instance.run(submission_id=submission_id)
            elapsed_ms = isolate_time if isolate_time > 0 else (time.perf_counter() - start_time) * 1000.0
            peak_mb = isolate_mem
        except TLEException as e:
            logger.warning("[%s] Time limit exceeded — stopping container", submission_id)
            # time_limit is already in milliseconds (same units as execution_time_ms)
            return {"verdict": "TLE", "output": "", "message": "", "execution_time_ms": float(time_limit), "peak_memory_mb": getattr(e, "peak_memory_mb", 0.0)}
        except SandboxError as e:
            logger.error("[%s] Sandbox fault during custom run: %s", submission_id, e)
            return {"verdict": "SYSTEM_ERROR", "output": "", "message": str(e)[:2000], "execution_time_ms": 0.0, "peak_memory_mb": 0.0}

        run_output = extract_file_from_container(container, "/workspace/actual_op.txt")

        if run_exit_code == 0:
            return {"verdict": "AC", "output": run_output, "message": "", "execution_time_ms": elapsed_ms, "peak_memory_mb": peak_mb}

        return {"verdict": map_exit_code(run_exit_code), "output": "", "message": run_stderr[:2000], "execution_time_ms": elapsed_ms, "peak_memory_mb": peak_mb}

    except SandboxError as e:
        logger.error("[%s] Sandbox fault during custom run: %s", submission_id, e)
        return {"verdict": "SYSTEM_ERROR", "output": "", "message": str(e)[:2000], "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
    except Exception:
        logger.exception(
            "[%s] Unhandled error during custom run (language=%s, time_limit=%s, memory_limit=%s)",
            submission_id, language, time_limit, memory_limit,
        )
        return {"verdict": "SYSTEM_ERROR", "output": "", "message": "", "execution_time_ms": 0.0, "peak_memory_mb": 0.0}
    finally:
        if container:
            try:
                container.stop(timeout=1)
            except Exception:
                pass
            try:
                container.remove(force=True)
            except Exception:
                pass