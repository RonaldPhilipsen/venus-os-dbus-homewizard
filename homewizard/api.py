"""HTTPS client for the HomeWizard local API v2."""

import http.client
import json
import os
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple

CA_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ext", "homewizard-ca.pem"
)

API_VERSION = "2"
TOKEN_WAIT_ERROR = "user:creation-not-enabled"
SERIAL_PATTERN = re.compile(r"[0-9a-fA-F]{12}")
DEVICE_DOMAIN = "device.homewizard.energy"


class ApiError(Exception):
    """A request to the meter failed."""


class AuthError(ApiError):
    """The meter rejected the token (HTTP 401)."""


@dataclass
class DeviceInfo:
    product_name: str
    product_type: str
    serial: str
    firmware_version: str


def make_context(verify_tls: bool) -> ssl.SSLContext:
    """Build the TLS context.

    With verify_tls, the context checks the certificate chain against the
    HomeWizard CA. The name check happens after the handshake, see
    peer_matches, because the meters put their name in different fields.
    """
    if not verify_tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    ctx = ssl.create_default_context(cafile=CA_FILE)
    # The HomeWizard CA is an X.509 v1 certificate, which strict mode (3.13+) rejects.
    ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.check_hostname = False
    return ctx


def _dns_name(tls_name: str) -> Optional[str]:
    """Map appliance/<type>/<serial> to <serial>.<type>.device.homewizard.energy."""
    parts = tls_name.split("/")
    if len(parts) != 3 or parts[0] != "appliance" or not parts[1] or not parts[2]:
        return None
    return "%s.%s.%s" % (parts[2], parts[1], DEVICE_DOMAIN)


def peer_matches(cert: Dict[str, Any], tls_name: str) -> bool:
    """Tell whether a verified certificate belongs to the meter with tls_name.

    The P1 Meter puts appliance/<type>/<serial> in the common name only. The
    kWh Meter also has a DNS name <serial>.<type>.device.homewizard.energy.
    OpenSSL ignores the common name when a DNS name exists, so the driver
    checks both fields itself.
    """
    for rdn in cert.get("subject", ()):
        for key, value in rdn:
            if key == "commonName" and value == tls_name:
                return True
    dns_name = _dns_name(tls_name)
    if dns_name is None:
        return False
    for kind, value in cert.get("subjectAltName", ()):
        if kind == "DNS" and value.lower() == dns_name.lower():
            return True
    return False


class _Connection(http.client.HTTPSConnection):
    """HTTPS connection that checks the meter name after the handshake."""

    def __init__(self, host: str, timeout: float, context: ssl.SSLContext, tls_name: Optional[str]):
        super().__init__(host, 443, timeout=timeout, context=context)
        self._tls_name = tls_name
        self._tls_context = context

    def connect(self) -> None:
        sock = socket.create_connection((self.host, self.port), self.timeout)
        try:
            tls = self._tls_context.wrap_socket(sock)
        except BaseException:
            sock.close()
            raise
        if self._tls_name is not None and self._tls_context.verify_mode == ssl.CERT_REQUIRED:
            if not peer_matches(tls.getpeercert() or {}, self._tls_name):
                tls.close()
                raise ssl.SSLCertVerificationError(
                    "certificate is not valid for {}".format(self._tls_name)
                )
        self.sock = tls


def _parse_object(raw: bytes) -> Dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError as exc:
        raise ApiError("invalid JSON body: {}".format(exc)) from exc
    if not isinstance(data, dict):
        raise ApiError("JSON body is not an object")
    return data


def _status_error(status: int, raw: bytes) -> ApiError:
    text = raw[:200].decode("utf-8", "replace")
    message = "HTTP {}: {}".format(status, text) if text else "HTTP {}".format(status)
    if status == 401:
        return AuthError(message)
    return ApiError(message)


class Client:
    def __init__(
        self,
        host: str,
        token: Optional[str],
        verify_tls: bool = True,
        timeout: float = 2.0,
        connection_factory: Optional[Callable[[], Any]] = None,
    ):
        self.host = host
        self.token = token
        self.verify_tls = verify_tls
        self.timeout = timeout
        self._factory = connection_factory or self._default_connection
        self._tls_name = None  # type: Optional[str]
        self._context = None  # type: Optional[ssl.SSLContext]
        self._conn = None  # type: Any

    def set_tls_name(self, name: str) -> None:
        """Check the meter name from the next connection on."""
        self._tls_name = name
        self.close()

    def get_device(self) -> DeviceInfo:
        data = self._request("GET", "/api")
        try:
            product_name = data["product_name"]
            product_type = data["product_type"]
            serial = data["serial"]
            firmware_version = data["firmware_version"]
        except KeyError as exc:
            self.close()
            raise ApiError("device info misses {}".format(exc)) from exc
        if not isinstance(serial, str) or not SERIAL_PATTERN.fullmatch(serial):
            self.close()
            raise ApiError("device info has a serial that is not valid: {!r}".format(serial))
        if not isinstance(product_type, str) or not product_type:
            self.close()
            raise ApiError(
                "device info has a product type that is not valid: {!r}".format(product_type)
            )
        return DeviceInfo(
            product_name=str(product_name),
            product_type=product_type,
            serial=serial.lower(),
            firmware_version=str(firmware_version),
        )

    def get_measurement(self) -> Dict[str, Any]:
        return self._request("GET", "/api/measurement")

    def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _default_connection(self) -> _Connection:
        if self._context is None:
            self._context = make_context(self.verify_tls)
        return _Connection(self.host, self.timeout, self._context, self._tls_name)

    def _request(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        status, raw = self._exchange(method, path, payload)
        try:
            if status != 200:
                raise _status_error(status, raw)
            return _parse_object(raw)
        except ApiError:
            self.close()
            raise

    def _exchange(
        self, method: str, path: str, payload: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, bytes]:
        headers = {"X-Api-Version": API_VERSION}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            if self._conn is None:
                self._conn = self._factory()
            self._conn.request(method, path, body=body, headers=headers)
            response = self._conn.getresponse()
            return response.status, response.read()
        except (OSError, http.client.HTTPException) as exc:
            # ssl.SSLError and socket.timeout are OSError subclasses.
            self.close()
            raise ApiError("{} {} failed: {!r}".format(method, path, exc)) from exc
        except BaseException:
            self.close()
            raise


def request_token(
    host: str,
    name: str,
    verify_tls: bool = True,
    timeout: float = 2.0,
    connection_factory: Optional[Callable[[], Any]] = None,
) -> Optional[str]:
    """Ask the meter for a token.

    Returns None while the user has not pressed the button on the meter.
    """
    client = Client(host, None, verify_tls, timeout, connection_factory)
    try:
        status, raw = client._exchange("POST", "/api/user", {"name": name})
    finally:
        client.close()
    if status == 200:
        token = _parse_object(raw).get("token")
        if not isinstance(token, str) or not token:
            raise ApiError("token response has no token")
        return token
    if status == 403:
        try:
            error = _parse_object(raw).get("error")
        except ApiError:
            error = None
        if error == TOKEN_WAIT_ERROR:
            return None
    raise _status_error(status, raw)
