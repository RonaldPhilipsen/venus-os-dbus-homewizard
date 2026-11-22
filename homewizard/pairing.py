"""Get an API token from a HomeWizard meter, one button press at a time."""

import re
import time
from typing import Callable, Optional

from homewizard.api import request_token

PAIR_WAIT_S = 60
NAME_PREFIX = "local/venus_"
MAX_NAME_LEN = 46


def user_name(host_name: str) -> str:
    """Build the user name that the meter stores with the token."""
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", host_name)
    cleaned = cleaned[: MAX_NAME_LEN - len(NAME_PREFIX)]
    return NAME_PREFIX + cleaned


def pair(
    host: str,
    name: str,
    wait_s: float = PAIR_WAIT_S,
    request: Callable[[str, str], Optional[str]] = request_token,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Optional[str]:
    """Ask for a token once a second until the button is pressed or time runs out.

    Returns None on timeout. Errors other than "button not pressed" propagate.
    """
    start = clock()
    while True:
        token = request(host, name)
        if token is not None:
            return token
        if clock() - start >= wait_s:
            return None
        sleep(1)
