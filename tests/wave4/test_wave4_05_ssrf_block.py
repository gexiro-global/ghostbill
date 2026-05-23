from pathlib import Path


def test_webhook_url_blocks_credentials_and_private_ips():
    source = (Path("backend/app/core/tor_proxy.py")).read_text()
    assert "parsed.scheme not in" in source
    assert "parsed.username or parsed.password" in source
    assert "host_ip.is_private" in source
    assert "host_ip.is_loopback" in source
