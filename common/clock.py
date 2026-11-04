"""Clock information each service reports, to verify the shared-clock assumption.

If all containers share one monotonic clock, (wall - monotonic) is the same
in every container, apart from tiny differences in when each pair was read.
The experiment runner compares the offsets that each service reports in
/stats before trusting cross-container latency values.
"""

import time


def clock_info() -> dict[str, int]:
    mono = time.monotonic_ns()
    wall = time.time_ns()
    return {"wall_ns": wall, "mono_ns": mono, "wall_minus_mono_ns": wall - mono}
