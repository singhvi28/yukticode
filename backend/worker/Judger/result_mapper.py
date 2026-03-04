def map_exit_code(exit_code: int) -> str:
    """
    Map a process exit code to a judge status string.

    Parameters:
    - exit_code (int): The exit code returned by the run command.

    Returns:
    - str: One of 'AC', 'RE', 'TLE', 'MLE', or 'UNKNOWN'.
    """
    return {
        0:   "AC",
        1:   "RE",
        143: "TLE",
        137: "MLE",
    }.get(exit_code, "UNKNOWN")
