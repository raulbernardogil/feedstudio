"""Remote feed download with SSRF protection.

Controls:
- Only http(s) schemes; plain http must be explicitly allowed by settings.
- No credentials in URLs; only allowed ports.
- Every hostname is resolved and *all* resolved addresses must be public
  (``ipaddress.is_global``). Private, loopback, link-local (incl. the cloud
  metadata address 169.254.169.254), multicast and reserved ranges are refused.
- Redirects are followed manually (bounded) and every hop is re-validated.
- After connecting, the actual peer address is checked again, which defeats
  DNS-rebinding between validation and connection.
- The body is streamed to disk with a hard byte limit and the content is
  sniffed (XML or GZIP) regardless of the declared Content-Type.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin, urlsplit

import httpx

Resolver = Callable[[str, int], Iterable[str]]


class FetchError(Exception):
    def __init__(self, message: str, code: str = "fetch_failed"):
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass(frozen=True)
class FetchPolicy:
    allow_http: bool = False
    allowed_ports: tuple[int, ...] = (80, 443)
    max_bytes: int = 200 * 1024 * 1024
    max_redirects: int = 5
    timeout_seconds: float = 60.0
    allow_private_networks: bool = False  # only for local development/testing


@dataclass
class FetchResult:
    path: Path
    size_bytes: int
    sha256: str
    content_type: str | None
    final_url: str


def default_resolver(host: str, port: int) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError(f"No se pudo resolver el host '{host}'", code="dns_failed") from exc
    return sorted({info[4][0] for info in infos})


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_url(url: str, policy: FetchPolicy, resolver: Resolver = default_resolver) -> None:
    if len(url) > 2048:
        raise FetchError("La URL es demasiado larga", code="url_invalid")
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise FetchError("Solo se admiten URLs http/https", code="url_scheme")
    if scheme == "http" and not policy.allow_http:
        raise FetchError("Solo se admiten URLs HTTPS", code="url_scheme")
    if parts.username or parts.password:
        raise FetchError("La URL no puede contener credenciales", code="url_credentials")
    host = parts.hostname
    if not host:
        raise FetchError("La URL no tiene host", code="url_invalid")
    port = parts.port or (443 if scheme == "https" else 80)
    if port not in policy.allowed_ports:
        raise FetchError(f"Puerto {port} no permitido", code="url_port")
    if policy.allow_private_networks:
        return
    addresses = list(resolver(host, port))
    if not addresses:
        raise FetchError(f"No se pudo resolver el host '{host}'", code="dns_failed")
    for address in addresses:
        if not _is_public(address):
            raise FetchError("El destino apunta a una red privada o reservada", code="url_private")


def _check_peer(response: httpx.Response, policy: FetchPolicy) -> None:
    if policy.allow_private_networks:
        return
    stream = response.extensions.get("network_stream")
    if stream is None:
        return  # transports without sockets (tests); pre-resolution still applies
    peer = stream.get_extra_info("server_addr")
    if peer and not _is_public(str(peer[0])):
        raise FetchError("La conexión se resolvió a una red privada", code="url_private")


def _sniff(first_bytes: bytes) -> None:
    head = first_bytes.lstrip(b"\xef\xbb\xbf").lstrip()
    if head.startswith(b"\x1f\x8b") or head.startswith(b"<") or first_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return
    raise FetchError("El contenido descargado no es XML ni GZIP", code="not_xml")


def fetch_to_file(
    url: str,
    dest: Path,
    policy: FetchPolicy,
    resolver: Resolver = default_resolver,
    transport: httpx.BaseTransport | None = None,
) -> FetchResult:
    current = url
    with httpx.Client(
        follow_redirects=False,
        timeout=policy.timeout_seconds,
        transport=transport,
        headers={"User-Agent": "FeedStudio/0.1 (+feed importer)", "Accept": "application/xml, text/xml, */*"},
        trust_env=False,
    ) as client:
        for _ in range(policy.max_redirects + 1):
            validate_url(current, policy, resolver)
            try:
                with client.stream("GET", current) as response:
                    _check_peer(response, policy)
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("Redirección sin destino", code="redirect_invalid")
                        current = urljoin(current, location)
                        continue
                    if response.status_code != 200:
                        raise FetchError(f"El servidor respondió HTTP {response.status_code}", code="http_status")
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > policy.max_bytes:
                        raise FetchError("El archivo remoto supera el tamaño máximo", code="size_limit")
                    return _stream_body(response, dest, policy, current)
            except httpx.HTTPError as exc:
                raise FetchError(f"Error de red al descargar: {exc.__class__.__name__}", code="network") from exc
    raise FetchError("Demasiadas redirecciones", code="redirect_limit")


def _stream_body(response: httpx.Response, dest: Path, policy: FetchPolicy, final_url: str) -> FetchResult:
    digest = hashlib.sha256()
    size = 0
    sniffed = False
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with open(tmp, "wb") as out:
            for chunk in response.iter_bytes(64 * 1024):
                if not sniffed and chunk:
                    _sniff(chunk[:512])
                    sniffed = True
                size += len(chunk)
                if size > policy.max_bytes:
                    raise FetchError("El archivo remoto supera el tamaño máximo", code="size_limit")
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise FetchError("El archivo descargado está vacío", code="empty")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return FetchResult(dest, size, digest.hexdigest(), response.headers.get("content-type"), final_url)
