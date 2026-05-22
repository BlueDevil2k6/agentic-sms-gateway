"""
SMS Bridge CLI — install via pip, then:

  sms-bridge setup    interactive configuration wizard
  sms-bridge start    start the gateway server
  sms-bridge qr       display Android device pairing QR code
  sms-bridge status   show current configuration
  sms-bridge reset    remove saved configuration
"""
from __future__ import annotations

import asyncio
import io
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from sms_bridge.config import Config, DEFAULT_DATA_DIR
from sms_bridge.config_store import ConfigStore, generate_api_key

console = Console()
store   = ConfigStore()

# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_config() -> Config:
    cfg = store.load()
    if cfg is None:
        console.print("[red]✗ No configuration found.[/red]")
        console.print("  Run [bold]sms-bridge setup[/bold] first.")
        sys.exit(1)
    return cfg


def _build_ws_url(host: str, ws_port: int, use_ssl: bool) -> str:
    scheme = "wss" if use_ssl else "ws"
    is_local = host in ("localhost", "127.0.0.1", "::1")
    if is_local:
        return f"ws://localhost:{ws_port}"
    return f"{scheme}://{host}:{ws_port}"


def _mask(key: str) -> str:
    return key[:12] + "••••••••" if len(key) > 12 else "••••••••"


def _detect_ips() -> list[tuple[str, str]]:
    """
    Return (interface_name, ipv4_address) for every non-loopback interface.
    Includes Tailscale (100.x.x.x), VPN tunnels (tun*/utun*), Ethernet, Wi-Fi, etc.
    Returns an empty list if psutil is not installed.
    """
    try:
        import socket
        import psutil
        results = []
        for iface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if (
                    addr.family == socket.AF_INET
                    and not addr.address.startswith("127.")
                    and addr.address != "0.0.0.0"
                ):
                    # Annotate well-known interface patterns
                    label = iface
                    il = iface.lower()
                    if "tailscale" in il or il.startswith("ts"):
                        label = f"{iface} [dim](Tailscale)[/dim]"
                    elif il.startswith("tun") or il.startswith("utun"):
                        label = f"{iface} [dim](VPN)[/dim]"
                    elif il.startswith("docker") or il.startswith("br-"):
                        label = f"{iface} [dim](Docker)[/dim]"
                    results.append((label, addr.address))
        return results
    except Exception:
        return []


# ── CLI group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version="0.1.0", prog_name="sms-bridge")
def cli() -> None:
    """SMS Bridge — Android SMS gateway for AI agents via MCP."""


# ── setup ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--non-interactive", is_flag=True, hidden=True,
              help="Skip prompts (for scripted installs; requires --api-key and --host)")
@click.option("--api-key",  default=None)
@click.option("--host",     default=None)
@click.option("--mcp-port", default=None, type=int)
@click.option("--ws-port",  default=None, type=int)
@click.option("--fcm-path", default=None)
@click.option("--data-dir", default=None)
@click.option("--log-level", default=None)
def setup(non_interactive, api_key, host, mcp_port, ws_port, fcm_path, data_dir, log_level):
    """Interactive configuration wizard."""

    # ── Header ────────────────────────────────────────────────────────────────
    console.print()
    console.print(Panel.fit(
        "[bold blue]SMS Bridge — Setup[/bold blue]\n"
        "[dim]Takes about 2 minutes. Config saved to ~/.config/sms-bridge/config.json[/dim]",
        border_style="blue",
    ))
    console.print()

    # Warn if overwriting
    if store.exists() and not non_interactive:
        console.print("[yellow]⚠ Existing configuration found.[/yellow]")
        if not click.confirm("Overwrite it?", default=False):
            console.print("Aborted.")
            return
        console.print()

    existing = store.load_raw() or {}

    # ── Step 1: Security ──────────────────────────────────────────────────────
    console.rule("[bold]Step 1 · Security[/bold]")
    console.print()

    default_key = existing.get("api_key") or generate_api_key()
    if non_interactive:
        resolved_api_key = api_key or default_key
    else:
        console.print("Your [bold]API key[/bold] authenticates both the Android device and AI agents.")
        console.print(f"[dim]Press Enter to use an auto-generated key.[/dim]")
        resolved_api_key = click.prompt(
            "API key",
            default=default_key,
            show_default=False,
            prompt_suffix="\n  > ",
        )
    console.print()

    # ── Step 2: Network ───────────────────────────────────────────────────────
    console.rule("[bold]Step 2 · Network[/bold]")
    console.print()

    default_host = existing.get("_host", "")
    if non_interactive:
        resolved_host = host or default_host or "localhost"
    else:
        console.print(
            "Choose the [bold]IP address or hostname[/bold] the Android app will use to reach this server.\n"
            "[dim]This is embedded in the pairing QR code.[/dim]\n"
        )

        detected = _detect_ips()

        if detected:
            # Build a selection table
            t = Table(box=box.SIMPLE, show_header=True, padding=(0, 2))
            t.add_column("#",          style="bold", width=3)
            t.add_column("Interface",  style="cyan")
            t.add_column("IP Address", style="green")
            for i, (iface, ip) in enumerate(detected, 1):
                t.add_row(str(i), iface, ip)
            t.add_row(
                str(len(detected) + 1),
                "[dim]custom[/dim]",
                "[dim]Enter manually[/dim]",
            )
            console.print(t)

            choice = click.prompt(
                f"Select",
                type=click.IntRange(1, len(detected) + 1),
                default=1,
            )
            if choice <= len(detected):
                resolved_host = detected[choice - 1][1]
                console.print(f"  Using [green]{resolved_host}[/green]")
            else:
                resolved_host = click.prompt(
                    "  Custom hostname or IP",
                    default=default_host or "localhost",
                    prompt_suffix="\n  > ",
                )
        else:
            # psutil not available — fall back to plain prompt
            console.print("[dim]Could not detect interfaces — enter manually.[/dim]")
            resolved_host = click.prompt(
                "Hostname / IP",
                default=default_host or "localhost",
                prompt_suffix="\n  > ",
            )
    console.print()

    default_mcp = existing.get("mcp_port", 8080)
    default_ws  = existing.get("ws_port", 8765)
    if non_interactive:
        resolved_mcp = mcp_port or default_mcp
        resolved_ws  = ws_port  or default_ws
    else:
        console.print("[bold]Ports[/bold]")
        resolved_mcp = click.prompt("  MCP port  (AI agents connect here)", default=default_mcp, type=int)
        resolved_ws  = click.prompt("  WebSocket port (Android device connects here)", default=default_ws, type=int)
    console.print()

    # Decide ws:// vs wss://
    is_local = resolved_host in ("localhost", "127.0.0.1", "::1")
    if non_interactive or is_local:
        use_ssl = not is_local
    else:
        console.print(
            "[bold]SSL / TLS[/bold]\n"
            "[dim]Use wss:// (recommended for production) or ws:// (local / behind a TLS proxy).[/dim]"
        )
        use_ssl = click.confirm("  Use SSL (wss://)?", default=True)
    console.print()

    resolved_ws_url = _build_ws_url(resolved_host, resolved_ws, use_ssl)

    # ── Step 3: Firebase ──────────────────────────────────────────────────────
    console.rule("[bold]Step 3 · Firebase / FCM (optional)[/bold]")
    console.print()

    default_fcm = existing.get("fcm_service_account_path", "")
    if non_interactive:
        resolved_fcm = fcm_path or default_fcm
    else:
        console.print(
            "Path to your [bold]FCM service account JSON[/bold] file.\n"
            "[dim]Enables push-wake when the Android WebSocket is closed.\n"
            "Press Enter to skip — SMS delivery will still work if the device stays connected.[/dim]"
        )
        raw_fcm = click.prompt(
            "FCM service account path",
            default=default_fcm or "",
            show_default=bool(default_fcm),
            prompt_suffix="\n  > ",
        )
        resolved_fcm = raw_fcm.strip()
        if resolved_fcm and not Path(resolved_fcm).exists():
            console.print(f"  [yellow]⚠ File not found: {resolved_fcm}[/yellow]  (saved anyway — fix the path before starting)")
    console.print()

    # ── Step 4: Storage ───────────────────────────────────────────────────────
    console.rule("[bold]Step 4 · Storage[/bold]")
    console.print()

    default_dd = existing.get("data_dir", str(DEFAULT_DATA_DIR))
    if non_interactive:
        resolved_dd = data_dir or default_dd
    else:
        console.print(
            "[bold]Message queue directory[/bold]\n"
            "[dim]Inbound and outbound SMS files are stored here.[/dim]"
        )
        resolved_dd = click.prompt("  Data directory", default=default_dd, prompt_suffix="\n  > ")
    console.print()

    log_choices = ["DEBUG", "INFO", "WARNING", "ERROR"]
    default_ll  = existing.get("log_level", "INFO")
    if non_interactive:
        resolved_ll = (log_level or default_ll).upper()
    else:
        resolved_ll = click.prompt(
            "Log level",
            default=default_ll,
            type=click.Choice(log_choices, case_sensitive=False),
        ).upper()

    # ── Save ──────────────────────────────────────────────────────────────────
    cfg = Config(
        api_key=resolved_api_key,
        mcp_port=resolved_mcp,
        ws_port=resolved_ws,
        ws_url=resolved_ws_url,
        fcm_service_account_path=resolved_fcm,
        data_dir=Path(resolved_dd),
        log_level=resolved_ll,
    )
    # Stash the plain host so we can re-populate it on next setup
    raw_dict = cfg.to_dict()
    raw_dict["_host"] = resolved_host
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text(json.dumps(raw_dict, indent=2))
    store.path.chmod(0o600)

    # ── Summary ───────────────────────────────────────────────────────────────
    console.print()
    console.print(f"[green]✓ Configuration saved to {store.path}[/green]")
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column(style="dim")
    t.add_column()
    t.add_row("API key",        _mask(resolved_api_key))
    t.add_row("MCP endpoint",   f"http://{resolved_host}:{resolved_mcp}/mcp")
    t.add_row("WebSocket URL",  resolved_ws_url)
    t.add_row("FCM",            resolved_fcm or "[dim]disabled[/dim]")
    t.add_row("Data dir",       resolved_dd)
    console.print(t)

    console.print()
    console.print(Panel(
        "[bold]Next steps[/bold]\n\n"
        "  Start the server:       [bold cyan]sms-bridge start[/bold cyan]\n"
        "  Pair Android device:    [bold cyan]sms-bridge qr[/bold cyan]",
        border_style="green",
    ))
    console.print()


# ── start ─────────────────────────────────────────────────────────────────────

@cli.command()
def start() -> None:
    """Start the SMS Bridge gateway server."""
    cfg = _require_config()

    console.print()
    console.print(Panel(
        f"[bold green]SMS Bridge v0.1.0[/bold green]\n\n"
        f"  MCP   →  [cyan]http://0.0.0.0:{cfg.mcp_port}/mcp[/cyan]\n"
        f"  WS    →  [cyan]{cfg.ws_url}[/cyan]\n"
        f"  Data  →  [dim]{cfg.data_dir}[/dim]\n\n"
        f"[dim]Press Ctrl+C to stop[/dim]",
        border_style="green",
    ))
    console.print()

    from sms_bridge.main import run
    try:
        asyncio.run(run(cfg))
    except KeyboardInterrupt:
        console.print("\n[yellow]Server stopped.[/yellow]")


# ── qr ────────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--device-name", "-n", default="My Gateway Phone",
              show_default=True, help="Name embedded in the QR code")
@click.option("--save", "-s", is_flag=True,
              help="Also save the QR code as sms-bridge-qr.png in the current directory")
def qr(device_name: str, save: bool) -> None:
    """Display the Android device pairing QR code."""
    cfg = _require_config()

    payload = json.dumps({
        "url": cfg.ws_url,
        "key": cfg.api_key,
        "name": device_name,
    })

    try:
        import qrcode as _qrcode
    except ImportError:
        console.print("[red]qrcode package not found — reinstall with: pip install 'sms-bridge[qr]'[/red]")
        sys.exit(1)

    qr_obj = _qrcode.QRCode(border=2)
    qr_obj.add_data(payload)
    qr_obj.make(fit=True)

    console.print()
    console.print(Panel.fit(
        f"[bold]Pairing QR Code[/bold]  [dim]·  {device_name}[/dim]",
        border_style="blue",
    ))
    console.print("[dim]Scan this with the SMS Bridge Android app:[/dim]\n")

    buf = io.StringIO()
    qr_obj.print_ascii(out=buf, invert=True)
    console.print(buf.getvalue())

    console.print(f"  [dim]WebSocket URL:[/dim]  {cfg.ws_url}")
    console.print(f"  [dim]API key:      [/dim]  {_mask(cfg.api_key)}")
    console.print()

    if save:
        img  = qr_obj.make_image(fill_color="black", back_color="white")
        dest = Path.cwd() / "sms-bridge-qr.png"
        img.save(dest)
        console.print(f"[green]✓ QR code saved to {dest}[/green]")
        console.print()


# ── status ────────────────────────────────────────────────────────────────────

@cli.command()
def status() -> None:
    """Show current configuration."""
    if not store.exists():
        console.print("[yellow]No configuration found.[/yellow]  Run [bold]sms-bridge setup[/bold].")
        return

    cfg = _require_config()

    console.print()
    console.print(Panel.fit("[bold]SMS Bridge — Configuration[/bold]", border_style="blue"))
    console.print()

    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    t.add_column(style="dim", min_width=24)
    t.add_column()

    t.add_row("Config file",       str(store.path))
    t.add_row("API key",           _mask(cfg.api_key))
    t.add_row("MCP port",          str(cfg.mcp_port))
    t.add_row("WebSocket URL",     cfg.ws_url)
    t.add_row("FCM credentials",   cfg.fcm_service_account_path or "[dim]not configured[/dim]")
    t.add_row("Data directory",    str(cfg.data_dir))
    t.add_row("Message retention", f"{cfg.message_retention_days} days")
    t.add_row("Log level",         cfg.log_level)

    console.print(t)
    console.print()


# ── reset ─────────────────────────────────────────────────────────────────────

@cli.command()
@click.confirmation_option(prompt="This will delete your saved configuration. Continue?")
def reset() -> None:
    """Delete saved configuration (does not affect message queue data)."""
    store.delete()
    console.print("[green]✓ Configuration deleted.[/green]")
    console.print("  Run [bold]sms-bridge setup[/bold] to reconfigure.")


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    cli()


if __name__ == "__main__":
    main()
