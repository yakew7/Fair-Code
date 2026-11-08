"""Helpers for tests whose timing depends on how busy the machine is (#1264, #1284)."""
import os


def load_factor(loadavg=None, cpus=None) -> float:
    """How much slower than an idle machine this one is right now (1.0 to 4.0): the one-minute load average per core, so a
    block that takes 5 s alone is not failed at 30 s because the suite runs on every core next to other work."""
    try:
        load = (loadavg or os.getloadavg)()[0]
    except (AttributeError, OSError):
        return 1.0
    return max(1.0, min(4.0, load / (cpus or os.cpu_count() or 1)))
