import http.client
import json
import os
import ssl

import pytest

from homewizard.api import (
    CA_FILE,
    ApiError,
    AuthError,
    Client,
    make_context,
    request_token,
)

TOKEN = "A" * 32
DEVICE_BODY = (
    b'{"product_name":"P1 Meter","product_type":"HWE-P1","serial":"5c2fafaabbcc",'
    b'"firmware_version":"6.00","api_version":"2.0.0"}'
)


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    def read(self):
        return self._body


class FakeConnection:
    def __init__(self, responses, error=None):
        self.responses = list(responses)
        self.error = error
        self.requests = []
        self.closed = False

    def request(self, method, path, body=None, headers=None):
        self.requests.append((method, path, body, headers))
        if self.error is not None:
            raise self.error

    def getresponse(self):
        status, body = self.responses.pop(0)
        return FakeResponse(status, body)

    def close(self):
        self.closed = True


class Factory:
    def __init__(self, *conns):
        self.conns = list(conns)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.conns.pop(0)


def test_get_device_sends_headers_and_parses():
    conn = FakeConnection([(200, DEVICE_BODY)])
    info = Client("h", TOKEN, connection_factory=lambda: conn).get_device()
    assert info.serial == "5c2fafaabbcc" and info.product_type == "HWE-P1"
    assert info.product_name == "P1 Meter" and info.firmware_version == "6.00"
    method, path, _, headers = conn.requests[0]
    assert (method, path) == ("GET", "/api")
    assert headers["X-Api-Version"] == "2" and headers["Authorization"] == "Bearer " + TOKEN


def test_client_without_token_sends_no_authorization():
    conn = FakeConnection([(200, b'{"power_w": 5}')])
    Client("h", None, connection_factory=lambda: conn).get_measurement()
    headers = conn.requests[0][3]
    assert headers["X-Api-Version"] == "2"
    assert "Authorization" not in headers


def test_get_measurement_returns_dict():
    conn = FakeConnection([(200, b'{"power_w": -123.4, "energy_import_kwh": 1.5}')])
    data = Client("h", TOKEN, connection_factory=lambda: conn).get_measurement()
    assert data == {"power_w": -123.4, "energy_import_kwh": 1.5}
    assert conn.requests[0][:2] == ("GET", "/api/measurement")


def test_401_raises_auth_error():
    conn = FakeConnection([(401, b'{"error":"user:unauthorized"}')])
    with pytest.raises(AuthError):
        Client("h", TOKEN, connection_factory=lambda: conn).get_measurement()


def test_other_status_raises_api_error_with_status():
    conn = FakeConnection([(500, b"")])
    with pytest.raises(ApiError) as exc:
        Client("h", TOKEN, connection_factory=lambda: conn).get_measurement()
    assert not isinstance(exc.value, AuthError)
    assert "500" in str(exc.value)


def test_garbage_body_raises_api_error():
    conn = FakeConnection([(200, b"<html>")])
    with pytest.raises(ApiError):
        Client("h", TOKEN, connection_factory=lambda: conn).get_measurement()


def test_non_object_json_raises_api_error():
    conn = FakeConnection([(200, b"[1,2]")])
    with pytest.raises(ApiError):
        Client("h", TOKEN, connection_factory=lambda: conn).get_measurement()


def test_oserror_closes_and_reconnects():
    broken = FakeConnection([], error=OSError("connection reset"))
    good = FakeConnection([(200, b'{"power_w": 1}')])
    factory = Factory(broken, good)
    client = Client("h", TOKEN, connection_factory=factory)
    with pytest.raises(ApiError) as exc:
        client.get_measurement()
    assert "connection reset" in str(exc.value)
    assert broken.closed
    assert client.get_measurement() == {"power_w": 1}
    assert factory.calls == 2


@pytest.mark.parametrize(
    "error",
    [
        ssl.SSLError("bad cert"),
        http.client.RemoteDisconnected("gone"),
    ],
)
def test_transport_errors_raise_api_error(error):
    conn = FakeConnection([], error=error)
    with pytest.raises(ApiError):
        Client("h", TOKEN, connection_factory=lambda: conn).get_measurement()
    assert conn.closed


def test_bad_status_closes_connection():
    first = FakeConnection([(500, b"")])
    second = FakeConnection([(200, b'{"power_w": 1}')])
    factory = Factory(first, second)
    client = Client("h", TOKEN, connection_factory=factory)
    with pytest.raises(ApiError):
        client.get_measurement()
    assert first.closed
    client.get_measurement()
    assert factory.calls == 2


def test_connection_reused_between_calls():
    conn = FakeConnection([(200, b'{"power_w": 1}'), (200, b'{"power_w": 2}')])
    factory = Factory(conn)
    client = Client("h", TOKEN, connection_factory=factory)
    assert client.get_measurement() == {"power_w": 1}
    assert client.get_measurement() == {"power_w": 2}
    assert factory.calls == 1


def test_set_tls_name_closes_connection():
    first = FakeConnection([(200, b'{"power_w": 1}')])
    second = FakeConnection([(200, b'{"power_w": 2}')])
    factory = Factory(first, second)
    client = Client("h", TOKEN, connection_factory=factory)
    client.get_measurement()
    client.set_tls_name("appliance/p1dongle/5c2fafaabbcc")
    assert first.closed
    client.get_measurement()
    assert factory.calls == 2


def test_close_closes_connection():
    conn = FakeConnection([(200, b'{"power_w": 1}')])
    client = Client("h", TOKEN, connection_factory=lambda: conn)
    client.get_measurement()
    client.close()
    assert conn.closed


def test_request_token_waits_on_403():
    conn = FakeConnection([(403, b'{"error":"user:creation-not-enabled"}')])
    assert request_token("h", "local/venus_x", connection_factory=lambda: conn) is None


def test_request_token_returns_token():
    conn = FakeConnection([(200, b'{"token":"ABCDEF0123456789","name":"local/venus_x"}')])
    assert request_token("h", "local/venus_x", connection_factory=lambda: conn) == "ABCDEF0123456789"
    method, path, body, headers = conn.requests[0]
    assert (method, path) == ("POST", "/api/user")
    assert json.loads(body) == {"name": "local/venus_x"}
    assert headers["X-Api-Version"] == "2"
    assert headers["Content-Type"] == "application/json"
    assert "Authorization" not in headers
    assert conn.closed


def test_request_token_other_403_raises():
    conn = FakeConnection([(403, b'{"error":"something:else"}')])
    with pytest.raises(ApiError):
        request_token("h", "local/venus_x", connection_factory=lambda: conn)


def test_request_token_other_status_raises():
    conn = FakeConnection([(500, b"")])
    with pytest.raises(ApiError):
        request_token("h", "local/venus_x", connection_factory=lambda: conn)


def test_ca_file_points_to_ext():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert CA_FILE == os.path.join(root, "ext", "homewizard-ca.pem")
    assert os.path.isfile(CA_FILE)


def test_context_verify_without_name_checks_chain_only():
    ctx = make_context(True, None)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_REQUIRED


def test_context_verify_with_name_checks_hostname():
    ctx = make_context(True, "appliance/p1dongle/x")
    assert ctx.check_hostname is True
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.hostname_checks_common_name is True


def test_context_no_verify():
    ctx = make_context(False, None)
    assert ctx.check_hostname is False
    assert ctx.verify_mode == ssl.CERT_NONE


def test_device_info_missing_field_raises_api_error():
    conn = FakeConnection([(200, b'{"product_type":"HWE-P1"}')])
    with pytest.raises(ApiError):
        Client("h", TOKEN, connection_factory=lambda: conn).get_device()
    assert conn.closed


def test_default_connection_uses_host_then_tls_name():
    client = Client("192.168.1.10", TOKEN, timeout=2.0)
    first = client._default_connection()
    assert (first.host, first.port, first.timeout) == ("192.168.1.10", 443, 2.0)
    assert first._server_hostname == "192.168.1.10"
    assert first._context.check_hostname is False
    client.set_tls_name("appliance/p1dongle/5c2fafaabbcc")
    second = client._default_connection()
    assert second._server_hostname == "appliance/p1dongle/5c2fafaabbcc"
    assert second._context is not first._context
    assert second._context.check_hostname is True
