#!/usr/bin/env python3
"""Get an API token from a HomeWizard meter. Run it on the GX device."""
import argparse
import functools
import os
import socket
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

from homewizard.api import ApiError, request_token  # noqa: E402
from homewizard.pairing import PAIR_WAIT_S, pair, user_name  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Get an API token from a HomeWizard meter.")
    parser.add_argument("host", help="address of the meter")
    parser.add_argument(
        "--name",
        default=user_name(socket.gethostname()),
        help="user name stored with the token (default: from the host name)",
    )
    parser.add_argument(
        "--insecure", action="store_true", help="skip the TLS certificate checks"
    )
    args = parser.parse_args(argv)

    print("Press the button on the meter now.")
    print("On a kWh meter, press the Wi-Fi button for 1 to 3 seconds.")
    print("A second pairing with the same name makes the old token invalid.")

    request = functools.partial(request_token, verify_tls=not args.insecure)
    try:
        token = pair(args.host, args.name, request=request)
    except ApiError as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1

    if token is None:
        print("No button press seen in {} seconds.".format(PAIR_WAIT_S), file=sys.stderr)
        return 1

    print("Token = {}".format(token))
    print("Paste this line into the [METER:...] section of config.ini.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
