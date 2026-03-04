import logging
import uuid
import logging
logging.basicConfig(level=logging.DEBUG)
from .docker_manager import DockerManager
from .file_utils import put_files_to_container, extract_file_from_container
from .result_mapper import map_exit_code
from .languages.base import TLEException
from .languages.cpp import CppLanguage
from .languages.python import PythonLanguage

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

    for pattern in forbidden_patterns:
        if pattern in src_code:
            raise SecurityViolationException(f"Forbidden pattern detected: {pattern}")


def get_language_instance(language, container, time_limit, memory_limit):
    """
    Returns an instance of the language-specific class based on the provided language.
    """
    if language == 'cpp':
        return CppLanguage(container, time_limit, memory_limit)
    elif language == "py":
        return PythonLanguage(container, time_limit, memory_limit)
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
               src_code=None, std_in=None, expected_out=None):
    """
    Orchestrates the compilation and execution of the provided source code within an
    ephemeral Docker container using stream I/O, then compares the output.

    Returns a verdict string: "AC", "WA", "TLE", "CE", "RE", "MLE", or "SYSTEM_ERROR".
    Never raises — callers are guaranteed to receive a verdict they can forward to the user.
    """
    submission_id = str(uuid.uuid4())
    try:
        check_forbidden_patterns(language, src_code)

        dm = DockerManager(submission_id, time_limit, memory_limit)
        container = dm.start_container()
        language_instance = get_language_instance(language, container, time_limit, memory_limit)

        put_files_to_container(container, language, src_code, std_in, expected_out)

        if language in ["cpp", "java"]:
            compile_exit_code, _ = language_instance.compile(submission_id=submission_id)
            if compile_exit_code == 1:
                return "CE"

        try:
            run_exit_code, _ = language_instance.run(submission_id=submission_id)
        except TLEException:
            logger.warning("[%s] Time limit exceeded — stopping container", submission_id)
            try:
                container.stop(timeout=2)
            except Exception:
                pass
            return "TLE"

        if run_exit_code == 0:
            expected_op_data = extract_file_from_container(container, "/workspace/expected_op.txt")
            actual_op_data = extract_file_from_container(container, "/workspace/actual_op.txt")
            return "AC" if compare_outputs(expected_op_data, actual_op_data) else "WA"

        return map_exit_code(run_exit_code)

    except SecurityViolationException as e:
        logger.warning("[%s] Security violation: %s", submission_id, str(e))
        return "CE"  # Map static analysis failures to Compilation Error
    except Exception:
        logger.exception(
            "[%s] Unhandled error during judging (language=%s, time_limit=%s, memory_limit=%s)",
            submission_id, language, time_limit, memory_limit,
        )
        return "SYSTEM_ERROR"


def custom_run(language, time_limit, memory_limit,
               src_code=None, std_in=None):
    """
    Run code against a custom test case in an ephemeral container using stream I/O.

    Returns (verdict, output) where verdict is one of: "AC", "TLE", "CE", "RE",
    "MLE", "SYSTEM_ERROR". Never raises.
    """
    submission_id = str(uuid.uuid4())
    try:
        check_forbidden_patterns(language, src_code)

        dm = DockerManager(submission_id, time_limit, memory_limit)
        container = dm.start_container()
        language_instance = get_language_instance(language, container, time_limit, memory_limit)

        put_files_to_container(container, language, src_code, std_in)

        if language in ["cpp", "java"]:
            compile_exit_code, _ = language_instance.compile(submission_id=submission_id)
            if compile_exit_code == 1:
                return "CE", ""

        try:
            run_exit_code, _ = language_instance.run(submission_id=submission_id)
        except TLEException:
            logger.warning("[%s] Time limit exceeded — stopping container", submission_id)
            try:
                container.stop(timeout=2)
            except Exception:
                pass
            return "TLE", ""

        run_output = extract_file_from_container(container, "/workspace/actual_op.txt")

        if run_exit_code == 0:
            return "AC", run_output

        return map_exit_code(run_exit_code), ""

    except SecurityViolationException as e:
        logger.warning("[%s] Security violation in custom run: %s", submission_id, str(e))
        return "CE", ""
    except Exception:
        logger.exception(
            "[%s] Unhandled error during custom run (language=%s, time_limit=%s, memory_limit=%s)",
            submission_id, language, time_limit, memory_limit,
        )
        return "SYSTEM_ERROR", ""