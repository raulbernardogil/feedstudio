import gzip

import httpx
import pytest

from feedstudio.ingestion.fetcher import FetchError, FetchPolicy, fetch_to_file, validate_url

PUBLIC = {"feeds.example.com": ["93.184.216.34"], "cdn.example.com": ["93.184.216.35"], "evil.example.com": ["10.0.0.5"],
          "rebind.example.com": ["93.184.216.36", "127.0.0.1"], "v6.example.com": ["::ffff:192.168.1.1"]}


def resolver(host, port):
    if host in PUBLIC:
        return PUBLIC[host]
    import ipaddress

    ipaddress.ip_address(host)  # literal IPs resolve to themselves
    return [host]


POLICY = FetchPolicy()


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/f.xml", "https://10.1.2.3/f.xml", "https://169.254.169.254/latest/meta-data",
    "https://[::1]/f.xml", "https://evil.example.com/f.xml", "https://rebind.example.com/f.xml",
    "https://v6.example.com/f.xml", "https://0.0.0.0/f.xml", "https://100.64.0.1/f.xml",
])
def test_private_destinations_blocked(url):
    with pytest.raises(FetchError) as exc:
        validate_url(url, POLICY, resolver)
    assert exc.value.code == "url_private"


@pytest.mark.parametrize(("url", "code"), [
    ("ftp://feeds.example.com/f.xml", "url_scheme"), ("http://feeds.example.com/f.xml", "url_scheme"),
    ("https://u:p@feeds.example.com/f.xml", "url_credentials"), ("https://feeds.example.com:22/f.xml", "url_port"),
])
def test_url_policy(url, code):
    with pytest.raises(FetchError) as exc:
        validate_url(url, POLICY, resolver)
    assert exc.value.code == code


def test_public_url_allowed():
    validate_url("https://feeds.example.com/f.xml", POLICY, resolver)


def _transport(routes):
    def handler(request: httpx.Request):
        return routes[str(request.url)]()

    return httpx.MockTransport(handler)


def test_redirect_to_private_network_is_blocked(tmp_path):
    transport = _transport({
        "https://feeds.example.com/f.xml": lambda: httpx.Response(302, headers={"location": "https://169.254.169.254/latest"}),
    })
    with pytest.raises(FetchError) as exc:
        fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "f.xml", POLICY, resolver, transport)
    assert exc.value.code == "url_private"


def test_redirect_chain_followed_and_validated(tmp_path):
    body = b'<?xml version="1.0"?><rss><channel></channel></rss>'
    transport = _transport({
        "https://feeds.example.com/f.xml": lambda: httpx.Response(301, headers={"location": "https://cdn.example.com/real.xml"}),
        "https://cdn.example.com/real.xml": lambda: httpx.Response(200, content=body, headers={"content-type": "text/plain"}),
    })
    result = fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "f.xml", POLICY, resolver, transport)
    assert result.final_url == "https://cdn.example.com/real.xml"
    assert (tmp_path / "f.xml").read_bytes() == body


def test_redirect_loop_limited(tmp_path):
    transport = _transport({"https://feeds.example.com/f.xml": lambda: httpx.Response(302, headers={"location": "/f.xml"})})
    with pytest.raises(FetchError) as exc:
        fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "f.xml", POLICY, resolver, transport)
    assert exc.value.code == "redirect_limit"


def test_size_limit_and_content_sniffing(tmp_path):
    big = _transport({"https://feeds.example.com/f.xml": lambda: httpx.Response(200, content=b"<" + b"a" * 5000)})
    with pytest.raises(FetchError) as exc:
        fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "f.xml", FetchPolicy(max_bytes=1000), resolver, big)
    assert exc.value.code == "size_limit"
    assert not (tmp_path / "f.xml").exists()

    html = _transport({"https://feeds.example.com/f.xml": lambda: httpx.Response(200, content=b"\x89PNG....")})
    with pytest.raises(FetchError) as exc:
        fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "f.xml", POLICY, resolver, html)
    assert exc.value.code == "not_xml"

    gz = _transport({"https://feeds.example.com/f.xml": lambda: httpx.Response(200, content=gzip.compress(b"<rss/>"))})
    assert fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "g.xml", POLICY, resolver, gz).size_bytes > 0


def test_http_error_status(tmp_path):
    transport = _transport({"https://feeds.example.com/f.xml": lambda: httpx.Response(404)})
    with pytest.raises(FetchError) as exc:
        fetch_to_file("https://feeds.example.com/f.xml", tmp_path / "f.xml", POLICY, resolver, transport)
    assert exc.value.code == "http_status"
