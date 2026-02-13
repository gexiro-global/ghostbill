#!/usr/bin/env python3
"""
GhostBill CLI — Command-line management tool.

Usage:
    python ghostbill-cli.py --help
    python ghostbill-cli.py register --address 4... --view-key abc...
    python ghostbill-cli.py invoice create --amount 0.5
    python ghostbill-cli.py invoice list
    python ghostbill-cli.py status

Environment variables:
    GHOSTBILL_API_KEY    — API key (gb_live_... or gb_test_...)
    GHOSTBILL_URL        — Backend URL (default: http://127.0.0.1:8013)

Flags:
    --tor                — Route requests through Tor SOCKS5 proxy (127.0.0.1:9050)
    --key KEY            — Override API key
    --url URL            — Override backend URL
"""

import json
import os
import sys
from datetime import datetime
from decimal import Decimal

import click
import httpx
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# ─── Globals ─────────────────────────────────────────────────────────────────

console = Console()

DEFAULT_URL = "http://127.0.0.1:8013"
TOR_PROXY = "socks5://127.0.0.1:9050"

PICONERO = 10**12


# ─── Helpers ─────────────────────────────────────────────────────────────────


def get_client(ctx: click.Context) -> httpx.Client:
    """Build httpx client from context (URL, Tor, timeout)."""
    url = ctx.obj["url"]
    use_tor = ctx.obj["tor"]

    transport = None
    if use_tor:
        transport = httpx.HTTPTransport(proxy=TOR_PROXY)

    return httpx.Client(
        base_url=url,
        timeout=30.0,
        transport=transport,
    )


def get_headers(ctx: click.Context) -> dict:
    """Build auth headers from context."""
    key = ctx.obj.get("key")
    if not key:
        console.print("[red]Error:[/red] No API key set.")
        console.print("Set via: export GHOSTBILL_API_KEY=gb_live_...")
        console.print("Or use: --key gb_live_...")
        sys.exit(1)
    return {"Authorization": f"Bearer {key}"}


def format_xmr(atomic: int) -> str:
    """Format atomic units as XMR string."""
    xmr = Decimal(str(atomic)) / Decimal(str(PICONERO))
    return f"{xmr:.12f} XMR"


def format_time(iso_str: str | None) -> str:
    """Format ISO datetime string for display."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return iso_str


def status_color(status: str) -> str:
    """Return rich color markup for invoice/payment status."""
    colors = {
        "pending": "yellow",
        "paid": "green",
        "expired": "red",
        "partially_paid": "cyan",
        "overpaid": "magenta",
        "late_paid": "blue",
        "cancelled": "dim",
        "detected": "yellow",
        "confirmed": "green",
        "orphaned": "red",
        "delivered": "green",
        "failed": "red",
    }
    color = colors.get(status, "white")
    return f"[{color}]{status}[/{color}]"


def handle_error(resp: httpx.Response) -> None:
    """Print error details and exit."""
    try:
        data = resp.json()
        detail = data.get("detail", json.dumps(data, indent=2))
    except Exception:
        detail = resp.text

    console.print(f"[red]Error {resp.status_code}:[/red] {detail}")
    sys.exit(1)


# ─── Main Group ──────────────────────────────────────────────────────────────


@click.group()
@click.option(
    "--url",
    default=None,
    envvar="GHOSTBILL_URL",
    help="Backend URL (default: http://127.0.0.1:8013)",
)
@click.option(
    "--key",
    default=None,
    envvar="GHOSTBILL_API_KEY",
    help="API key (gb_live_... or gb_test_...)",
)
@click.option(
    "--tor",
    is_flag=True,
    default=False,
    help="Route through Tor SOCKS5 proxy (127.0.0.1:9050)",
)
@click.pass_context
def cli(ctx, url, key, tor):
    """GhostBill CLI — Monero payment gateway management."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url or DEFAULT_URL
    ctx.obj["key"] = key
    ctx.obj["tor"] = tor

    if tor:
        console.print("[dim]🧅 Tor proxy enabled[/dim]")


# ─── Register ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--address", required=True, help="Monero primary address (starts with 4)")
@click.option("--view-key", required=True, help="Monero secret view key (64 hex)")
@click.option("--name", default="My Store", help="Store name")
@click.option("--email", default=None, help="Contact email")
@click.option("--webhook-url", default=None, help="Webhook URL")
@click.pass_context
def register(ctx, address, view_key, name, email, webhook_url):
    """Register a new merchant."""
    client = get_client(ctx)

    payload = {
        "primary_address": address,
        "view_key": view_key,
        "name": name,
    }
    if email:
        payload["email"] = email
    if webhook_url:
        payload["webhook_url"] = webhook_url

    with client:
        resp = client.post("/v1/merchants", json=payload)

    if resp.status_code != 201:
        handle_error(resp)

    data = resp.json()

    panel_text = Text()
    panel_text.append("Merchant ID: ", style="bold")
    panel_text.append(data["merchant_id"] + "\n")
    panel_text.append("Name: ", style="bold")
    panel_text.append(data["name"] + "\n")
    panel_text.append("Environment: ", style="bold")
    panel_text.append(data["environment"] + "\n\n")
    panel_text.append("API Keys:\n", style="bold yellow")
    panel_text.append(f"  Live: {data['api_keys']['live']}\n", style="green")
    panel_text.append(f"  Test: {data['api_keys']['test']}\n", style="cyan")
    panel_text.append("\nWebhook Secret:\n", style="bold yellow")
    panel_text.append(f"  {data['webhook_secret']}\n", style="magenta")
    panel_text.append("\n⚠  Store these securely! They will NOT be shown again.", style="bold red")

    console.print(Panel(panel_text, title="✅ Merchant Registered", border_style="green"))


# ─── Status ──────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def status(ctx):
    """Check backend health and connectivity."""
    client = get_client(ctx)
    url = ctx.obj["url"]

    console.print(f"\n[bold]Checking {url}...[/bold]")

    try:
        with client:
            # Health
            resp = client.get("/health")
            if resp.status_code == 200:
                data = resp.json()
                console.print(f"  Health:  [green]✓ {data['status']}[/green] (v{data.get('version', '?')})")
            else:
                console.print(f"  Health:  [red]✗ HTTP {resp.status_code}[/red]")

            # Price
            price_resp = client.get("/v1/price")
            if price_resp.status_code == 200:
                price_data = price_resp.json()
                usd = price_data.get("xmr_usd") or price_data.get("usd", "N/A")
                console.print(f"  Price:   [green]✓[/green] XMR/USD = {usd}")
            else:
                console.print(f"  Price:   [yellow]⚠ HTTP {price_resp.status_code}[/yellow]")

            # Auth (if key set)
            key = ctx.obj.get("key")
            if key:
                me_resp = client.get(
                    "/v1/merchants/me",
                    headers={"Authorization": f"Bearer {key}"},
                )
                if me_resp.status_code == 200:
                    me = me_resp.json()
                    console.print(f"  Auth:    [green]✓[/green] Merchant: {me['name']} ({me['id'][:8]}...)")
                else:
                    console.print(f"  Auth:    [red]✗ HTTP {me_resp.status_code}[/red]")
            else:
                console.print("  Auth:    [dim]— No API key set[/dim]")

        console.print()

    except httpx.ConnectError as exc:
        console.print(f"  [red]✗ Connection failed: {exc}[/red]")
        sys.exit(1)
    except Exception as exc:
        console.print(f"  [red]✗ Error: {exc}[/red]")
        sys.exit(1)


# ─── Invoice Group ───────────────────────────────────────────────────────────


@cli.group()
def invoice():
    """Invoice management (create, list, get, cancel)."""
    pass


@invoice.command("create")
@click.option("--amount", required=True, help="Amount in XMR (e.g. 0.5)")
@click.option("--description", default=None, help="Invoice description")
@click.option("--expires-in", default=3600, type=int, help="Expiry in seconds (600-86400)")
@click.option("--metadata", default=None, help="JSON metadata string")
@click.pass_context
def invoice_create(ctx, amount, description, expires_in, metadata):
    """Create a new invoice."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    payload = {"amount_xmr": amount, "expires_in": expires_in}
    if description:
        payload["description"] = description
    if metadata:
        try:
            payload["metadata"] = json.loads(metadata)
        except json.JSONDecodeError:
            console.print("[red]Error:[/red] Invalid JSON in --metadata")
            sys.exit(1)

    with client:
        resp = client.post("/v1/invoices", json=payload, headers=headers)

    if resp.status_code != 201:
        handle_error(resp)

    inv = resp.json()

    table = Table(title="Invoice Created", show_header=False, border_style="green")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", inv["id"])
    table.add_row("Status", status_color(inv["status"]))
    table.add_row("Amount XMR", inv["amount_xmr"])
    table.add_row("Amount Atomic", f"{inv['amount_atomic']:,}")
    if inv.get("fiat_amount"):
        table.add_row("Fiat", f"${inv['fiat_amount']} {inv.get('fiat_currency', 'USD')}")
    table.add_row("Address", inv["address"] or "—")
    table.add_row("Address Index", str(inv.get("address_index", "—")))
    table.add_row("Expires", format_time(inv["expires_at"]))
    if inv.get("description"):
        table.add_row("Description", inv["description"])

    console.print(table)


@invoice.command("list")
@click.option("--status", "inv_status", default=None, help="Filter by status")
@click.option("--limit", default=20, type=int, help="Max results (1-100)")
@click.option("--offset", default=0, type=int, help="Offset for pagination")
@click.pass_context
def invoice_list(ctx, inv_status, limit, offset):
    """List invoices."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    params = {"limit": limit, "offset": offset}
    if inv_status:
        params["status"] = inv_status

    with client:
        resp = client.get("/v1/invoices", params=params, headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    data = resp.json()

    table = Table(title=f"Invoices (total: {data['total']})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Amount XMR", justify="right")
    table.add_column("Status")
    table.add_column("Created", max_width=20)
    table.add_column("Expires", max_width=20)
    table.add_column("Description", max_width=25)

    for inv in data["invoices"]:
        table.add_row(
            inv["id"][:12] + "...",
            inv["amount_xmr"],
            status_color(inv["status"]),
            format_time(inv["created_at"]),
            format_time(inv["expires_at"]),
            (inv.get("description") or "—")[:25],
        )

    console.print(table)
    if data["total"] > limit:
        console.print(f"[dim]Showing {len(data['invoices'])}/{data['total']}. Use --offset for more.[/dim]")


@invoice.command("get")
@click.argument("invoice_id")
@click.pass_context
def invoice_get(ctx, invoice_id):
    """Get invoice details by ID."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.get(f"/v1/invoices/{invoice_id}", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    inv = resp.json()

    table = Table(title="Invoice Details", show_header=False, border_style="blue")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", inv["id"])
    table.add_row("Merchant", inv["merchant_id"])
    table.add_row("Status", status_color(inv["status"]))
    table.add_row("Amount XMR", inv["amount_xmr"])
    table.add_row("Amount Atomic", f"{inv['amount_atomic']:,}")
    if inv.get("fiat_amount"):
        table.add_row("Fiat Amount", f"${inv['fiat_amount']} {inv.get('fiat_currency', '')}")
        table.add_row("Fiat Rate", str(inv.get("fiat_rate", "—")))
    table.add_row("Address", inv.get("address") or "—")
    table.add_row("Address Index", str(inv.get("address_index", "—")))
    table.add_row("Description", inv.get("description") or "—")
    table.add_row("Created", format_time(inv["created_at"]))
    table.add_row("Expires", format_time(inv["expires_at"]))
    table.add_row("Paid At", format_time(inv.get("paid_at")))

    if inv.get("metadata"):
        table.add_row("Metadata", json.dumps(inv["metadata"], indent=2))

    console.print(table)


@invoice.command("cancel")
@click.argument("invoice_id")
@click.confirmation_option(prompt="Are you sure you want to cancel this invoice?")
@click.pass_context
def invoice_cancel(ctx, invoice_id):
    """Cancel a pending invoice."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.post(f"/v1/invoices/{invoice_id}/cancel", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    inv = resp.json()
    console.print(f"[green]✓[/green] Invoice {inv['id'][:12]}... cancelled")


# ─── Payments ────────────────────────────────────────────────────────────────


@cli.group()
def payments():
    """Payment queries (list, get)."""
    pass


@payments.command("list")
@click.option("--invoice-id", default=None, help="Filter by invoice ID")
@click.option("--status", "pay_status", default=None, help="Filter by status")
@click.option("--limit", default=20, type=int)
@click.option("--offset", default=0, type=int)
@click.pass_context
def payments_list(ctx, invoice_id, pay_status, limit, offset):
    """List payments."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    params = {"limit": limit, "offset": offset}
    if invoice_id:
        params["invoice_id"] = invoice_id
    if pay_status:
        params["status"] = pay_status

    with client:
        resp = client.get("/v1/payments", params=params, headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    data = resp.json()

    table = Table(title=f"Payments (total: {data['total']})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Invoice", style="dim", max_width=12)
    table.add_column("TX Hash", max_width=16)
    table.add_column("Amount XMR", justify="right")
    table.add_column("Status")
    table.add_column("Confirmations", justify="right")
    table.add_column("Detected", max_width=20)

    for p in data["payments"]:
        table.add_row(
            p["id"][:12] + "...",
            p["invoice_id"][:12] + "...",
            p["tx_hash"][:16] + "...",
            p["amount_xmr"],
            status_color(p["status"]),
            str(p["confirmations"]),
            format_time(p["detected_at"]),
        )

    console.print(table)


@payments.command("get")
@click.argument("payment_id")
@click.pass_context
def payments_get(ctx, payment_id):
    """Get payment details by ID."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.get(f"/v1/payments/{payment_id}", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    p = resp.json()

    table = Table(title="Payment Details", show_header=False, border_style="blue")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", p["id"])
    table.add_row("Invoice", p["invoice_id"])
    table.add_row("TX Hash", p["tx_hash"])
    table.add_row("Amount XMR", p["amount_xmr"])
    table.add_row("Amount Atomic", f"{p['amount_atomic']:,}")
    table.add_row("Status", status_color(p["status"]))
    table.add_row("Confirmations", str(p["confirmations"]))
    table.add_row("Block Height", str(p.get("block_height") or "—"))
    table.add_row("Detected", format_time(p["detected_at"]))
    table.add_row("Confirmed", format_time(p.get("confirmed_at")))

    console.print(table)


# ─── Webhooks ────────────────────────────────────────────────────────────────


@cli.group()
def webhooks():
    """Webhook delivery log and retry."""
    pass


@webhooks.command("list")
@click.option("--invoice-id", default=None, help="Filter by invoice ID")
@click.option("--status", "wh_status", default=None, help="Filter by status")
@click.option("--limit", default=20, type=int)
@click.option("--offset", default=0, type=int)
@click.pass_context
def webhooks_list(ctx, invoice_id, wh_status, limit, offset):
    """List webhook deliveries."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    params = {"limit": limit, "offset": offset}
    if invoice_id:
        params["invoice_id"] = invoice_id
    if wh_status:
        params["status"] = wh_status

    with client:
        resp = client.get("/v1/webhooks", params=params, headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    data = resp.json()

    table = Table(title=f"Webhook Deliveries (total: {data['total']})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Event")
    table.add_column("Status")
    table.add_column("Attempts", justify="right")
    table.add_column("Response", justify="right")
    table.add_column("Created", max_width=20)

    for w in data["webhooks"]:
        table.add_row(
            w["id"][:12] + "...",
            w["event_type"],
            status_color(w["status"]),
            str(w["attempts"]),
            str(w.get("response_code") or "—"),
            format_time(w["created_at"]),
        )

    console.print(table)


@webhooks.command("get")
@click.argument("delivery_id")
@click.pass_context
def webhooks_get(ctx, delivery_id):
    """Get webhook delivery details."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.get(f"/v1/webhooks/{delivery_id}", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    w = resp.json()

    table = Table(title="Webhook Delivery", show_header=False, border_style="blue")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("ID", w["id"])
    table.add_row("Event", w["event_type"])
    table.add_row("Status", status_color(w["status"]))
    table.add_row("URL", w.get("url", "—"))
    table.add_row("Attempts", f"{w['attempts']}/{w.get('max_attempts', 7)}")
    table.add_row("Response Code", str(w.get("response_code") or "—"))
    table.add_row("Created", format_time(w["created_at"]))

    if w.get("payload"):
        table.add_row("Payload", json.dumps(w["payload"], indent=2))

    console.print(table)


@webhooks.command("retry")
@click.argument("delivery_id")
@click.pass_context
def webhooks_retry(ctx, delivery_id):
    """Retry a failed webhook delivery."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.post(f"/v1/webhooks/{delivery_id}/retry", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    console.print(f"[green]✓[/green] Webhook {delivery_id[:12]}... queued for retry")


# ─── API Keys ────────────────────────────────────────────────────────────────


@cli.group(name="api-keys")
def api_keys():
    """API key management (list, create, revoke)."""
    pass


@api_keys.command("list")
@click.pass_context
def api_keys_list(ctx):
    """List all API keys."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.get("/v1/api-keys", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    data = resp.json()

    # Handle various response formats
    if isinstance(data, list):
        keys = data
    elif isinstance(data, dict):
        keys = data.get("keys", data.get("api_keys", data.get("data", [])))
    else:
        keys = []

    table = Table(title=f"API Keys ({len(keys)})")
    table.add_column("ID", style="dim", max_width=12)
    table.add_column("Prefix")
    table.add_column("Environment")
    table.add_column("Label")
    table.add_column("Active")
    table.add_column("Last Used", max_width=20)

    for k in keys:
        active = "[green]✓[/green]" if k.get("is_active", True) else "[red]✗[/red]"
        table.add_row(
            k["id"][:12] + "...",
            k.get("key_prefix", "—"),
            k.get("environment", "—"),
            k.get("label", "—"),
            active,
            format_time(k.get("last_used_at")),
        )

    console.print(table)


@api_keys.command("create")
@click.option("--label", default="CLI key", help="Key label")
@click.option("--env", "environment", default="live", type=click.Choice(["live", "test"]))
@click.pass_context
def api_keys_create(ctx, label, environment):
    """Create a new API key."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.post(
            "/v1/api-keys",
            json={"label": label, "environment": environment},
            headers=headers,
        )

    if resp.status_code not in (200, 201):
        handle_error(resp)

    data = resp.json()

    panel_text = Text()
    panel_text.append("Key: ", style="bold")
    panel_text.append(data["key"] + "\n", style="green")
    panel_text.append("ID: ", style="bold")
    panel_text.append(data["id"] + "\n")
    panel_text.append("Environment: ", style="bold")
    panel_text.append(data.get("environment", environment) + "\n")
    panel_text.append("Label: ", style="bold")
    panel_text.append(label + "\n")
    panel_text.append("\n⚠  Store this key securely! It will NOT be shown again.", style="bold red")

    console.print(Panel(panel_text, title="🔑 API Key Created", border_style="green"))


@api_keys.command("revoke")
@click.argument("key_id")
@click.confirmation_option(prompt="Are you sure you want to revoke this key?")
@click.pass_context
def api_keys_revoke(ctx, key_id):
    """Revoke an API key."""
    client = get_client(ctx)
    headers = get_headers(ctx)

    with client:
        resp = client.delete(f"/v1/api-keys/{key_id}", headers=headers)

    if resp.status_code != 200:
        handle_error(resp)

    console.print(f"[green]✓[/green] API key {key_id[:12]}... revoked")


# ─── Price ───────────────────────────────────────────────────────────────────


@cli.command()
@click.pass_context
def price(ctx):
    """Get current XMR/USD price."""
    client = get_client(ctx)

    with client:
        resp = client.get("/v1/price")

    if resp.status_code != 200:
        handle_error(resp)

    data = resp.json()

    table = Table(title="XMR Price", show_header=False, border_style="blue")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    for key, val in data.items():
        table.add_row(key, str(val))

    console.print(table)


# ─── Entry Point ─────────────────────────────────────────────────────────────


if __name__ == "__main__":
    cli()
