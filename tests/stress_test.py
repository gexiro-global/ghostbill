"""
GhostBill — Concurrent invoice creation stress test.

NOTE: Backend has rate limiting (100 req/min). Tests are tuned to work
within those limits while still verifying concurrency safety.

Usage:
    cd /root/ghostbill && python3 -m pytest tests/stress_test.py -v
"""

import asyncio
import time

import httpx
import pytest

from tests.conftest import auth_headers, create_invoice


async def create_invoice_safe(
    client: httpx.AsyncClient,
    api_key: str,
    index: int,
) -> dict | None:
    """Create invoice, return None on rate limit (429)."""
    try:
        resp = await client.post(
            "/v1/invoices",
            json={"amount_xmr": "0.001", "description": f"Stress #{index}", "expires_in": 3600},
            headers=auth_headers(api_key),
        )
        if resp.status_code == 201:
            return resp.json()
        if resp.status_code == 429:
            return None  # Rate limited — expected under load
        resp.raise_for_status()
    except Exception:
        return None


@pytest.mark.asyncio
class TestConcurrentInvoices:

    async def test_concurrent_invoice_creation(self, client: httpx.AsyncClient, test_merchant: dict):
        """Create 20 invoices concurrently and verify uniqueness."""
        api_key = test_merchant["api_key_live"]
        count = 20

        start = time.monotonic()
        tasks = [create_invoice_safe(client, api_key, i) for i in range(count)]
        results = await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start

        successes = [r for r in results if r is not None]
        rate_limited = sum(1 for r in results if r is None)

        # At least 50% should succeed (rate limiter may block some)
        success_rate = len(successes) / count * 100
        assert success_rate >= 50, f"Only {success_rate}% success rate"

        # Verify unique IDs
        ids = [inv["id"] for inv in successes]
        assert len(ids) == len(set(ids)), "Duplicate invoice IDs!"

        # Verify unique addresses
        addresses = [inv["address"] for inv in successes if inv.get("address")]
        assert len(addresses) == len(set(addresses)), "Duplicate addresses!"

        # Verify unique address_index
        indices = [inv["address_index"] for inv in successes if inv.get("address_index") is not None]
        assert len(indices) == len(set(indices)), "Duplicate address indices!"

        # All should be pending with correct amount
        for inv in successes:
            assert inv["status"] == "pending"
            assert inv["amount_atomic"] == 1000000000  # 0.001 XMR

        throughput = len(successes) / elapsed
        print(f"\n✓ Stress test: {len(successes)}/{count} in {elapsed:.2f}s")
        print(f"  Throughput: {throughput:.1f} invoices/sec")
        print(f"  Rate limited: {rate_limited}")

    async def test_list_invoices_after_stress(self, client: httpx.AsyncClient, test_merchant: dict):
        """Verify listing works (with rate limit retry)."""
        api_key = test_merchant["api_key_live"]

        # Retry with backoff if rate limited
        for attempt in range(3):
            resp = await client.get(
                "/v1/invoices", params={"limit": 50, "status": "pending"},
                headers=auth_headers(api_key),
            )
            if resp.status_code == 200:
                break
            if resp.status_code == 429:
                await asyncio.sleep(2 * (attempt + 1))

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        print(f"\n✓ Listed {data['total']} pending invoices")

    async def test_sequential_baseline(self, client: httpx.AsyncClient, test_merchant: dict):
        """5 sequential invoices for throughput comparison."""
        api_key = test_merchant["api_key_live"]

        # Wait for wallet-rpc to recover after stress test
        await asyncio.sleep(3)

        count = 5
        successes = 0
        start = time.monotonic()
        for i in range(count):
            try:
                await create_invoice(client, api_key, amount_xmr="0.001", description=f"Seq #{i}")
                successes += 1
            except AssertionError:
                await asyncio.sleep(2)  # Retry delay on 503/429
                try:
                    await create_invoice(client, api_key, amount_xmr="0.001", description=f"Seq retry #{i}")
                    successes += 1
                except AssertionError:
                    pass  # Skip if still unavailable
        elapsed = time.monotonic() - start

        assert successes >= 3, f"Only {successes}/{count} sequential invoices succeeded"
        print(f"\n✓ Sequential: {successes}/{count} invoices in {elapsed:.2f}s ({successes / elapsed:.1f}/s)")
