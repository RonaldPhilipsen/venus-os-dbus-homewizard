import re

from homewizard.pairing import pair, user_name

TOKEN = "AB" * 16


class FakeClock:
    """Monotonic clock that only moves when the fake sleep is called."""

    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_user_name_cleans_and_limits():
    assert user_name("einstein") == "local/venus_einstein"
    assert user_name("my gx.local") == "local/venus_my_gx_local"
    assert re.match(r"^local\/[a-zA-Z0-9\-_/\\# ]{1,40}$", user_name("x" * 80))
    assert len(user_name("x" * 80)) == 46


def test_user_name_empty_host():
    assert user_name("") == "local/venus_"


def test_pair_retries_until_token():
    clock = FakeClock()
    responses = [None, None, TOKEN]
    calls = []

    def request(host, name):
        calls.append((host, name))
        return responses.pop(0)

    token = pair("192.0.2.5", "local/venus_test", request=request, sleep=clock.sleep, clock=clock)

    assert token == TOKEN
    assert calls == [("192.0.2.5", "local/venus_test")] * 3


def test_pair_times_out():
    clock = FakeClock()
    calls = []

    def request(host, name):
        calls.append(host)
        return None

    token = pair(
        "192.0.2.5", "local/venus_test", wait_s=60, request=request, sleep=clock.sleep, clock=clock
    )

    assert token is None
    assert clock.now >= 60
    assert len(calls) == 61
