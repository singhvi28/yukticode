def map_exit_code(exit_code: int) -> str:
    """
    Map a process exit code to a judge status string.

    Parameters:
    - exit_code (int): The exit code returned by the run command.

    Returns:
    - str: One of 'AC', 'RE', 'TLE', 'MLE', or 'SYSTEM_ERROR'.
      Never returns 'UNKNOWN' — unmapped codes fall back to 'RE'.
    """
    # 143 -> TLE is a safety net; run_with_gvisor normally raises TLEException
    # for 124/143 before map_exit_code is called.
    if exit_code in (126, 127):
        return "SYSTEM_ERROR"
    if exit_code > 128:
        # Signal deaths (e.g. 134 SIGABRT, 137 OOM, 139 SIGSEGV)
        if exit_code == 137:
            return "MLE"
        if exit_code == 143:
            return "TLE"
        return "RE"
    return {
        0: "AC",
        1: "RE",
        2: "RE",
    }.get(exit_code, "RE")
