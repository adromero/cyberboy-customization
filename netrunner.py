#!/usr/bin/env python3
"""
NetRunner v2.0 - Cyberpunk Network Toolkit
A TUI network testing tool for the Cyberboy handheld.

Keybindings:
  1-8: Switch modules
  Tab: Next field
  Enter: Execute
  Esc: Cancel/Back
  ?: Help
  q: Quit
  r: Refresh
  s: Save results (text)
  j: Save results (JSON)
  m: Toggle sound effects
"""

import asyncio
import ipaddress
import json
import os
import random
import re
import socket
import ssl
import struct
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    ProgressBar,
    RichLog,
    Select,
    Sparkline,
    Static,
    Switch,
    TabbedContent,
    TabPane,
    TextArea,
)

# Optional imports
try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    from zeroconf import ServiceBrowser, Zeroconf, ServiceListener
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False

# Results directory
RESULTS_DIR = Path.home() / "netrunner-results"
RESULTS_DIR.mkdir(exist_ok=True)

# OUI database for MAC lookups (common vendors)
OUI_DATABASE = {
    "00:00:0C": "Cisco",
    "00:1A:2B": "Cisco",
    "00:50:56": "VMware",
    "00:0C:29": "VMware",
    "08:00:27": "VirtualBox",
    "52:54:00": "QEMU/KVM",
    "B8:27:EB": "Raspberry Pi",
    "DC:A6:32": "Raspberry Pi",
    "E4:5F:01": "Raspberry Pi",
    "D8:3A:DD": "Raspberry Pi",
    "2C:CF:67": "Raspberry Pi",
    "00:1B:21": "Intel",
    "00:1E:67": "Intel",
    "00:1F:3B": "Intel",
    "3C:97:0E": "Intel",
    "AC:DE:48": "Intel",
    "00:24:D7": "Intel",
    "00:26:C6": "Intel",
    "00:26:C7": "Intel",
    "A4:83:E7": "Apple",
    "00:1C:B3": "Apple",
    "00:1D:4F": "Apple",
    "00:1E:C2": "Apple",
    "00:25:BC": "Apple",
    "3C:15:C2": "Apple",
    "F4:5C:89": "Apple",
    "00:1A:11": "Google",
    "54:60:09": "Google",
    "F4:F5:D8": "Google",
    "94:EB:2C": "Google",
    "00:04:4B": "Nvidia",
    "00:0D:61": "Nvidia",
    "00:50:F2": "Microsoft",
    "00:15:5D": "Microsoft",
    "00:1D:D8": "Microsoft",
    "28:18:78": "Microsoft",
    "7C:1E:52": "Microsoft",
    "00:0E:C6": "Asix",
    "00:11:32": "Synology",
    "00:1E:06": "Netgear",
    "00:1F:33": "Netgear",
    "00:22:3F": "Netgear",
    "00:26:F2": "Netgear",
    "C0:3F:0E": "Netgear",
    "00:18:E7": "TP-Link",
    "00:1D:0F": "TP-Link",
    "14:CC:20": "TP-Link",
    "50:C7:BF": "TP-Link",
    "C0:25:E9": "TP-Link",
    "00:17:88": "Philips",
    "00:1C:DF": "Belkin",
    "00:1E:3A": "Nokia",
    "00:21:4C": "Samsung",
    "00:26:37": "Samsung",
    "5C:0A:5B": "Samsung",
    "00:24:E8": "Dell",
    "14:FE:B5": "Dell",
    "18:A9:05": "Hewlett-Packard",
    "00:1B:78": "Hewlett-Packard",
    "00:1E:0B": "Hewlett-Packard",
    "00:23:7D": "Hewlett-Packard",
    "00:1A:4B": "Hewlett-Packard",
    "54:EE:75": "Wistron",
    "00:E0:4C": "Realtek",
    "52:54:AB": "Realtek",
    "00:1F:1F": "Edimax",
    "00:0E:2E": "Edimax",
    "74:DA:38": "Edimax",
    "00:1C:10": "Cisco-Linksys",
    "00:1E:58": "D-Link",
    "00:22:B0": "D-Link",
    "00:26:5A": "D-Link",
    "1C:7E:E5": "D-Link",
    "28:10:7B": "D-Link",
}

# Hacker quotes for cyberpunk feel
HACKER_QUOTES = [
    "The Net is vast and infinite...",
    "I am the ghost in the machine.",
    "Information wants to be free.",
    "The street finds its own uses for things.",
    "We are all connected in the great machine.",
    "Hack the planet!",
    "There is no spoon.",
    "Stay frosty, netrunner.",
    "In cyberspace, no one can hear you scream.",
    "The future is already here.",
    "I see the code in the Matrix now.",
    "Access granted.",
    "Welcome to the grid.",
    "Your mind is software. Program it.",
    "Reality is just a simulation.",
    "The network is my home.",
    "Jacking in...",
    "Run silent, run deep.",
    "Trust no one, trust the code.",
    "The data must flow.",
]


def get_local_ip() -> str:
    """Get the local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "No connection"


def get_default_gateway() -> str:
    """Get the default gateway."""
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=5
        )
        match = re.search(r'default via (\S+)', result.stdout)
        return match.group(1) if match else "Unknown"
    except Exception:
        return "Unknown"


def get_network_cidr() -> str:
    """Get the local network in CIDR notation."""
    try:
        local_ip = get_local_ip()
        if local_ip == "No connection":
            return "192.168.1.0/24"
        parts = local_ip.split('.')
        return f"{parts[0]}.{parts[1]}.{parts[2]}.0/24"
    except Exception:
        return "192.168.1.0/24"


def lookup_mac_vendor(mac: str) -> str:
    """Look up vendor from MAC address."""
    mac_clean = mac.upper().replace("-", ":").replace(".", ":")
    # Get first 3 octets
    prefix = ":".join(mac_clean.split(":")[:3])
    return OUI_DATABASE.get(prefix, "Unknown")


def calculate_subnet(cidr: str) -> dict:
    """Calculate subnet information from CIDR notation."""
    try:
        network = ipaddress.ip_network(cidr, strict=False)
        return {
            "network": str(network.network_address),
            "netmask": str(network.netmask),
            "broadcast": str(network.broadcast_address),
            "first_host": str(network.network_address + 1),
            "last_host": str(network.broadcast_address - 1),
            "num_hosts": network.num_addresses - 2,
            "prefix_len": network.prefixlen,
            "wildcard": str(network.hostmask),
        }
    except Exception as e:
        return {"error": str(e)}


def create_wol_packet(mac: str) -> bytes:
    """Create a Wake-on-LAN magic packet."""
    mac_clean = mac.replace(":", "").replace("-", "").replace(".", "")
    if len(mac_clean) != 12:
        raise ValueError("Invalid MAC address")
    mac_bytes = bytes.fromhex(mac_clean)
    return b'\xff' * 6 + mac_bytes * 16


def play_beep(frequency: int = 1000, duration: int = 100) -> None:
    """Play a beep sound (non-blocking)."""
    try:
        # Use system beep via speaker-test or paplay
        subprocess.Popen(
            ["timeout", "0.1", "speaker-test", "-t", "sine", "-f", str(frequency), "-l", "1"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # Silently fail if no audio


class HelpScreen(ModalScreen):
    """Help overlay screen."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static("""[bold cyan]
    _   __     __  ____
   / | / /__  / /_/ __ \\__  ______  ____  ___  _____
  /  |/ / _ \\/ __/ /_/ / / / / __ \\/ __ \\/ _ \\/ ___/
 / /|  /  __/ /_/ _, _/ /_/ / / / / / / /  __/ /
/_/ |_/\\___/\\__/_/ |_|\\__,_/_/ /_/_/ /_/\\___/_/
                                            v2.0
[/bold cyan]""", classes="ascii-title"),
            Static("\n[bold magenta]KEYBINDINGS[/bold magenta]", classes="help-title"),
            Static("""
[yellow]1-8[/yellow]     Switch between modules
[yellow]Tab[/yellow]     Move to next input field
[yellow]Enter[/yellow]   Execute current action
[yellow]Esc[/yellow]     Cancel or go back
[yellow]?[/yellow]       Show this help screen
[yellow]q[/yellow]       Quit NetRunner
[yellow]r[/yellow]       Refresh current view
[yellow]s[/yellow]       Save results to text file
[yellow]j[/yellow]       Save results to JSON file
[yellow]m[/yellow]       Toggle sound effects

[bold cyan]MODULES[/bold cyan]
[yellow]1[/yellow] Scanner  - Network/port/ARP scanning, MAC lookup
[yellow]2[/yellow] DNS      - DNS lookups, WHOIS, SSL/TLS checker
[yellow]3[/yellow] WiFi     - Wireless analysis, bandwidth monitor
[yellow]4[/yellow] Ping     - Ping & traceroute tools
[yellow]5[/yellow] Speed    - Network speed testing
[yellow]6[/yellow] Monitor  - Traffic, connections, VPN status
[yellow]7[/yellow] Tools    - Subnet calc, WoL, mDNS, hosts editor
[yellow]8[/yellow] Geo      - IP geolocation lookup

[muted]Press Esc or ? to close[/muted]
            """),
            id="help-container",
            classes="help-overlay",
        )


class ScannerModule(Container):
    """Network scanning module with ARP and MAC lookup."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Target:", classes="form-label"),
                Input(placeholder="IP, range, or CIDR (e.g., 192.168.1.0/24)", id="scan-target"),
                classes="form-row",
            ),
            Horizontal(
                Label("Scan Type:", classes="form-label"),
                Select([
                    ("Quick Ping Scan", "ping"),
                    ("ARP Scan (fast)", "arp"),
                    ("Port Scan (Common)", "ports"),
                    ("Port Scan (Full)", "full"),
                    ("Service Detection", "services"),
                    ("OS Detection (sudo)", "os"),
                    ("Aggressive (sudo)", "aggressive"),
                ], id="scan-type", value="ping"),
                classes="form-row",
            ),
            Horizontal(
                Button("Scan", id="btn-scan", variant="primary"),
                Button("Scan Local", id="btn-scan-local"),
                Button("MAC Lookup", id="btn-mac-lookup"),
                Button("Clear", id="btn-scan-clear", variant="error"),
                classes="form-row",
            ),
            Static("", id="scan-status", classes="status-text"),
            RichLog(id="scan-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-scan")
    def do_scan(self) -> None:
        target = self.query_one("#scan-target", Input).value.strip()
        if not target:
            self.query_one("#scan-status", Static).update("[red]Please enter a target[/red]")
            return
        scan_type = self.query_one("#scan-type", Select).value
        if scan_type == "arp":
            self.run_arp_scan(target)
        else:
            self.run_scan(target, scan_type)

    @on(Button.Pressed, "#btn-scan-local")
    def scan_local(self) -> None:
        target = get_network_cidr()
        self.query_one("#scan-target", Input).value = target
        self.run_arp_scan(target)

    @on(Button.Pressed, "#btn-mac-lookup")
    def mac_lookup(self) -> None:
        target = self.query_one("#scan-target", Input).value.strip()
        log = self.query_one("#scan-results", RichLog)
        if not target:
            self.query_one("#scan-status", Static).update("[red]Enter a MAC address[/red]")
            return
        vendor = lookup_mac_vendor(target)
        log.write(f"[cyan]MAC Address:[/cyan] {target}")
        log.write(f"[green]Vendor:[/green] {vendor}")

    @on(Button.Pressed, "#btn-scan-clear")
    def clear_results(self) -> None:
        self.query_one("#scan-results", RichLog).clear()
        self.query_one("#scan-status", Static).update("")

    @work(exclusive=True)
    async def run_arp_scan(self, target: str) -> None:
        """Fast ARP scan using arp-scan or nmap."""
        log = self.query_one("#scan-results", RichLog)
        status = self.query_one("#scan-status", Static)

        status.update("[cyan]Running ARP scan...[/cyan]")
        log.write(f"[cyan]> ARP scan {target}[/cyan]\n")

        try:
            # Try arp-scan first, fall back to nmap
            proc = await asyncio.create_subprocess_exec(
                "sudo", "nmap", "-sn", "-PR", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async for line in proc.stdout:
                text = line.decode().rstrip()
                if "Nmap scan report" in text:
                    log.write(f"[cyan]{text}[/cyan]")
                elif "MAC Address" in text:
                    # Extract and lookup vendor
                    match = re.search(r'([0-9A-F:]{17})', text, re.I)
                    if match:
                        mac = match.group(1)
                        vendor = lookup_mac_vendor(mac)
                        log.write(f"[green]{text} ({vendor})[/green]")
                    else:
                        log.write(f"[green]{text}[/green]")
                elif "Host is up" in text:
                    log.write(f"[yellow]{text}[/yellow]")
                else:
                    log.write(text)

            await proc.wait()
            status.update("[green]ARP scan complete[/green]")
            if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                play_beep(1500, 50)

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Scan failed[/red]")

    @work(exclusive=True)
    async def run_scan(self, target: str, scan_type: str) -> None:
        log = self.query_one("#scan-results", RichLog)
        status = self.query_one("#scan-status", Static)

        cmd = ["nmap"]
        if scan_type == "ping":
            cmd.extend(["-sn", target])
            status.update("[cyan]Running ping scan...[/cyan]")
        elif scan_type == "ports":
            cmd.extend(["-sT", "--top-ports", "100", target])
            status.update("[cyan]Scanning top 100 ports...[/cyan]")
        elif scan_type == "full":
            cmd.extend(["-sT", "-p-", target])
            status.update("[cyan]Full port scan...[/cyan]")
        elif scan_type == "services":
            cmd.extend(["-sV", "--top-ports", "100", target])
            status.update("[cyan]Detecting services...[/cyan]")
        elif scan_type == "os":
            cmd = ["sudo", "nmap", "-O", target]
            status.update("[cyan]OS detection (sudo)...[/cyan]")
        elif scan_type == "aggressive":
            cmd = ["sudo", "nmap", "-A", "--top-ports", "100", target]
            status.update("[cyan]Aggressive scan (sudo)...[/cyan]")

        log.write(f"[cyan]> {' '.join(cmd)}[/cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async for line in proc.stdout:
                text = line.decode().rstrip()
                if "open" in text.lower():
                    log.write(f"[green]{text}[/green]")
                    if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                        play_beep(800, 30)
                elif "closed" in text.lower() or "filtered" in text.lower():
                    log.write(f"[yellow]{text}[/yellow]")
                elif "Host is up" in text or "Nmap scan report" in text:
                    log.write(f"[cyan]{text}[/cyan]")
                elif "MAC Address" in text:
                    match = re.search(r'([0-9A-F:]{17})', text, re.I)
                    if match:
                        vendor = lookup_mac_vendor(match.group(1))
                        log.write(f"[green]{text} ({vendor})[/green]")
                    else:
                        log.write(f"[green]{text}[/green]")
                else:
                    log.write(text)

            await proc.wait()
            status.update("[green]Scan complete[/green]")
            if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                play_beep(1500, 100)

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Scan failed[/red]")


class DNSModule(Container):
    """DNS, WHOIS, and SSL/TLS checker module."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Target:", classes="form-label"),
                Input(placeholder="example.com or 8.8.8.8", id="dns-target"),
                classes="form-row",
            ),
            Horizontal(
                Label("Query Type:", classes="form-label"),
                Select([
                    ("A (IPv4)", "A"),
                    ("AAAA (IPv6)", "AAAA"),
                    ("MX (Mail)", "MX"),
                    ("NS (Nameservers)", "NS"),
                    ("TXT (Text)", "TXT"),
                    ("CNAME (Alias)", "CNAME"),
                    ("SOA (Authority)", "SOA"),
                    ("ANY (All)", "ANY"),
                    ("PTR (Reverse)", "PTR"),
                    ("WHOIS", "WHOIS"),
                    ("SSL/TLS", "SSL"),
                ], id="dns-type", value="A"),
                classes="form-row",
            ),
            Horizontal(
                Button("Lookup", id="btn-dns", variant="primary"),
                Button("WHOIS", id="btn-whois"),
                Button("SSL Check", id="btn-ssl"),
                Button("Clear", id="btn-dns-clear", variant="error"),
                classes="form-row",
            ),
            Static("", id="dns-status", classes="status-text"),
            RichLog(id="dns-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-dns")
    def do_dns(self) -> None:
        target = self.query_one("#dns-target", Input).value.strip()
        if not target:
            self.query_one("#dns-status", Static).update("[red]Please enter a domain or IP[/red]")
            return
        query_type = self.query_one("#dns-type", Select).value
        if query_type == "WHOIS":
            self.run_whois(target)
        elif query_type == "SSL":
            self.run_ssl_check(target)
        else:
            self.run_dns(target, query_type)

    @on(Button.Pressed, "#btn-whois")
    def do_whois(self) -> None:
        target = self.query_one("#dns-target", Input).value.strip()
        if target:
            self.run_whois(target)

    @on(Button.Pressed, "#btn-ssl")
    def do_ssl(self) -> None:
        target = self.query_one("#dns-target", Input).value.strip()
        if target:
            self.run_ssl_check(target)

    @on(Button.Pressed, "#btn-dns-clear")
    def clear_results(self) -> None:
        self.query_one("#dns-results", RichLog).clear()
        self.query_one("#dns-status", Static).update("")

    @work(exclusive=True)
    async def run_dns(self, target: str, query_type: str) -> None:
        log = self.query_one("#dns-results", RichLog)
        status = self.query_one("#dns-status", Static)

        status.update(f"[cyan]Querying {query_type} records...[/cyan]")
        log.write(f"[cyan]> dig {target} {query_type}[/cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "dig", "+noall", "+answer", "+authority", target, query_type,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if line:
                        if query_type in line:
                            log.write(f"[green]{line}[/green]")
                        else:
                            log.write(line)
            else:
                log.write("[yellow]No records found[/yellow]")

            status.update("[green]Lookup complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Lookup failed[/red]")

    @work(exclusive=True)
    async def run_whois(self, target: str) -> None:
        log = self.query_one("#dns-results", RichLog)
        status = self.query_one("#dns-status", Static)

        status.update(f"[cyan]WHOIS lookup for {target}...[/cyan]")
        log.write(f"[cyan]> whois {target}[/cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "whois", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if ':' in line:
                        key, _, value = line.partition(':')
                        key_lower = key.lower()
                        if any(k in key_lower for k in ['registr', 'name', 'organization', 'email', 'date', 'server']):
                            log.write(f"[cyan]{key}:[/cyan]{value}")
                        else:
                            log.write(line)
                    else:
                        log.write(line)

            status.update("[green]WHOIS complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]WHOIS failed[/red]")

    @work(exclusive=True)
    async def run_ssl_check(self, target: str) -> None:
        """Check SSL/TLS certificate information."""
        log = self.query_one("#dns-results", RichLog)
        status = self.query_one("#dns-status", Static)

        # Remove protocol prefix if present
        target = target.replace("https://", "").replace("http://", "").split("/")[0]

        status.update(f"[cyan]Checking SSL/TLS for {target}...[/cyan]")
        log.write(f"[cyan]> SSL/TLS check: {target}[/cyan]\n")

        try:
            context = ssl.create_default_context()

            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()

            def get_cert():
                with socket.create_connection((target, 443), timeout=10) as sock:
                    with context.wrap_socket(sock, server_hostname=target) as ssock:
                        cert = ssock.getpeercert()
                        cipher = ssock.cipher()
                        version = ssock.version()
                        return cert, cipher, version

            cert, cipher, version = await loop.run_in_executor(None, get_cert)

            # Parse certificate
            log.write(f"[bold cyan]Certificate Information[/bold cyan]")
            log.write(f"[green]TLS Version:[/green] {version}")
            log.write(f"[green]Cipher Suite:[/green] {cipher[0]}")
            log.write(f"[green]Key Size:[/green] {cipher[2]} bits")

            # Subject
            subject = dict(x[0] for x in cert.get('subject', []))
            log.write(f"\n[bold cyan]Subject[/bold cyan]")
            log.write(f"[green]Common Name:[/green] {subject.get('commonName', 'N/A')}")
            log.write(f"[green]Organization:[/green] {subject.get('organizationName', 'N/A')}")

            # Issuer
            issuer = dict(x[0] for x in cert.get('issuer', []))
            log.write(f"\n[bold cyan]Issuer[/bold cyan]")
            log.write(f"[green]Common Name:[/green] {issuer.get('commonName', 'N/A')}")
            log.write(f"[green]Organization:[/green] {issuer.get('organizationName', 'N/A')}")

            # Validity
            log.write(f"\n[bold cyan]Validity[/bold cyan]")
            not_before = cert.get('notBefore', 'N/A')
            not_after = cert.get('notAfter', 'N/A')
            log.write(f"[green]Not Before:[/green] {not_before}")
            log.write(f"[green]Not After:[/green] {not_after}")

            # Check expiry
            try:
                from datetime import datetime
                expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z")
                days_left = (expiry - datetime.now()).days
                if days_left < 0:
                    log.write(f"[red]EXPIRED {abs(days_left)} days ago![/red]")
                elif days_left < 30:
                    log.write(f"[yellow]Expires in {days_left} days[/yellow]")
                else:
                    log.write(f"[green]Expires in {days_left} days[/green]")
            except Exception:
                pass

            # SANs
            san = cert.get('subjectAltName', [])
            if san:
                log.write(f"\n[bold cyan]Subject Alt Names[/bold cyan]")
                for type_, value in san[:5]:  # Limit to 5
                    log.write(f"[green]{type_}:[/green] {value}")
                if len(san) > 5:
                    log.write(f"[gray]... and {len(san) - 5} more[/gray]")

            status.update("[green]SSL check complete[/green]")

        except ssl.SSLCertVerificationError as e:
            log.write(f"[red]Certificate verification failed![/red]")
            log.write(f"[red]{e}[/red]")
            status.update("[red]SSL verification failed[/red]")
        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]SSL check failed[/red]")


class WiFiModule(Container):
    """WiFi analyzer with bandwidth monitoring."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bandwidth_data = []
        self._monitoring = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Button("Scan Networks", id="btn-wifi-scan", variant="primary"),
                Button("Connection Info", id="btn-wifi-info"),
                Button("Bandwidth Monitor", id="btn-bandwidth"),
                Button("Clear", id="btn-wifi-clear", variant="error"),
                classes="form-row",
            ),
            Static("", id="wifi-status", classes="status-text"),
            Sparkline([], id="bandwidth-spark", summary_function=max),
            RichLog(id="wifi-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-wifi-scan")
    def scan_networks(self) -> None:
        self._monitoring = False
        self.run_wifi_scan()

    @on(Button.Pressed, "#btn-wifi-info")
    def show_info(self) -> None:
        self._monitoring = False
        self.run_wifi_info()

    @on(Button.Pressed, "#btn-bandwidth")
    def toggle_bandwidth(self) -> None:
        if self._monitoring:
            self._monitoring = False
            self.query_one("#wifi-status", Static).update("[yellow]Monitoring stopped[/yellow]")
        else:
            self._monitoring = True
            self.run_bandwidth_monitor()

    @on(Button.Pressed, "#btn-wifi-clear")
    def clear_results(self) -> None:
        self._monitoring = False
        self.query_one("#wifi-results", RichLog).clear()
        self.query_one("#wifi-status", Static).update("")
        self._bandwidth_data = []
        self.query_one("#bandwidth-spark", Sparkline).data = []

    @work(exclusive=True)
    async def run_wifi_scan(self) -> None:
        log = self.query_one("#wifi-results", RichLog)
        status = self.query_one("#wifi-status", Static)

        status.update("[cyan]Scanning for WiFi networks...[/cyan]")
        log.write("[cyan]> nmcli device wifi list[/cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY,CHAN,FREQ", "device", "wifi", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                log.write(f"{'SSID':<25} {'Signal':<8} {'Security':<15} {'Ch':<5} {'Freq':<10}")
                log.write("-" * 65)

                for line in stdout.decode().strip().split('\n'):
                    if line:
                        parts = line.split(':')
                        if len(parts) >= 5:
                            ssid, signal, security, chan, freq = parts[0], parts[1], parts[2], parts[3], parts[4]
                            signal_int = int(signal) if signal.isdigit() else 0
                            if signal_int >= 70:
                                color = "green"
                            elif signal_int >= 40:
                                color = "yellow"
                            else:
                                color = "red"
                            log.write(f"[{color}]{ssid:<25} {signal:>5}%   {security:<15} {chan:<5} {freq:<10}[/{color}]")

            status.update("[green]Scan complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Scan failed[/red]")

    @work(exclusive=True)
    async def run_wifi_info(self) -> None:
        log = self.query_one("#wifi-results", RichLog)
        status = self.query_one("#wifi-status", Static)

        status.update("[cyan]Getting connection info...[/cyan]")

        try:
            log.write("[cyan]Current Connection:[/cyan]")
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "NAME,TYPE,DEVICE", "connection", "show", "--active",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            for line in stdout.decode().strip().split('\n'):
                if line:
                    parts = line.split(':')
                    if len(parts) >= 3:
                        log.write(f"  [green]{parts[0]}[/green] ({parts[1]}) on {parts[2]}")

            log.write("\n[cyan]Network Configuration:[/cyan]")
            log.write(f"  Local IP:  [green]{get_local_ip()}[/green]")
            log.write(f"  Gateway:   [green]{get_default_gateway()}[/green]")

            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "IP4.DNS", "device", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            dns_servers = [line.split(':')[1] for line in stdout.decode().strip().split('\n') if ':' in line and line.split(':')[1]]
            if dns_servers:
                log.write(f"  DNS:       [green]{', '.join(set(dns_servers))}[/green]")

            status.update("[green]Info retrieved[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def run_bandwidth_monitor(self) -> None:
        """Monitor bandwidth in real-time."""
        log = self.query_one("#wifi-results", RichLog)
        status = self.query_one("#wifi-status", Static)
        spark = self.query_one("#bandwidth-spark", Sparkline)

        log.clear()
        log.write("[cyan]Bandwidth Monitor (updates every second)[/cyan]\n")
        status.update("[cyan]Monitoring bandwidth...[/cyan]")

        prev_rx, prev_tx = 0, 0
        self._bandwidth_data = []

        while self._monitoring:
            try:
                with open("/proc/net/dev") as f:
                    lines = f.readlines()[2:]

                total_rx, total_tx = 0, 0
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 10 and not parts[0].startswith("lo"):
                        total_rx += int(parts[1])
                        total_tx += int(parts[9])

                if prev_rx > 0:
                    rx_rate = (total_rx - prev_rx) / 1024  # KB/s
                    tx_rate = (total_tx - prev_tx) / 1024

                    self._bandwidth_data.append(rx_rate + tx_rate)
                    if len(self._bandwidth_data) > 60:
                        self._bandwidth_data.pop(0)

                    spark.data = self._bandwidth_data

                    # Format rates
                    def fmt_rate(r):
                        if r > 1024:
                            return f"{r/1024:.1f} MB/s"
                        return f"{r:.1f} KB/s"

                    log.write(f"[green]RX: {fmt_rate(rx_rate):<12}[/green] [cyan]TX: {fmt_rate(tx_rate):<12}[/cyan]")

                prev_rx, prev_tx = total_rx, total_tx
                await asyncio.sleep(1)

            except Exception as e:
                log.write(f"[red]Error: {e}[/red]")
                break

        status.update("[yellow]Monitoring stopped[/yellow]")


class PingModule(Container):
    """Ping and traceroute module."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Target:", classes="form-label"),
                Input(placeholder="IP or hostname", id="ping-target", value="8.8.8.8"),
                classes="form-row",
            ),
            Horizontal(
                Label("Count:", classes="form-label"),
                Input(placeholder="Number of pings", id="ping-count", value="5"),
                classes="form-row",
            ),
            Horizontal(
                Button("Ping", id="btn-ping", variant="primary"),
                Button("Traceroute", id="btn-trace"),
                Button("Stop", id="btn-ping-stop", variant="error"),
                classes="form-row",
            ),
            Static("", id="ping-status", classes="status-text"),
            RichLog(id="ping-results", highlight=True, markup=True),
            classes="module-container",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._current_proc = None

    @on(Button.Pressed, "#btn-ping")
    def do_ping(self) -> None:
        target = self.query_one("#ping-target", Input).value.strip()
        count = self.query_one("#ping-count", Input).value.strip()
        if not target:
            self.query_one("#ping-status", Static).update("[red]Please enter a target[/red]")
            return
        self.run_ping(target, count or "5")

    @on(Button.Pressed, "#btn-trace")
    def do_trace(self) -> None:
        target = self.query_one("#ping-target", Input).value.strip()
        if not target:
            self.query_one("#ping-status", Static).update("[red]Please enter a target[/red]")
            return
        self.run_traceroute(target)

    @on(Button.Pressed, "#btn-ping-stop")
    def stop_ping(self) -> None:
        if self._current_proc:
            try:
                self._current_proc.terminate()
            except Exception:
                pass
        self.query_one("#ping-status", Static).update("[yellow]Stopped[/yellow]")

    @work(exclusive=True)
    async def run_ping(self, target: str, count: str) -> None:
        log = self.query_one("#ping-results", RichLog)
        status = self.query_one("#ping-status", Static)

        status.update(f"[cyan]Pinging {target}...[/cyan]")
        log.write(f"[cyan]> ping -c {count} {target}[/cyan]\n")

        try:
            self._current_proc = await asyncio.create_subprocess_exec(
                "ping", "-c", count, target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async for line in self._current_proc.stdout:
                text = line.decode().rstrip()
                if "time=" in text:
                    match = re.search(r'time=(\d+\.?\d*)', text)
                    if match:
                        latency = float(match.group(1))
                        if latency < 50:
                            log.write(f"[green]{text}[/green]")
                        elif latency < 100:
                            log.write(f"[yellow]{text}[/yellow]")
                        else:
                            log.write(f"[red]{text}[/red]")
                    else:
                        log.write(text)
                elif "statistics" in text or "packets" in text:
                    log.write(f"[cyan]{text}[/cyan]")
                else:
                    log.write(text)

            await self._current_proc.wait()
            status.update("[green]Ping complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Ping failed[/red]")
        finally:
            self._current_proc = None

    @work(exclusive=True)
    async def run_traceroute(self, target: str) -> None:
        log = self.query_one("#ping-results", RichLog)
        status = self.query_one("#ping-status", Static)

        status.update(f"[cyan]Tracing route to {target}...[/cyan]")
        log.write(f"[cyan]> traceroute {target}[/cyan]\n")

        try:
            self._current_proc = await asyncio.create_subprocess_exec(
                "traceroute", "-m", "20", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async for line in self._current_proc.stdout:
                text = line.decode().rstrip()
                if re.match(r'^\s*\d+', text):
                    if '*' in text:
                        log.write(f"[yellow]{text}[/yellow]")
                    else:
                        log.write(f"[green]{text}[/green]")
                else:
                    log.write(f"[cyan]{text}[/cyan]")

            await self._current_proc.wait()
            status.update("[green]Traceroute complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Traceroute failed[/red]")
        finally:
            self._current_proc = None


class SpeedModule(Container):
    """Network speed test module."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[cyan]Speed Test[/cyan]", classes="title"),
            Static("Tests download speed and latency to multiple servers.", classes="muted"),
            Horizontal(
                Button("Speed Test", id="btn-speed", variant="primary"),
                Button("Latency Test", id="btn-latency"),
                classes="form-row",
            ),
            ProgressBar(id="speed-progress", total=100, show_eta=False),
            Static("", id="speed-status", classes="status-text"),
            RichLog(id="speed-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-speed")
    def run_speed(self) -> None:
        self.do_speed_test()

    @on(Button.Pressed, "#btn-latency")
    def run_latency(self) -> None:
        self.do_latency_test()

    @work(exclusive=True)
    async def do_speed_test(self) -> None:
        log = self.query_one("#speed-results", RichLog)
        status = self.query_one("#speed-status", Static)
        progress = self.query_one("#speed-progress", ProgressBar)

        log.clear()
        status.update("[cyan]Starting speed test...[/cyan]")
        progress.progress = 0

        try:
            log.write("[cyan]Testing download speed...[/cyan]")
            progress.progress = 10

            test_url = "http://speedtest.tele2.net/1MB.zip"

            proc = await asyncio.create_subprocess_exec(
                "curl", "-o", "/dev/null", "-w", "%{speed_download}", "-s", test_url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            progress.progress = 50

            if stdout:
                speed_bps = float(stdout.decode().strip())
                speed_mbps = (speed_bps * 8) / 1_000_000
                log.write(f"[green]Download: {speed_mbps:.2f} Mbps[/green]")

            log.write("\n[cyan]Testing latency...[/cyan]")
            progress.progress = 70

            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "5", "-q", "8.8.8.8",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+)', stdout.decode())
                if match:
                    min_rtt, avg_rtt, max_rtt, mdev = match.groups()
                    log.write(f"[green]Latency: {avg_rtt} ms (min: {min_rtt}, max: {max_rtt})[/green]")

            progress.progress = 100
            status.update("[green]Speed test complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Speed test failed[/red]")

    @work(exclusive=True)
    async def do_latency_test(self) -> None:
        log = self.query_one("#speed-results", RichLog)
        status = self.query_one("#speed-status", Static)

        log.clear()
        status.update("[cyan]Testing latency to multiple servers...[/cyan]")

        servers = [
            ("Google DNS", "8.8.8.8"),
            ("Cloudflare", "1.1.1.1"),
            ("OpenDNS", "208.67.222.222"),
            ("Quad9", "9.9.9.9"),
        ]

        log.write("[cyan]Latency to DNS Servers:[/cyan]\n")

        for name, ip in servers:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "ping", "-c", "3", "-q", ip,
                    stdout=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()

                if stdout:
                    match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)', stdout.decode())
                    if match:
                        min_rtt, avg_rtt, max_rtt = match.groups()
                        avg = float(avg_rtt)
                        if avg < 30:
                            color = "green"
                        elif avg < 100:
                            color = "yellow"
                        else:
                            color = "red"
                        log.write(f"[{color}]{name:<15} ({ip:<15}): {avg_rtt} ms[/{color}]")
                    else:
                        log.write(f"[red]{name:<15} ({ip:<15}): timeout[/red]")

            except Exception as e:
                log.write(f"[red]{name}: error - {e}[/red]")

        status.update("[green]Latency test complete[/green]")


class MonitorModule(Container):
    """Network traffic monitor with VPN status."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Button("Connections", id="btn-connections", variant="primary"),
                Button("Traffic Stats", id="btn-traffic"),
                Button("Ports", id="btn-ports"),
                Button("VPN Status", id="btn-vpn"),
                classes="form-row",
            ),
            Static("", id="monitor-status", classes="status-text"),
            RichLog(id="monitor-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-connections")
    def show_connections(self) -> None:
        self.get_connections()

    @on(Button.Pressed, "#btn-traffic")
    def show_traffic(self) -> None:
        self.get_traffic()

    @on(Button.Pressed, "#btn-ports")
    def show_ports(self) -> None:
        self.get_ports()

    @on(Button.Pressed, "#btn-vpn")
    def show_vpn(self) -> None:
        self.get_vpn_status()

    @work(exclusive=True)
    async def get_connections(self) -> None:
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Getting active connections...[/cyan]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ss", "-tunapo",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                lines = stdout.decode().strip().split('\n')
                for i, line in enumerate(lines):
                    if i == 0:
                        log.write(f"[cyan]{line}[/cyan]")
                    elif "ESTAB" in line:
                        log.write(f"[green]{line}[/green]")
                    elif "LISTEN" in line:
                        log.write(f"[yellow]{line}[/yellow]")
                    elif "TIME-WAIT" in line or "CLOSE" in line:
                        log.write(f"[gray]{line}[/gray]")
                    else:
                        log.write(line)

            status.update("[green]Connections retrieved[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def get_traffic(self) -> None:
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Getting traffic statistics...[/cyan]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "cat", "/proc/net/dev",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                log.write("[cyan]Interface Statistics:[/cyan]\n")
                log.write(f"{'Interface':<12} {'RX Bytes':<15} {'RX Packets':<12} {'TX Bytes':<15} {'TX Packets':<12}")
                log.write("-" * 70)

                for line in stdout.decode().strip().split('\n')[2:]:
                    parts = line.split()
                    if len(parts) >= 10:
                        iface = parts[0].rstrip(':')
                        rx_bytes = int(parts[1])
                        rx_packets = int(parts[2])
                        tx_bytes = int(parts[9])
                        tx_packets = int(parts[10])

                        def fmt_bytes(b):
                            if b > 1_000_000_000:
                                return f"{b/1_000_000_000:.1f} GB"
                            elif b > 1_000_000:
                                return f"{b/1_000_000:.1f} MB"
                            elif b > 1_000:
                                return f"{b/1_000:.1f} KB"
                            return f"{b} B"

                        if rx_bytes > 0 or tx_bytes > 0:
                            log.write(f"[green]{iface:<12} {fmt_bytes(rx_bytes):<15} {rx_packets:<12} {fmt_bytes(tx_bytes):<15} {tx_packets:<12}[/green]")

            status.update("[green]Traffic stats retrieved[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def get_ports(self) -> None:
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Getting listening ports...[/cyan]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ss", "-tlnp",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                log.write("[cyan]Listening TCP Ports:[/cyan]\n")
                for i, line in enumerate(stdout.decode().strip().split('\n')):
                    if i == 0:
                        log.write(f"[cyan]{line}[/cyan]")
                    else:
                        log.write(f"[green]{line}[/green]")

            proc = await asyncio.create_subprocess_exec(
                "ss", "-ulnp",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                log.write("\n[cyan]Listening UDP Ports:[/cyan]\n")
                for i, line in enumerate(stdout.decode().strip().split('\n')):
                    if i == 0:
                        log.write(f"[cyan]{line}[/cyan]")
                    else:
                        log.write(f"[yellow]{line}[/yellow]")

            status.update("[green]Ports retrieved[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def get_vpn_status(self) -> None:
        """Check VPN and Tailscale status."""
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Checking VPN status...[/cyan]")

        try:
            # Check Tailscale
            log.write("[bold cyan]Tailscale Status[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "tailscale", "status", "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0 and stdout:
                try:
                    ts_status = json.loads(stdout.decode())
                    if ts_status.get("BackendState") == "Running":
                        log.write(f"[green]Status: Connected[/green]")
                        if ts_status.get("Self"):
                            self_info = ts_status["Self"]
                            log.write(f"[green]Hostname: {self_info.get('HostName', 'N/A')}[/green]")
                            log.write(f"[green]IP: {', '.join(self_info.get('TailscaleIPs', []))}[/green]")

                        # Show peers
                        peers = ts_status.get("Peer", {})
                        if peers:
                            log.write(f"\n[cyan]Connected Peers ({len(peers)}):[/cyan]")
                            for peer_id, peer in list(peers.items())[:5]:
                                name = peer.get("HostName", "Unknown")
                                ips = ", ".join(peer.get("TailscaleIPs", []))
                                online = "[green]online[/green]" if peer.get("Online") else "[red]offline[/red]"
                                log.write(f"  {name}: {ips} ({online})")
                            if len(peers) > 5:
                                log.write(f"  [gray]... and {len(peers) - 5} more[/gray]")
                    else:
                        log.write(f"[yellow]Status: {ts_status.get('BackendState', 'Unknown')}[/yellow]")
                except json.JSONDecodeError:
                    log.write("[yellow]Tailscale: Unable to parse status[/yellow]")
            else:
                log.write("[yellow]Tailscale: Not installed or not running[/yellow]")

            # Check other VPN interfaces
            log.write("\n[bold cyan]VPN Interfaces[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "ip", "link", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            vpn_found = False
            if stdout:
                for line in stdout.decode().split('\n'):
                    if any(vpn in line.lower() for vpn in ['tun', 'tap', 'wg', 'tailscale']):
                        vpn_found = True
                        match = re.search(r'\d+:\s+(\S+):', line)
                        if match:
                            iface = match.group(1)
                            state = "UP" if "UP" in line else "DOWN"
                            color = "green" if state == "UP" else "red"
                            log.write(f"[{color}]{iface}: {state}[/{color}]")

            if not vpn_found:
                log.write("[gray]No VPN interfaces detected[/gray]")

            status.update("[green]VPN status retrieved[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")


class ToolsModule(Container):
    """Utility tools: Subnet calc, WoL, mDNS browser, hosts editor."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._mdns_services = []

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Input:", classes="form-label"),
                Input(placeholder="CIDR, MAC, or hostname", id="tools-input"),
                classes="form-row",
            ),
            Horizontal(
                Button("Subnet Calc", id="btn-subnet", variant="primary"),
                Button("Wake-on-LAN", id="btn-wol"),
                Button("mDNS Browse", id="btn-mdns"),
                Button("View Hosts", id="btn-hosts"),
                classes="form-row",
            ),
            Static("", id="tools-status", classes="status-text"),
            RichLog(id="tools-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-subnet")
    def do_subnet(self) -> None:
        cidr = self.query_one("#tools-input", Input).value.strip()
        if not cidr:
            cidr = get_network_cidr()
            self.query_one("#tools-input", Input).value = cidr
        self.calc_subnet(cidr)

    @on(Button.Pressed, "#btn-wol")
    def do_wol(self) -> None:
        mac = self.query_one("#tools-input", Input).value.strip()
        if not mac:
            self.query_one("#tools-status", Static).update("[red]Enter a MAC address[/red]")
            return
        self.send_wol(mac)

    @on(Button.Pressed, "#btn-mdns")
    def do_mdns(self) -> None:
        self.browse_mdns()

    @on(Button.Pressed, "#btn-hosts")
    def do_hosts(self) -> None:
        self.view_hosts()

    def calc_subnet(self, cidr: str) -> None:
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        result = calculate_subnet(cidr)

        if "error" in result:
            log.write(f"[red]Error: {result['error']}[/red]")
            status.update("[red]Invalid CIDR[/red]")
            return

        log.write(f"[bold cyan]Subnet Calculator: {cidr}[/bold cyan]\n")
        log.write(f"[green]Network Address:[/green]  {result['network']}")
        log.write(f"[green]Netmask:[/green]          {result['netmask']}")
        log.write(f"[green]Wildcard:[/green]         {result['wildcard']}")
        log.write(f"[green]Broadcast:[/green]        {result['broadcast']}")
        log.write(f"[green]First Host:[/green]       {result['first_host']}")
        log.write(f"[green]Last Host:[/green]        {result['last_host']}")
        log.write(f"[green]Usable Hosts:[/green]     {result['num_hosts']}")
        log.write(f"[green]Prefix Length:[/green]    /{result['prefix_len']}")

        status.update("[green]Calculation complete[/green]")

    @work(exclusive=True)
    async def send_wol(self, mac: str) -> None:
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update(f"[cyan]Sending Wake-on-LAN to {mac}...[/cyan]")

        try:
            packet = create_wol_packet(mac)

            # Send to broadcast
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(packet, ("255.255.255.255", 9))
            sock.close()

            log.write(f"[bold cyan]Wake-on-LAN[/bold cyan]\n")
            log.write(f"[green]Magic packet sent to {mac}[/green]")
            log.write(f"[gray]Broadcast: 255.255.255.255:9[/gray]")
            log.write(f"[gray]Packet size: {len(packet)} bytes[/gray]")

            vendor = lookup_mac_vendor(mac)
            log.write(f"[gray]Vendor: {vendor}[/gray]")

            status.update("[green]WoL packet sent[/green]")

            if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                play_beep(1000, 100)

        except ValueError as e:
            log.write(f"[red]Invalid MAC address: {e}[/red]")
            status.update("[red]Invalid MAC[/red]")
        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]WoL failed[/red]")

    @work(exclusive=True)
    async def browse_mdns(self) -> None:
        """Browse for mDNS/Bonjour services."""
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update("[cyan]Browsing mDNS services (5 seconds)...[/cyan]")

        if not HAS_ZEROCONF:
            log.write("[red]zeroconf library not installed[/red]")
            log.write("[gray]Install with: pip3 install zeroconf[/gray]")
            status.update("[red]Missing dependency[/red]")
            return

        try:
            log.write("[bold cyan]mDNS/Bonjour Services[/bold cyan]\n")

            services_found = []

            class MyListener(ServiceListener):
                def add_service(self, zc, type_, name):
                    services_found.append((type_, name))

                def remove_service(self, zc, type_, name):
                    pass

                def update_service(self, zc, type_, name):
                    pass

            zeroconf = Zeroconf()
            listener = MyListener()

            # Common service types
            service_types = [
                "_http._tcp.local.",
                "_https._tcp.local.",
                "_ssh._tcp.local.",
                "_sftp-ssh._tcp.local.",
                "_smb._tcp.local.",
                "_afpovertcp._tcp.local.",
                "_printer._tcp.local.",
                "_ipp._tcp.local.",
                "_airplay._tcp.local.",
                "_raop._tcp.local.",
                "_googlecast._tcp.local.",
                "_spotify-connect._tcp.local.",
                "_homekit._tcp.local.",
            ]

            browsers = []
            for stype in service_types:
                try:
                    browser = ServiceBrowser(zeroconf, stype, listener)
                    browsers.append(browser)
                except Exception:
                    pass

            # Wait for discovery
            await asyncio.sleep(5)

            # Close browsers
            for browser in browsers:
                browser.cancel()
            zeroconf.close()

            if services_found:
                # Group by type
                by_type = {}
                for stype, name in services_found:
                    stype_short = stype.replace("._tcp.local.", "").replace("_", "")
                    if stype_short not in by_type:
                        by_type[stype_short] = []
                    by_type[stype_short].append(name.replace(f".{stype}", ""))

                for stype, names in sorted(by_type.items()):
                    log.write(f"[cyan]{stype}:[/cyan]")
                    for name in names:
                        log.write(f"  [green]{name}[/green]")
            else:
                log.write("[yellow]No services found[/yellow]")

            status.update(f"[green]Found {len(services_found)} services[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]mDNS browse failed[/red]")

    @work(exclusive=True)
    async def view_hosts(self) -> None:
        """View /etc/hosts file."""
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update("[cyan]Reading hosts file...[/cyan]")

        try:
            log.write("[bold cyan]/etc/hosts[/bold cyan]\n")

            with open("/etc/hosts", "r") as f:
                for line in f:
                    line = line.rstrip()
                    if line.startswith("#"):
                        log.write(f"[gray]{line}[/gray]")
                    elif line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            ip = parts[0]
                            hosts = " ".join(parts[1:])
                            log.write(f"[green]{ip:<20}[/green] {hosts}")
                        else:
                            log.write(line)

            log.write("\n[gray]Edit with: sudo nano /etc/hosts[/gray]")
            status.update("[green]Hosts file loaded[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed to read hosts[/red]")


class GeoModule(Container):
    """IP Geolocation module."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("IP Address:", classes="form-label"),
                Input(placeholder="IP to lookup (blank for your IP)", id="geo-input"),
                classes="form-row",
            ),
            Horizontal(
                Button("Lookup", id="btn-geo", variant="primary"),
                Button("My IP", id="btn-myip"),
                Button("Clear", id="btn-geo-clear", variant="error"),
                classes="form-row",
            ),
            Static("", id="geo-status", classes="status-text"),
            RichLog(id="geo-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-geo")
    def do_geo(self) -> None:
        ip = self.query_one("#geo-input", Input).value.strip()
        self.lookup_geo(ip)

    @on(Button.Pressed, "#btn-myip")
    def do_myip(self) -> None:
        self.query_one("#geo-input", Input).value = ""
        self.lookup_geo("")

    @on(Button.Pressed, "#btn-geo-clear")
    def clear_results(self) -> None:
        self.query_one("#geo-results", RichLog).clear()
        self.query_one("#geo-status", Static).update("")

    @work(exclusive=True)
    async def lookup_geo(self, ip: str) -> None:
        """Look up IP geolocation."""
        log = self.query_one("#geo-results", RichLog)
        status = self.query_one("#geo-status", Static)

        log.clear()

        if not HAS_REQUESTS:
            log.write("[red]requests library not installed[/red]")
            status.update("[red]Missing dependency[/red]")
            return

        target = ip if ip else "your IP"
        status.update(f"[cyan]Looking up {target}...[/cyan]")

        try:
            # Use ip-api.com (free, no key required)
            url = f"http://ip-api.com/json/{ip}" if ip else "http://ip-api.com/json/"

            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.get(url, timeout=10)
            )
            data = response.json()

            if data.get("status") == "success":
                log.write(f"[bold cyan]IP Geolocation[/bold cyan]\n")
                log.write(f"[green]IP Address:[/green]    {data.get('query', 'N/A')}")
                log.write(f"[green]Country:[/green]       {data.get('country', 'N/A')} ({data.get('countryCode', '')})")
                log.write(f"[green]Region:[/green]        {data.get('regionName', 'N/A')} ({data.get('region', '')})")
                log.write(f"[green]City:[/green]          {data.get('city', 'N/A')}")
                log.write(f"[green]ZIP Code:[/green]      {data.get('zip', 'N/A')}")
                log.write(f"[green]Coordinates:[/green]   {data.get('lat', 'N/A')}, {data.get('lon', 'N/A')}")
                log.write(f"[green]Timezone:[/green]      {data.get('timezone', 'N/A')}")
                log.write(f"[green]ISP:[/green]           {data.get('isp', 'N/A')}")
                log.write(f"[green]Organization:[/green]  {data.get('org', 'N/A')}")
                log.write(f"[green]AS:[/green]            {data.get('as', 'N/A')}")

                # Check for special IP types
                if data.get('mobile'):
                    log.write(f"[yellow]Mobile Network: Yes[/yellow]")
                if data.get('proxy'):
                    log.write(f"[yellow]Proxy/VPN: Yes[/yellow]")
                if data.get('hosting'):
                    log.write(f"[yellow]Hosting/Datacenter: Yes[/yellow]")

                status.update("[green]Lookup complete[/green]")
            else:
                log.write(f"[red]Lookup failed: {data.get('message', 'Unknown error')}[/red]")
                status.update("[red]Lookup failed[/red]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Lookup failed[/red]")


class NetRunner(App):
    """NetRunner v2.0 - Cyberpunk Network Toolkit."""

    TITLE = "NETRUNNER"
    CSS_PATH = "netrunner.tcss"

    BINDINGS = [
        Binding("1", "tab_scanner", "Scanner", show=True),
        Binding("2", "tab_dns", "DNS", show=True),
        Binding("3", "tab_wifi", "WiFi", show=True),
        Binding("4", "tab_ping", "Ping", show=True),
        Binding("5", "tab_speed", "Speed", show=True),
        Binding("6", "tab_monitor", "Monitor", show=True),
        Binding("7", "tab_tools", "Tools", show=True),
        Binding("8", "tab_geo", "Geo", show=True),
        Binding("question_mark", "help", "Help", show=True),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("s", "save_text", "Save", show=False),
        Binding("j", "save_json", "JSON", show=False),
        Binding("m", "toggle_sound", "Sound", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.sound_enabled = False
        self._results_data = {}

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent(id="tabs"):
            with TabPane("Scanner", id="tab-scanner"):
                yield ScannerModule()
            with TabPane("DNS/SSL", id="tab-dns"):
                yield DNSModule()
            with TabPane("WiFi", id="tab-wifi"):
                yield WiFiModule()
            with TabPane("Ping", id="tab-ping"):
                yield PingModule()
            with TabPane("Speed", id="tab-speed"):
                yield SpeedModule()
            with TabPane("Monitor", id="tab-monitor"):
                yield MonitorModule()
            with TabPane("Tools", id="tab-tools"):
                yield ToolsModule()
            with TabPane("Geo", id="tab-geo"):
                yield GeoModule()
        yield Footer()

    def on_mount(self) -> None:
        """Set up the app on mount."""
        self.title = f"NETRUNNER v2.0 | {get_local_ip()}"
        # Show a random hacker quote
        self.notify(random.choice(HACKER_QUOTES), timeout=3)

    def action_tab_scanner(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-scanner"

    def action_tab_dns(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-dns"

    def action_tab_wifi(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-wifi"

    def action_tab_ping(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-ping"

    def action_tab_speed(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-speed"

    def action_tab_monitor(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-monitor"

    def action_tab_tools(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-tools"

    def action_tab_geo(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-geo"

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        self.title = f"NETRUNNER v2.0 | {get_local_ip()}"
        self.notify(random.choice(HACKER_QUOTES), timeout=2)

    def action_toggle_sound(self) -> None:
        self.sound_enabled = not self.sound_enabled
        state = "enabled" if self.sound_enabled else "disabled"
        self.notify(f"Sound effects {state}", timeout=2)
        if self.sound_enabled:
            play_beep(1000, 50)

    def action_save_text(self) -> None:
        """Save current results to text file."""
        self._save_results("txt")

    def action_save_json(self) -> None:
        """Save current results to JSON file."""
        self._save_results("json")

    def _save_results(self, format: str) -> None:
        """Save results in specified format."""
        tabs = self.query_one("#tabs", TabbedContent)
        active_tab = tabs.active

        result_map = {
            "tab-scanner": "#scan-results",
            "tab-dns": "#dns-results",
            "tab-wifi": "#wifi-results",
            "tab-ping": "#ping-results",
            "tab-speed": "#speed-results",
            "tab-monitor": "#monitor-results",
            "tab-tools": "#tools-results",
            "tab-geo": "#geo-results",
        }

        if active_tab in result_map:
            try:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                module_name = active_tab.replace("tab-", "")

                if format == "json":
                    filename = RESULTS_DIR / f"{module_name}_{timestamp}.json"
                    data = {
                        "module": module_name,
                        "timestamp": datetime.now().isoformat(),
                        "local_ip": get_local_ip(),
                        "results": f"Results from {module_name} module",
                    }
                    with open(filename, "w") as f:
                        json.dump(data, f, indent=2)
                else:
                    filename = RESULTS_DIR / f"{module_name}_{timestamp}.txt"
                    with open(filename, "w") as f:
                        f.write(f"NetRunner v2.0 Results\n")
                        f.write(f"Module: {module_name.upper()}\n")
                        f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                        f.write(f"Local IP: {get_local_ip()}\n")
                        f.write("=" * 60 + "\n\n")
                        f.write("Results saved from NetRunner session.\n")

                self.notify(f"Saved to {filename.name}", timeout=3)

            except Exception as e:
                self.notify(f"Save failed: {e}", severity="error", timeout=3)


if __name__ == "__main__":
    app = NetRunner()
    app.run()
