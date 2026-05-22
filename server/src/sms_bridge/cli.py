"""
SMS Bridge CLI — install via pip, then:

  sms-bridge setup     interactive configuration wizard
  sms-bridge start     start the gateway server (background daemon)
  sms-bridge stop      stop the running daemon
  sms-bridge logs      tail the server log
  sms-bridge send      send an outbound SMS
  sms-bridge qr        display Android device pairing QR code
  sms-bridge status    show current configuration and running state
  sms-bridge upgrade   upgrade to the latest version from GitHub
  sms-bridge reset     remove saved configuration
"""
from __future__ import annotations

import asyncio
import io
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from sms_bridge.config import Config, DEFAULT_DATA_DIR, SMS_GATEWAY_DIR
from sms_bridge.config_store import ConfigStore, generate_api_key

console = Console()
store   = ConfigStore()

# Fixed paths — everything lives under ~/.sms-gateway
FCM_STUB_PATH = SMS_GATEWAY_DIR / "fcm-service-account.json"
PID_FILE      = SMS_GATEWAY_DIR / "sms-bridge.pid"
LOG_FILE      = SMS_GATEWAY_DIR / "sms-bridge.log"
TLS_CERT_PATH = SMS_GATEWAY_DIR / "cert.pem"
TLS_KEY_PATH  = SMS_GATEWAY_DIR / "key.pem"

FCM_STUB_CONTENT = {
    "_stub": True,
    "_instructions": [
        "Replace this file with your real Firebase service account JSON.",
        "",
        "How to get your FCM service account JSON:",
        "  1. Go to https://console.firebase.google.com",
        "  2. Open your project (or create one for this app)",
        "  3. Click the gear icon → Project Settings",
        "  4. Go to the 'Service accounts' tab",
        "  5. Click 'Generate new private key' → 'Generate key'",
        "  6. Overwrite this file with the downloaded JSON:",
        f"     {SMS_GATEWAY_DIR}/fcm-service-account.json",
        "",
        "Without a real credential, FCM wake-up is disabled.",
        "SMS still works as long as the device WebSocket stays connected.",
    ],
    "type": "service_account",
    "project_id": "YOUR_PROJECT_ID",
    "private_key_id": "YOUR_KEY_ID",
    "private_key": "-----BEGIN RSA PRIVATE KEY-----\nREPLACE_WITH_REAL_KEY\n-----END RSA PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk@YOUR_PROJECT_ID.iam.gserviceaccount.com",
    "client_id": "YOUR_CLIENT_ID",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk%40YOUR_PROJECT_ID.iam.gserviceaccount.com",
}

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


def _get_running_pid() -> int | None:
    """Return the PID from the PID file if the process is still alive, else None."""
    try:
        pid = int(PID_FILE.read_text().strip())
        # Check if process exists (signal 0 = existence check)
        os.kill(pid, 0)
        return pid
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        return None


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


def _generate_self_signed_cert(host: str, cert_path: Path, key_path: Path) -> None:
    """
    Generate a self-signed TLS certificate using Python's cryptography library
    (already a transitive dependency via firebase-admin / google-auth).
    The cert includes the host as a SAN so modern TLS stacks accept it.
    """
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    # Generate 2048-bit RSA key
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Build Subject Alternative Name — IP or DNS depending on what host looks like
    san: list[x509.GeneralName] = [x509.DNSName("localhost")]
    try:
        san.append(x509.IPAddress(ipaddress.ip_address(host)))
    except ValueError:
        san.append(x509.DNSName(host))

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, host),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "SMS Bridge (self-signed)"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))  # 10 years
        .add_extension(x509.SubjectAlternativeName(san), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    cert_path.parent.mkdir(parents=True, exist_ok=True)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert_path.chmod(0o644)          # cert is public — readable by anyone
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    key_path.chmod(0o600)           # key is private — owner-only


# ── CLI group ─────────────────────────────────────────────────────────────────

@click.group()
@click.version_option(version="0.1.6", prog_name="sms-bridge")
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
        resolved_cert = ""
        resolved_key  = ""
    else:
        console.print(
            "[bold]SSL / TLS[/bold]\n"
            "[dim]Use wss:// (recommended) or ws:// (local / behind an external TLS proxy).[/dim]"
        )
        use_ssl = click.confirm("  Use SSL (wss://)?", default=True)

        resolved_cert = ""
        resolved_key  = ""
        if use_ssl:
            console.print()
            existing_cert = existing.get("tls_cert_path", "")
            existing_key  = existing.get("tls_key_path", "")
            has_existing  = existing_cert and Path(existing_cert).exists()

            console.print(
                "[bold]TLS certificate[/bold]\n"
                "[dim]Choose a source for the TLS certificate:[/dim]\n"
            )
            console.print("  [bold]1[/bold]  Auto-generate a self-signed certificate (easiest — good for testing)")
            console.print("  [bold]2[/bold]  Use existing cert files (Let's Encrypt or your own)")
            if has_existing:
                console.print(f"  [bold]3[/bold]  Keep existing cert ({existing_cert})")
            console.print()

            max_choice = 3 if has_existing else 2
            cert_choice = click.prompt("  Select", type=click.IntRange(1, max_choice), default=1)

            if cert_choice == 1:
                console.print()
                console.print(f"  Generating self-signed cert for [cyan]{resolved_host}[/cyan]…")
                try:
                    _generate_self_signed_cert(resolved_host, TLS_CERT_PATH, TLS_KEY_PATH)
                    resolved_cert = str(TLS_CERT_PATH)
                    resolved_key  = str(TLS_KEY_PATH)
                    console.print(f"  [green]✓ Cert →  {TLS_CERT_PATH}[/green]")
                    console.print(f"  [green]✓ Key  →  {TLS_KEY_PATH}[/green]")
                    console.print()
                    console.print(Panel(
                        "[bold]Bundle the certificate into your Android app[/bold]\n\n"
                        "Copy the cert into the Android source, then rebuild:\n\n"
                        f"  [bold cyan]scp ubuntu@your-server:{TLS_CERT_PATH} \\\\\n"
                        "      android/app/src/main/res/raw/sms_bridge_cert.pem[/bold cyan]\n\n"
                        "  [bold cyan]./gradlew installDebug[/bold cyan]\n\n"
                        "[dim]Do this on the machine with the Android source code.[/dim]",
                        border_style="cyan",
                        title="[cyan]Next step[/cyan]",
                    ))
                except ImportError:
                    console.print("[red]✗ cryptography package not available — run: pip install cryptography[/red]")
                    use_ssl = False

            elif cert_choice == 2:
                resolved_cert = click.prompt(
                    "  Path to cert file (PEM)",
                    default=existing_cert or "/etc/letsencrypt/live/yourdomain/fullchain.pem",
                    prompt_suffix="\n  > ",
                )
                resolved_key = click.prompt(
                    "  Path to key file (PEM)",
                    default=existing_key or "/etc/letsencrypt/live/yourdomain/privkey.pem",
                    prompt_suffix="\n  > ",
                )
            else:
                # Keep existing
                resolved_cert = existing_cert
                resolved_key  = existing_key

    console.print()
    resolved_ws_url = _build_ws_url(resolved_host, resolved_ws, use_ssl)

    # ── Step 3: Firebase / FCM ────────────────────────────────────────────────
    console.rule("[bold]Step 3 · Firebase / FCM[/bold]")
    console.print()

    # Create the stub file if it doesn't already contain real credentials
    from sms_bridge.fcm.client import _is_stub
    if not FCM_STUB_PATH.exists() or _is_stub(str(FCM_STUB_PATH)):
        FCM_STUB_PATH.parent.mkdir(parents=True, exist_ok=True)
        FCM_STUB_PATH.write_text(json.dumps(FCM_STUB_CONTENT, indent=2))
        FCM_STUB_PATH.chmod(0o600)

    resolved_fcm = str(FCM_STUB_PATH)

    if not non_interactive:
        if _is_stub(resolved_fcm):
            console.print(
                f"A placeholder FCM credentials file has been created at:\n"
                f"  [bold cyan]{FCM_STUB_PATH}[/bold cyan]\n"
            )
            console.print(
                "[dim]To enable FCM wake-up (recommended for reliable delivery):[/dim]\n"
                "  1. Go to [link=https://console.firebase.google.com]console.firebase.google.com[/link]\n"
                "  2. Project Settings → Service accounts → [bold]Generate new private key[/bold]\n"
                f"  3. Overwrite [cyan]{FCM_STUB_PATH}[/cyan] with the downloaded JSON\n"
            )
            console.print(
                "[dim]SMS still works without this — the device just needs to keep its\n"
                "WebSocket connection open.[/dim]\n"
            )
        else:
            console.print(f"[green]✓ Real FCM credentials found at {FCM_STUB_PATH}[/green]\n")

    # ── Step 4: Storage ───────────────────────────────────────────────────────
    console.rule("[bold]Step 4 · Storage[/bold]")
    console.print()

    resolved_dd = data_dir or str(DEFAULT_DATA_DIR)
    if not non_interactive:
        console.print(
            f"Message queue directory: [cyan]{resolved_dd}[/cyan]\n"
            "[dim]Inbound and outbound SMS files are stored here.[/dim]\n"
        )
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
        tls_cert_path=resolved_cert,
        tls_key_path=resolved_key,
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
    tls_status = f"[green]{resolved_cert}[/green]" if resolved_cert else "[dim]disabled (ws://)[/dim]"
    t.add_row("TLS cert",       tls_status)
    fcm_status = "[yellow]stub — replace with real credentials[/yellow]" if _is_stub(resolved_fcm) else f"[green]{resolved_fcm}[/green]"
    t.add_row("FCM",            fcm_status)
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
@click.option(
    "--foreground", "-f", is_flag=True,
    help="Run in the foreground instead of daemonizing (useful for debugging).",
)
def start(foreground: bool) -> None:
    """Start the SMS Bridge gateway server (background daemon by default)."""
    cfg = _require_config()

    from sms_bridge.fcm.client import _is_stub

    fcm_path = cfg.fcm_service_account_path
    fcm_missing = (
        not fcm_path
        or not Path(fcm_path).exists()
        or _is_stub(fcm_path)
    )

    # ── Foreground mode ───────────────────────────────────────────────────────
    if foreground:
        console.print()
        if fcm_missing:
            console.print(Panel(
                "[bold yellow]⚠  FCM credentials not configured[/bold yellow]\n\n"
                "The server will start, but [bold]FCM wake-up is disabled[/bold].\n\n"
                "[bold]What this means:[/bold]\n"
                "  • If the Android app's WebSocket drops (screen off, network change,\n"
                "    Doze mode), outbound messages will queue but [bold]not be delivered\n"
                "    until the device reconnects on its own[/bold].\n"
                "  • Inbound SMS forwarding is unaffected — messages still flow while\n"
                "    the WebSocket is open.\n\n"
                "[bold]To fix:[/bold]\n"
                "  1. Go to [link=https://console.firebase.google.com]console.firebase.google.com[/link] "
                "→ Project Settings → Service accounts\n"
                "  2. Click [bold]Generate new private key[/bold]\n"
                f"  3. Overwrite  [cyan]{FCM_STUB_PATH}[/cyan]  with the downloaded JSON\n"
                "  4. Restart the server with  [bold cyan]sms-bridge start[/bold cyan]",
                border_style="yellow",
                title="[yellow]FCM disabled[/yellow]",
            ))
            console.print()

        tls_enabled = bool(cfg.tls_cert_path and Path(cfg.tls_cert_path).exists())
        console.print(Panel(
            f"[bold green]SMS Bridge v0.1.6[/bold green]\n\n"
            f"  MCP   →  [cyan]http://0.0.0.0:{cfg.mcp_port}/mcp[/cyan]\n"
            f"  WS    →  [cyan]{cfg.ws_url}[/cyan]\n"
            f"  TLS   →  {'[green]enabled[/green]' if tls_enabled else '[dim]disabled (ws://)[/dim]'}\n"
            f"  Data  →  [dim]{cfg.data_dir}[/dim]\n"
            f"  FCM   →  {'[yellow]disabled (stub)[/yellow]' if fcm_missing else '[green]enabled[/green]'}\n\n"
            f"[dim]Press Ctrl+C to stop[/dim]",
            border_style="green",
        ))
        console.print()

        from sms_bridge.main import run
        try:
            asyncio.run(run(cfg))
        except KeyboardInterrupt:
            console.print("\n[yellow]Server stopped.[/yellow]")
        return

    # ── Daemon mode (default) ─────────────────────────────────────────────────
    existing_pid = _get_running_pid()
    if existing_pid:
        console.print(f"[yellow]SMS Bridge is already running (PID {existing_pid}).[/yellow]")
        console.print("  Use [bold]sms-bridge stop[/bold] to stop it first.")
        sys.exit(1)

    # Ensure log directory exists
    SMS_GATEWAY_DIR.mkdir(parents=True, exist_ok=True)

    log_fh = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "sms_bridge", "start", "--foreground"],
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,   # detach from terminal
        close_fds=True,
    )
    PID_FILE.write_text(str(proc.pid))

    tls_enabled = bool(cfg.tls_cert_path and Path(cfg.tls_cert_path).exists())
    console.print()
    if fcm_missing:
        console.print(
            f"[yellow]⚠  FCM not configured[/yellow] — wake-up pushes disabled. "
            f"See [dim]{FCM_STUB_PATH}[/dim] for instructions.\n"
        )

    console.print(Panel(
        f"[bold green]SMS Bridge v0.1.6 started[/bold green]  "
        f"[dim](PID {proc.pid})[/dim]\n\n"
        f"  MCP   →  [cyan]http://0.0.0.0:{cfg.mcp_port}/mcp[/cyan]\n"
        f"  WS    →  [cyan]{cfg.ws_url}[/cyan]\n"
        f"  TLS   →  {'[green]enabled[/green]' if tls_enabled else '[dim]disabled (ws://)[/dim]'}\n"
        f"  Logs  →  [dim]{LOG_FILE}[/dim]\n\n"
        f"  [dim]sms-bridge stop[/dim]  to stop the server\n"
        f"  [dim]sms-bridge logs[/dim]  to tail the log",
        border_style="green",
    ))
    console.print()


# ── stop ──────────────────────────────────────────────────────────────────────

@cli.command()
def stop() -> None:
    """Stop the running SMS Bridge daemon."""
    pid = _get_running_pid()
    if pid is None:
        console.print("[yellow]SMS Bridge is not running.[/yellow]")
        return

    try:
        os.kill(pid, signal.SIGTERM)
        # Wait briefly and confirm
        import time
        for _ in range(20):
            time.sleep(0.25)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            # Still alive — escalate
            os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass  # already gone

    try:
        PID_FILE.unlink()
    except FileNotFoundError:
        pass

    console.print(f"[green]✓ SMS Bridge stopped (PID {pid}).[/green]")


# ── logs ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--lines", "-n", default=50, show_default=True, help="Number of recent lines to show.")
@click.option("--follow", "-f", is_flag=True, help="Follow log output (like tail -f).")
def logs(lines: int, follow: bool) -> None:
    """Show (or follow) the server log."""
    if not LOG_FILE.exists():
        console.print(f"[yellow]No log file found at {LOG_FILE}[/yellow]")
        console.print("  Start the server with  [bold]sms-bridge start[/bold]  first.")
        return

    if follow:
        try:
            subprocess.run(["tail", f"-n{lines}", "-f", str(LOG_FILE)])
        except KeyboardInterrupt:
            pass
    else:
        subprocess.run(["tail", f"-n{lines}", str(LOG_FILE)])


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


# ── send ──────────────────────────────────────────────────────────────────────

@cli.command()
@click.argument("to")
@click.argument("body")
@click.option("--device-id", "-d", default="any", show_default=True,
              help="Target device ID (omit to use any connected device).")
def send(to: str, body: str, device_id: str) -> None:
    """Send an outbound SMS through the gateway.

    \b
    TO    Destination phone number in E.164 format (e.g. +14155551234).
    BODY  Message text (quote it if it contains spaces).

    \b
    Examples:
      sms-bridge send +14155551234 "Hello from the CLI!"
      sms-bridge send +14155551234 "Hi" --device-id abc-123
    """
    import urllib.request
    import urllib.error

    cfg = _require_config()
    console.print()

    # ── Try the live server first (immediate delivery) ─────────────────────
    try:
        url     = f"http://localhost:{cfg.mcp_port}/api/send"
        payload = json.dumps({"to": to, "body": body, "device_id": device_id}).encode()
        req     = urllib.request.Request(
            url,
            data    = payload,
            headers = {
                "Authorization": f"Bearer {cfg.api_key}",
                "Content-Type":  "application/json",
            },
            method  = "POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())

        connected = result.get("device_connected", False)
        delivery  = (
            "[green]dispatched — device is connected[/green]"
            if connected else
            "[yellow]queued — device offline, will send on reconnect[/yellow]"
        )
        console.print(Panel(
            f"[bold green]✓  SMS sent[/bold green]\n\n"
            f"  To      [cyan]{to}[/cyan]\n"
            f"  Message {body}\n"
            f"  ID      [dim]{result['message_id']}[/dim]\n"
            f"  Status  {delivery}",
            border_style="green",
        ))

    except urllib.error.URLError:
        # ── Server not running — write directly to the file queue ──────────
        console.print(
            "[yellow]⚠  Server is not running — writing directly to queue.[/yellow]\n"
            "   Start the server ([bold cyan]sms-bridge start[/bold cyan]) to deliver the message.\n"
        )
        from sms_bridge.queue.file_queue import FileQueue
        queue = FileQueue(data_dir=cfg.data_dir)
        msg   = queue.enqueue_outbound(to=to, body=body, device_id=device_id)
        console.print(Panel(
            f"[bold yellow]SMS queued (server offline)[/bold yellow]\n\n"
            f"  To      [cyan]{to}[/cyan]\n"
            f"  Message {body}\n"
            f"  ID      [dim]{msg['id']}[/dim]\n"
            f"  Status  [yellow]pending — will send when server starts[/yellow]",
            border_style="yellow",
        ))

    except Exception as e:
        console.print(f"[red]✗ Error:[/red] {e}")
        sys.exit(1)

    console.print()


# ── gencert ───────────────────────────────────────────────────────────────────

@cli.command()
@click.option("--host", "-h", default=None,
              help="IP or hostname to embed in the certificate SAN. Defaults to the configured host.")
@click.option("--days", default=3650, show_default=True,
              help="Certificate validity in days.")
def gencert(host: str | None, days: int) -> None:
    """Generate (or regenerate) a self-signed TLS certificate."""
    cfg = store.load_raw() or {}
    resolved_host = host or cfg.get("_host") or "localhost"

    console.print()
    console.print(f"Generating self-signed TLS certificate for [cyan]{resolved_host}[/cyan]…")

    try:
        _generate_self_signed_cert(resolved_host, TLS_CERT_PATH, TLS_KEY_PATH)
    except ImportError:
        console.print("[red]✗ The 'cryptography' package is required:[/red]  pip install cryptography")
        sys.exit(1)

    # Persist cert/key paths into config
    if cfg:
        cfg["tls_cert_path"] = str(TLS_CERT_PATH)
        cfg["tls_key_path"]  = str(TLS_KEY_PATH)
        store.path.write_text(json.dumps(cfg, indent=2))

    console.print(f"[green]✓ Cert  →  {TLS_CERT_PATH}[/green]")
    console.print(f"[green]✓ Key   →  {TLS_KEY_PATH}[/green]")
    console.print()
    console.print(Panel(
        "[bold]Bundle the certificate into your Android app[/bold]\n\n"
        "The cert must be compiled into the APK so Android trusts it.\n"
        "Run this on the machine where you have the Android source:\n\n"
        f"  [bold cyan]scp ubuntu@your-server:{TLS_CERT_PATH} \\\\\n"
        "      android/app/src/main/res/raw/sms_bridge_cert.pem[/bold cyan]\n\n"
        "Then rebuild and reinstall the app:\n\n"
        "  [bold cyan]./gradlew installDebug[/bold cyan]\n\n"
        "You must repeat this whenever you regenerate the certificate.\n\n"
        "[dim]After reinstalling, re-scan the QR code and the wss:// handshake\n"
        "will succeed.[/dim]",
        border_style="cyan",
        title="[cyan]Next step[/cyan]",
    ))
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

    pid = _get_running_pid()
    running_str = f"[green]running (PID {pid})[/green]" if pid else "[dim]stopped[/dim]"

    t.add_row("Server",            running_str)
    t.add_row("Config file",       str(store.path))
    t.add_row("API key",           _mask(cfg.api_key))
    t.add_row("MCP port",          str(cfg.mcp_port))
    t.add_row("WebSocket URL",     cfg.ws_url)
    tls_val = cfg.tls_cert_path if cfg.tls_cert_path else "[dim]disabled[/dim]"
    t.add_row("TLS certificate",   tls_val)
    t.add_row("FCM credentials",   cfg.fcm_service_account_path or "[dim]not configured[/dim]")
    t.add_row("Data directory",    str(cfg.data_dir))
    t.add_row("Message retention", f"{cfg.message_retention_days} days")
    t.add_row("Log level",         cfg.log_level)
    if pid:
        t.add_row("Log file",      str(LOG_FILE))

    console.print(t)
    console.print()


# ── upgrade ───────────────────────────────────────────────────────────────────

_PACKAGE_URL = (
    "git+https://github.com/BlueDevil2k6/agentic-sms-gateway.git"
    "#subdirectory=server"
)

@cli.command()
@click.option("--restart", is_flag=True, default=False,
              help="Automatically restart the daemon after a successful upgrade.")
def upgrade(restart: bool) -> None:
    """Upgrade SMS Bridge to the latest version from GitHub."""
    import importlib.metadata

    current = importlib.metadata.version("sms-bridge")
    console.print()
    console.print(f"Current version: [cyan]{current}[/cyan]")
    console.print(f"Installing latest from GitHub…\n")

    was_running = _get_running_pid() is not None

    # Stop the daemon first so the running process doesn't hold file locks
    if was_running:
        console.print("[dim]Stopping server before upgrade…[/dim]")
        pid = _get_running_pid()
        if pid:
            try:
                import signal as _signal
                os.kill(pid, _signal.SIGTERM)
                import time as _time
                for _ in range(20):
                    _time.sleep(0.25)
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        break
            except ProcessLookupError:
                pass
            try:
                PID_FILE.unlink()
            except FileNotFoundError:
                pass

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", _PACKAGE_URL],
        text=True,
    )

    if result.returncode != 0:
        console.print("\n[red]✗ Upgrade failed.[/red]  Check the output above for details.")
        # Restart the old version if we stopped it
        if was_running:
            console.print("[dim]Restarting previous version…[/dim]")
            subprocess.Popen(
                [sys.executable, "-m", "sms_bridge", "start", "--foreground"],
                stdout=open(LOG_FILE, "a"), stderr=subprocess.STDOUT,
                start_new_session=True, close_fds=True,
            )
        sys.exit(1)

    # Read the new version from the freshly installed package
    try:
        # Force importlib to re-read metadata from disk
        import importlib.metadata as _meta
        new_version = _meta.version("sms-bridge")
    except Exception:
        new_version = "unknown"

    console.print()
    if new_version != current:
        console.print(f"[green]✓ Upgraded[/green]  {current} → [bold]{new_version}[/bold]")
    else:
        console.print(f"[green]✓ Already up to date[/green]  (v{current})")

    if was_running and (restart or new_version != current):
        console.print("[dim]Restarting server…[/dim]")
        SMS_GATEWAY_DIR.mkdir(parents=True, exist_ok=True)
        log_fh = open(LOG_FILE, "a")
        proc = subprocess.Popen(
            [sys.executable, "-m", "sms_bridge", "start", "--foreground"],
            stdout=log_fh, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )
        PID_FILE.write_text(str(proc.pid))
        console.print(f"[green]✓ Server restarted[/green]  (PID {proc.pid})")
    elif was_running:
        console.print(
            "\n[yellow]Note:[/yellow] Server was stopped for the upgrade. "
            "Run [bold cyan]sms-bridge start[/bold cyan] to restart it."
        )

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
