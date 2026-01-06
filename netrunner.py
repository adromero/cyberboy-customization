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
                                            v3.0
[/bold cyan]""", classes="ascii-title"),
            Static("\n[bold magenta]KEYBINDINGS[/bold magenta]", classes="help-title"),
            Static("""
[yellow]1-0,-,=[/yellow] Switch between 12 modules
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
[yellow]1[/yellow] Scanner   - Network/port/ARP/vuln scanning
[yellow]2[/yellow] DNS       - DNS lookups, WHOIS, SSL/TLS
[yellow]3[/yellow] WiFi      - Wireless analysis, bandwidth
[yellow]4[/yellow] Ping      - Ping & traceroute tools
[yellow]5[/yellow] Speed     - Download/upload speed tests
[yellow]6[/yellow] Monitor   - Traffic, connections, VPN
[yellow]7[/yellow] Tools     - Subnet, WoL, mDNS, ARP table
[yellow]8[/yellow] Geo       - IP geolocation lookup
[yellow]9[/yellow] HTTP      - Headers, methods, redirects
[yellow]0[/yellow] Security  - Headers check, email sec, banners
[yellow]-[/yellow] Bluetooth - Device scan, paired, controller
[yellow]=[/yellow] Packets   - Live packet capture (tcpdump)

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
                    ("TCP Port Scan (Top 100)", "ports"),
                    ("TCP Port Scan (Full)", "full"),
                    ("UDP Port Scan (Top 20)", "udp"),
                    ("Service Detection", "services"),
                    ("OS Detection (sudo)", "os"),
                    ("Vuln Scan (sudo)", "vuln"),
                    ("Aggressive (sudo)", "aggressive"),
                ], id="scan-type", value="ping"),
                classes="form-row",
            ),
            Horizontal(
                Label("Ports:", classes="form-label"),
                Input(placeholder="Custom ports: 22,80,443 or 1-1000", id="scan-ports"),
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
        custom_ports = self.query_one("#scan-ports", Input).value.strip()
        if scan_type == "arp":
            self.run_arp_scan(target)
        else:
            self.run_scan(target, scan_type, custom_ports)

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
    async def run_scan(self, target: str, scan_type: str, custom_ports: str = "") -> None:
        log = self.query_one("#scan-results", RichLog)
        status = self.query_one("#scan-status", Static)

        cmd = ["nmap"]
        port_arg = f"-p {custom_ports}" if custom_ports else ""

        if scan_type == "ping":
            cmd.extend(["-sn", target])
            status.update("[cyan]Running ping scan...[/cyan]")
        elif scan_type == "ports":
            if custom_ports:
                cmd.extend(["-sT", "-p", custom_ports, target])
                status.update(f"[cyan]Scanning ports {custom_ports}...[/cyan]")
            else:
                cmd.extend(["-sT", "--top-ports", "100", target])
                status.update("[cyan]Scanning top 100 TCP ports...[/cyan]")
        elif scan_type == "full":
            cmd.extend(["-sT", "-p-", target])
            status.update("[cyan]Full TCP port scan (65535 ports)...[/cyan]")
        elif scan_type == "udp":
            if custom_ports:
                cmd = ["sudo", "nmap", "-sU", "-p", custom_ports, target]
            else:
                cmd = ["sudo", "nmap", "-sU", "--top-ports", "20", target]
            status.update("[cyan]UDP port scan (sudo required)...[/cyan]")
        elif scan_type == "services":
            if custom_ports:
                cmd.extend(["-sV", "-p", custom_ports, target])
            else:
                cmd.extend(["-sV", "--top-ports", "100", target])
            status.update("[cyan]Detecting services...[/cyan]")
        elif scan_type == "os":
            cmd = ["sudo", "nmap", "-O", target]
            status.update("[cyan]OS detection (sudo)...[/cyan]")
        elif scan_type == "vuln":
            if custom_ports:
                cmd = ["sudo", "nmap", "--script=vuln", "-p", custom_ports, target]
            else:
                cmd = ["sudo", "nmap", "--script=vuln", "--top-ports", "100", target]
            status.update("[cyan]Vulnerability scan (sudo)...[/cyan]")
        elif scan_type == "aggressive":
            if custom_ports:
                cmd = ["sudo", "nmap", "-A", "-p", custom_ports, target]
            else:
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
            Horizontal(
                Button("Channel Analysis", id="btn-wifi-channels"),
                Button("Signal Strength", id="btn-wifi-signal"),
                Button("Hidden Networks", id="btn-wifi-hidden"),
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

    @on(Button.Pressed, "#btn-wifi-channels")
    def analyze_channels(self) -> None:
        self._monitoring = False
        self.run_channel_analysis()

    @on(Button.Pressed, "#btn-wifi-signal")
    def show_signal(self) -> None:
        self._monitoring = False
        self.run_signal_monitor()

    @on(Button.Pressed, "#btn-wifi-hidden")
    def scan_hidden(self) -> None:
        self._monitoring = False
        self.run_hidden_scan()

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

    @work(exclusive=True)
    async def run_channel_analysis(self) -> None:
        """Analyze WiFi channel usage."""
        log = self.query_one("#wifi-results", RichLog)
        status = self.query_one("#wifi-status", Static)

        log.clear()
        status.update("[cyan]Analyzing WiFi channels...[/cyan]")
        log.write("[bold cyan]WiFi Channel Analysis[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "SSID,CHAN,SIGNAL,FREQ", "device", "wifi", "list",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                # Aggregate by channel
                channels_2g = {}  # 1-14
                channels_5g = {}  # 36+

                for line in stdout.decode().strip().split('\n'):
                    if line:
                        parts = line.split(':')
                        if len(parts) >= 4:
                            ssid = parts[0] or "[Hidden]"
                            chan = parts[1]
                            signal = int(parts[2]) if parts[2].isdigit() else 0
                            freq = parts[3]

                            if chan.isdigit():
                                chan_num = int(chan)
                                if chan_num <= 14:
                                    if chan_num not in channels_2g:
                                        channels_2g[chan_num] = []
                                    channels_2g[chan_num].append((ssid, signal))
                                else:
                                    if chan_num not in channels_5g:
                                        channels_5g[chan_num] = []
                                    channels_5g[chan_num].append((ssid, signal))

                # Display 2.4 GHz channels
                log.write("[bold cyan]2.4 GHz Band:[/bold cyan]")
                log.write(f"{'Ch':<4} {'Networks':<10} {'Congestion':<15} {'Top SSID'}")
                log.write("-" * 55)

                for ch in range(1, 15):
                    networks = channels_2g.get(ch, [])
                    count = len(networks)
                    if count == 0:
                        bar = "[green]░░░░░░░░░░[/green]"
                        congestion = "Clear"
                    elif count <= 2:
                        bar = "[yellow]▓▓░░░░░░░░[/yellow]"
                        congestion = "Low"
                    elif count <= 4:
                        bar = "[yellow]▓▓▓▓░░░░░░[/yellow]"
                        congestion = "Medium"
                    else:
                        bar = "[red]▓▓▓▓▓▓▓▓░░[/red]"
                        congestion = "High"

                    top_ssid = networks[0][0][:15] if networks else ""
                    log.write(f"{ch:<4} {count:<10} {bar} {top_ssid}")

                # Display 5 GHz channels
                if channels_5g:
                    log.write("\n[bold cyan]5 GHz Band:[/bold cyan]")
                    log.write(f"{'Ch':<4} {'Networks':<10} {'Top Signal':<12} {'SSID'}")
                    log.write("-" * 50)

                    for ch in sorted(channels_5g.keys()):
                        networks = channels_5g[ch]
                        count = len(networks)
                        top_signal = max(n[1] for n in networks)
                        top_ssid = networks[0][0][:20]

                        if top_signal >= 70:
                            color = "green"
                        elif top_signal >= 40:
                            color = "yellow"
                        else:
                            color = "red"

                        log.write(f"[{color}]{ch:<4} {count:<10} {top_signal}%         {top_ssid}[/{color}]")

                # Recommendation
                log.write("\n[bold cyan]Recommendation:[/bold cyan]")
                # Find least congested channels
                best_2g = min(range(1, 14), key=lambda c: len(channels_2g.get(c, [])))
                log.write(f"[green]Best 2.4 GHz channel: {best_2g}[/green]")

            status.update("[green]Channel analysis complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Analysis failed[/red]")

    @work(exclusive=True)
    async def run_signal_monitor(self) -> None:
        """Monitor current WiFi signal strength."""
        log = self.query_one("#wifi-results", RichLog)
        status = self.query_one("#wifi-status", Static)
        spark = self.query_one("#bandwidth-spark", Sparkline)

        log.clear()
        status.update("[cyan]Monitoring signal strength...[/cyan]")
        log.write("[bold cyan]WiFi Signal Strength Monitor[/bold cyan]\n")

        try:
            # Get current connection
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "ACTIVE,SSID,SIGNAL,CHAN,FREQ", "device", "wifi", "list",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            current_ssid = None
            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if line.startswith("yes:"):
                        parts = line.split(':')
                        if len(parts) >= 5:
                            current_ssid = parts[1]
                            signal = parts[2]
                            chan = parts[3]
                            freq = parts[4]
                            log.write(f"[green]Connected to: {current_ssid}[/green]")
                            log.write(f"[cyan]Channel: {chan} ({freq})[/cyan]")
                            log.write(f"[cyan]Signal: {signal}%[/cyan]\n")
                            break

            if not current_ssid:
                log.write("[yellow]Not connected to WiFi[/yellow]")
                status.update("[yellow]No WiFi connection[/yellow]")
                return

            # Monitor signal over time
            log.write("[cyan]Signal history (10 samples):[/cyan]")
            signal_data = []

            for i in range(10):
                proc = await asyncio.create_subprocess_exec(
                    "nmcli", "-t", "-f", "ACTIVE,SIGNAL", "device", "wifi", "list",
                    stdout=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()

                if stdout:
                    for line in stdout.decode().strip().split('\n'):
                        if line.startswith("yes:"):
                            sig = int(line.split(':')[1])
                            signal_data.append(sig)
                            spark.data = signal_data

                            if sig >= 70:
                                color = "green"
                                quality = "Excellent"
                            elif sig >= 50:
                                color = "yellow"
                                quality = "Good"
                            elif sig >= 30:
                                color = "yellow"
                                quality = "Fair"
                            else:
                                color = "red"
                                quality = "Poor"

                            log.write(f"[{color}]Sample {i+1}: {sig}% ({quality})[/{color}]")
                            break

                await asyncio.sleep(1)

            # Summary
            if signal_data:
                avg_signal = sum(signal_data) / len(signal_data)
                min_signal = min(signal_data)
                max_signal = max(signal_data)
                log.write(f"\n[bold cyan]Summary:[/bold cyan]")
                log.write(f"  Average: {avg_signal:.0f}%")
                log.write(f"  Min: {min_signal}%, Max: {max_signal}%")
                log.write(f"  Variance: {max_signal - min_signal}%")

            status.update("[green]Signal monitoring complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Monitoring failed[/red]")

    @work(exclusive=True)
    async def run_hidden_scan(self) -> None:
        """Scan for hidden WiFi networks."""
        log = self.query_one("#wifi-results", RichLog)
        status = self.query_one("#wifi-status", Static)

        log.clear()
        status.update("[cyan]Scanning for hidden networks...[/cyan]")
        log.write("[bold cyan]Hidden Network Detection[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "SSID,BSSID,SIGNAL,CHAN,SECURITY", "device", "wifi", "list",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            hidden_count = 0
            visible_count = 0

            if stdout:
                log.write("[cyan]Detected Networks:[/cyan]\n")
                log.write(f"{'SSID':<25} {'BSSID':<20} {'Signal':<8} {'Ch':<5} {'Security'}")
                log.write("-" * 75)

                for line in stdout.decode().strip().split('\n'):
                    if line:
                        parts = line.split(':')
                        if len(parts) >= 5:
                            ssid = parts[0]
                            bssid = parts[1]
                            signal = parts[2]
                            chan = parts[3]
                            security = parts[4]

                            if not ssid or ssid == "--":
                                hidden_count += 1
                                ssid_display = "[Hidden Network]"
                                vendor = lookup_mac_vendor(bssid)
                                log.write(f"[red]{ssid_display:<25} {bssid:<20} {signal:>5}%  {chan:<5} {security}[/red]")
                                log.write(f"[gray]  └─ Vendor: {vendor}[/gray]")
                            else:
                                visible_count += 1
                                log.write(f"[green]{ssid:<25} {bssid:<20} {signal:>5}%  {chan:<5} {security}[/green]")

                log.write(f"\n[bold cyan]Summary:[/bold cyan]")
                log.write(f"  Visible networks: [green]{visible_count}[/green]")
                log.write(f"  Hidden networks:  [red]{hidden_count}[/red]")

                if hidden_count > 0:
                    log.write("\n[yellow]Note: Hidden networks broadcast their BSSID[/yellow]")
                    log.write("[yellow]but not their SSID. MAC vendor lookup can[/yellow]")
                    log.write("[yellow]help identify the device manufacturer.[/yellow]")

            status.update("[green]Hidden network scan complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Scan failed[/red]")


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
            Horizontal(
                Label("Server:", classes="form-label"),
                Select([
                    ("Auto (Tele2)", "tele2"),
                    ("Cloudflare", "cloudflare"),
                    ("Hetzner (EU)", "hetzner"),
                    ("OVH (EU)", "ovh"),
                ], id="speed-server", value="tele2"),
                classes="form-row",
            ),
            Horizontal(
                Button("Download", id="btn-speed", variant="primary"),
                Button("Upload", id="btn-upload"),
                Button("Full Test", id="btn-full-speed"),
                Button("Latency", id="btn-latency"),
                classes="form-row",
            ),
            ProgressBar(id="speed-progress", total=100, show_eta=False),
            Static("", id="speed-status", classes="status-text"),
            RichLog(id="speed-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-speed")
    def run_speed(self) -> None:
        server = self.query_one("#speed-server", Select).value
        self.do_speed_test(server)

    @on(Button.Pressed, "#btn-upload")
    def run_upload(self) -> None:
        server = self.query_one("#speed-server", Select).value
        self.do_upload_test(server)

    @on(Button.Pressed, "#btn-full-speed")
    def run_full(self) -> None:
        server = self.query_one("#speed-server", Select).value
        self.do_full_test(server)

    @on(Button.Pressed, "#btn-latency")
    def run_latency(self) -> None:
        self.do_latency_test()

    def _get_server_urls(self, server: str) -> dict:
        """Get download/upload URLs for selected server."""
        servers = {
            "tele2": {
                "download": "http://speedtest.tele2.net/10MB.zip",
                "upload": "http://speedtest.tele2.net/upload.php",
                "name": "Tele2 Speedtest",
            },
            "cloudflare": {
                "download": "https://speed.cloudflare.com/__down?bytes=10000000",
                "upload": "https://speed.cloudflare.com/__up",
                "name": "Cloudflare",
            },
            "hetzner": {
                "download": "https://speed.hetzner.de/10MB.bin",
                "upload": None,
                "name": "Hetzner (Germany)",
            },
            "ovh": {
                "download": "http://proof.ovh.net/files/10Mb.dat",
                "upload": None,
                "name": "OVH (France)",
            },
        }
        return servers.get(server, servers["tele2"])

    @work(exclusive=True)
    async def do_speed_test(self, server: str = "tele2") -> None:
        log = self.query_one("#speed-results", RichLog)
        status = self.query_one("#speed-status", Static)
        progress = self.query_one("#speed-progress", ProgressBar)

        log.clear()
        server_info = self._get_server_urls(server)
        status.update(f"[cyan]Testing download from {server_info['name']}...[/cyan]")
        progress.progress = 0

        try:
            log.write(f"[bold cyan]Download Speed Test[/bold cyan]")
            log.write(f"[cyan]Server: {server_info['name']}[/cyan]\n")
            progress.progress = 10

            proc = await asyncio.create_subprocess_exec(
                "curl", "-o", "/dev/null", "-w", "%{speed_download}|%{time_total}|%{size_download}",
                "-s", "--max-time", "30", server_info["download"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            progress.progress = 80

            if stdout:
                parts = stdout.decode().strip().split("|")
                if len(parts) >= 3:
                    speed_bps = float(parts[0])
                    time_total = float(parts[1])
                    size = int(float(parts[2]))

                    speed_mbps = (speed_bps * 8) / 1_000_000
                    size_mb = size / 1_000_000

                    log.write(f"[green]Download Speed: {speed_mbps:.2f} Mbps[/green]")
                    log.write(f"[cyan]Downloaded: {size_mb:.1f} MB in {time_total:.1f}s[/cyan]")

            progress.progress = 100
            status.update("[green]Download test complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Speed test failed[/red]")

    @work(exclusive=True)
    async def do_upload_test(self, server: str = "tele2") -> None:
        log = self.query_one("#speed-results", RichLog)
        status = self.query_one("#speed-status", Static)
        progress = self.query_one("#speed-progress", ProgressBar)

        log.clear()
        server_info = self._get_server_urls(server)
        progress.progress = 0

        if not server_info.get("upload"):
            log.write(f"[yellow]Upload test not available for {server_info['name']}[/yellow]")
            log.write("[cyan]Try Tele2 or Cloudflare server[/cyan]")
            status.update("[yellow]Upload not supported[/yellow]")
            return

        status.update(f"[cyan]Testing upload to {server_info['name']}...[/cyan]")

        try:
            log.write(f"[bold cyan]Upload Speed Test[/bold cyan]")
            log.write(f"[cyan]Server: {server_info['name']}[/cyan]")
            log.write("[cyan]Generating test data...[/cyan]\n")
            progress.progress = 10

            # Generate 5MB of random data for upload
            proc = await asyncio.create_subprocess_exec(
                "curl", "-X", "POST", "-w", "%{speed_upload}|%{time_total}",
                "-s", "--max-time", "60",
                "-d", "@/dev/urandom", "--data-binary", "-H", "Content-Type: application/octet-stream",
                "-o", "/dev/null", "--limit-rate", "0",
                server_info["upload"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            progress.progress = 80

            if stdout and '|' in stdout.decode():
                parts = stdout.decode().strip().split("|")
                speed_bps = float(parts[0]) if parts[0] else 0
                speed_mbps = (speed_bps * 8) / 1_000_000
                log.write(f"[green]Upload Speed: {speed_mbps:.2f} Mbps[/green]")
            else:
                log.write("[yellow]Upload test completed (speed data unavailable)[/yellow]")

            progress.progress = 100
            status.update("[green]Upload test complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Upload test failed[/red]")

    @work(exclusive=True)
    async def do_full_test(self, server: str = "tele2") -> None:
        log = self.query_one("#speed-results", RichLog)
        status = self.query_one("#speed-status", Static)
        progress = self.query_one("#speed-progress", ProgressBar)

        log.clear()
        server_info = self._get_server_urls(server)
        status.update(f"[cyan]Running full speed test...[/cyan]")
        progress.progress = 0

        try:
            log.write(f"[bold cyan]Full Speed Test[/bold cyan]")
            log.write(f"[cyan]Server: {server_info['name']}[/cyan]\n")

            # Latency test first
            log.write("[cyan]Testing latency...[/cyan]")
            progress.progress = 10

            proc = await asyncio.create_subprocess_exec(
                "ping", "-c", "5", "-q", "8.8.8.8",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                match = re.search(r'rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)', stdout.decode())
                if match:
                    min_rtt, avg_rtt, max_rtt = match.groups()
                    log.write(f"[green]Latency: {avg_rtt} ms (min: {min_rtt}, max: {max_rtt})[/green]\n")

            # Download test
            log.write("[cyan]Testing download speed...[/cyan]")
            progress.progress = 30

            proc = await asyncio.create_subprocess_exec(
                "curl", "-o", "/dev/null", "-w", "%{speed_download}",
                "-s", "--max-time", "30", server_info["download"],
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            download_mbps = 0
            if stdout:
                speed_bps = float(stdout.decode().strip())
                download_mbps = (speed_bps * 8) / 1_000_000
                log.write(f"[green]Download: {download_mbps:.2f} Mbps[/green]\n")

            progress.progress = 60

            # Upload test if available
            upload_mbps = 0
            if server_info.get("upload"):
                log.write("[cyan]Testing upload speed...[/cyan]")

                proc = await asyncio.create_subprocess_exec(
                    "curl", "-X", "POST", "-w", "%{speed_upload}",
                    "-s", "--max-time", "30", "-d", "@/dev/zero",
                    "-o", "/dev/null", server_info["upload"],
                    stdout=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()

                if stdout:
                    speed_bps = float(stdout.decode().strip()) if stdout.decode().strip() else 0
                    upload_mbps = (speed_bps * 8) / 1_000_000
                    log.write(f"[green]Upload: {upload_mbps:.2f} Mbps[/green]\n")
            else:
                log.write("[yellow]Upload test not available for this server[/yellow]\n")

            progress.progress = 100

            # Summary
            log.write("[bold cyan]Summary:[/bold cyan]")
            log.write(f"  Download: [green]{download_mbps:.2f} Mbps[/green]")
            if upload_mbps > 0:
                log.write(f"  Upload:   [green]{upload_mbps:.2f} Mbps[/green]")

            status.update("[green]Full test complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Full test failed[/red]")

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
            Horizontal(
                Button("Per-Process", id="btn-per-process"),
                Button("Top Talkers", id="btn-top-talkers"),
                Button("Socket Stats", id="btn-socket-stats"),
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

    @on(Button.Pressed, "#btn-per-process")
    def show_per_process(self) -> None:
        self.get_per_process()

    @on(Button.Pressed, "#btn-top-talkers")
    def show_top_talkers(self) -> None:
        self.get_top_talkers()

    @on(Button.Pressed, "#btn-socket-stats")
    def show_socket_stats(self) -> None:
        self.get_socket_stats()

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

    @work(exclusive=True)
    async def get_per_process(self) -> None:
        """Get network usage per process."""
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Getting per-process network usage...[/cyan]")
        log.write("[bold cyan]Network Usage by Process[/bold cyan]\n")

        try:
            # Use ss with process info
            proc = await asyncio.create_subprocess_exec(
                "ss", "-tunap",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                # Parse and aggregate by process
                process_conns = {}
                lines = stdout.decode().strip().split('\n')[1:]  # Skip header

                for line in lines:
                    # Extract process name from users:((...))
                    match = re.search(r'users:\(\("([^"]+)"', line)
                    if match:
                        proc_name = match.group(1)
                        if proc_name not in process_conns:
                            process_conns[proc_name] = {'estab': 0, 'listen': 0, 'other': 0}
                        if 'ESTAB' in line:
                            process_conns[proc_name]['estab'] += 1
                        elif 'LISTEN' in line:
                            process_conns[proc_name]['listen'] += 1
                        else:
                            process_conns[proc_name]['other'] += 1

                log.write(f"{'Process':<25} {'Established':<12} {'Listening':<10} {'Other'}")
                log.write("-" * 60)

                for proc_name, counts in sorted(process_conns.items(), key=lambda x: x[1]['estab'], reverse=True):
                    if counts['estab'] > 0:
                        log.write(f"[green]{proc_name:<25} {counts['estab']:<12} {counts['listen']:<10} {counts['other']}[/green]")
                    elif counts['listen'] > 0:
                        log.write(f"[yellow]{proc_name:<25} {counts['estab']:<12} {counts['listen']:<10} {counts['other']}[/yellow]")
                    else:
                        log.write(f"[gray]{proc_name:<25} {counts['estab']:<12} {counts['listen']:<10} {counts['other']}[/gray]")

            status.update("[green]Per-process info loaded[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def get_top_talkers(self) -> None:
        """Get top network connections by data transfer."""
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Analyzing top connections...[/cyan]")
        log.write("[bold cyan]Top Network Connections[/bold cyan]\n")

        try:
            # Get established connections with byte counts
            proc = await asyncio.create_subprocess_exec(
                "ss", "-tni", "state", "established",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                connections = []
                lines = stdout.decode().strip().split('\n')

                i = 0
                while i < len(lines):
                    line = lines[i]
                    if ':' in line and 'ESTAB' not in line:
                        # Connection line
                        parts = line.split()
                        if len(parts) >= 4:
                            local = parts[2] if len(parts) > 2 else "?"
                            remote = parts[3] if len(parts) > 3 else "?"

                            # Next line might have bytes info
                            bytes_recv = 0
                            bytes_sent = 0
                            if i + 1 < len(lines):
                                next_line = lines[i + 1]
                                recv_match = re.search(r'bytes_received:(\d+)', next_line)
                                sent_match = re.search(r'bytes_sent:(\d+)', next_line)
                                if recv_match:
                                    bytes_recv = int(recv_match.group(1))
                                if sent_match:
                                    bytes_sent = int(sent_match.group(1))

                            connections.append((local, remote, bytes_recv, bytes_sent))
                    i += 1

                # Sort by total bytes
                connections.sort(key=lambda x: x[2] + x[3], reverse=True)

                log.write(f"{'Local':<25} {'Remote':<25} {'Recv':<12} {'Sent'}")
                log.write("-" * 75)

                def fmt_bytes(b):
                    if b > 1_000_000:
                        return f"{b/1_000_000:.1f} MB"
                    elif b > 1_000:
                        return f"{b/1_000:.1f} KB"
                    return f"{b} B"

                for local, remote, recv, sent in connections[:15]:
                    total = recv + sent
                    if total > 1_000_000:
                        color = "green"
                    elif total > 10_000:
                        color = "yellow"
                    else:
                        color = "gray"
                    log.write(f"[{color}]{local:<25} {remote:<25} {fmt_bytes(recv):<12} {fmt_bytes(sent)}[/{color}]")

            status.update("[green]Top talkers loaded[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def get_socket_stats(self) -> None:
        """Get socket statistics."""
        log = self.query_one("#monitor-results", RichLog)
        status = self.query_one("#monitor-status", Static)

        log.clear()
        status.update("[cyan]Getting socket statistics...[/cyan]")
        log.write("[bold cyan]Socket Statistics[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ss", "-s",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if 'TCP:' in line or 'UDP:' in line:
                        log.write(f"[bold cyan]{line}[/bold cyan]")
                    elif 'estab' in line.lower():
                        log.write(f"[green]{line}[/green]")
                    elif 'closed' in line.lower() or 'time-wait' in line.lower():
                        log.write(f"[yellow]{line}[/yellow]")
                    else:
                        log.write(line)

            # Also get netstat-style summary
            log.write("\n[bold cyan]Protocol Statistics[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "cat", "/proc/net/snmp",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                lines = stdout.decode().strip().split('\n')
                i = 0
                while i < len(lines) - 1:
                    if lines[i].startswith('Tcp:') or lines[i].startswith('Udp:'):
                        headers = lines[i].split()
                        values = lines[i + 1].split()
                        protocol = headers[0].rstrip(':')
                        log.write(f"\n[cyan]{protocol}:[/cyan]")

                        for j in range(1, min(len(headers), len(values))):
                            header = headers[j]
                            value = values[j]
                            if header in ['InSegs', 'OutSegs', 'InDatagrams', 'OutDatagrams']:
                                log.write(f"  {header}: [green]{int(value):,}[/green]")
                            elif header in ['InErrs', 'OutErrs', 'InCsumErrors']:
                                if int(value) > 0:
                                    log.write(f"  {header}: [red]{int(value):,}[/red]")
                    i += 2

            status.update("[green]Socket stats loaded[/green]")

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
            Horizontal(
                Button("ARP Table", id="btn-arp"),
                Button("Routes", id="btn-routes"),
                Button("DNS Flush", id="btn-dns-flush"),
                Button("Interfaces", id="btn-ifaces"),
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

    @on(Button.Pressed, "#btn-arp")
    def do_arp(self) -> None:
        self.view_arp_table()

    @on(Button.Pressed, "#btn-routes")
    def do_routes(self) -> None:
        self.view_routes()

    @on(Button.Pressed, "#btn-dns-flush")
    def do_dns_flush(self) -> None:
        self.flush_dns()

    @on(Button.Pressed, "#btn-ifaces")
    def do_ifaces(self) -> None:
        self.view_interfaces()

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

    @work(exclusive=True)
    async def view_arp_table(self) -> None:
        """View the ARP table."""
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update("[cyan]Reading ARP table...[/cyan]")
        log.write("[bold cyan]ARP Table[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "neigh", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                log.write(f"{'IP Address':<18} {'MAC Address':<20} {'State':<12} {'Vendor'}")
                log.write("-" * 70)

                for line in stdout.decode().strip().split('\n'):
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 4:
                            ip = parts[0]
                            # Find MAC address (after 'lladdr')
                            mac = "N/A"
                            state = "INCOMPLETE"
                            for i, p in enumerate(parts):
                                if p == "lladdr" and i + 1 < len(parts):
                                    mac = parts[i + 1]
                                if p in ["REACHABLE", "STALE", "DELAY", "PROBE", "FAILED", "PERMANENT"]:
                                    state = p

                            vendor = lookup_mac_vendor(mac) if mac != "N/A" else ""

                            if state == "REACHABLE":
                                log.write(f"[green]{ip:<18} {mac:<20} {state:<12} {vendor}[/green]")
                            elif state == "STALE":
                                log.write(f"[yellow]{ip:<18} {mac:<20} {state:<12} {vendor}[/yellow]")
                            else:
                                log.write(f"[gray]{ip:<18} {mac:<20} {state:<12} {vendor}[/gray]")

            status.update("[green]ARP table loaded[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed to read ARP table[/red]")

    @work(exclusive=True)
    async def view_routes(self) -> None:
        """View the routing table."""
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update("[cyan]Reading routing table...[/cyan]")
        log.write("[bold cyan]Routing Table[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "route", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if line.strip():
                        if line.startswith("default"):
                            log.write(f"[green]{line}[/green]")
                        elif "linkdown" in line.lower():
                            log.write(f"[red]{line}[/red]")
                        else:
                            log.write(f"[cyan]{line}[/cyan]")

            # Also show IPv6 routes
            log.write("\n[bold cyan]IPv6 Routes[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "ip", "-6", "route", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if line.strip():
                        log.write(f"[yellow]{line}[/yellow]")

            status.update("[green]Routing table loaded[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed to read routes[/red]")

    @work(exclusive=True)
    async def flush_dns(self) -> None:
        """Flush DNS cache."""
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update("[cyan]Flushing DNS cache...[/cyan]")
        log.write("[bold cyan]DNS Cache Flush[/bold cyan]\n")

        try:
            # Try systemd-resolve first (most common on modern systems)
            proc = await asyncio.create_subprocess_exec(
                "sudo", "systemd-resolve", "--flush-caches",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                log.write("[green]✓ systemd-resolve cache flushed[/green]")
            else:
                # Try resolvectl (newer systems)
                proc = await asyncio.create_subprocess_exec(
                    "sudo", "resolvectl", "flush-caches",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()

                if proc.returncode == 0:
                    log.write("[green]✓ resolvectl cache flushed[/green]")
                else:
                    log.write("[yellow]⚠ No systemd-resolved found[/yellow]")

            # Also try nscd if available
            proc = await asyncio.create_subprocess_exec(
                "sudo", "nscd", "-i", "hosts",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await proc.communicate()

            if proc.returncode == 0:
                log.write("[green]✓ nscd hosts cache invalidated[/green]")

            log.write("\n[gray]DNS cache has been flushed[/gray]")
            status.update("[green]DNS cache flushed[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]DNS flush failed[/red]")

    @work(exclusive=True)
    async def view_interfaces(self) -> None:
        """View network interfaces."""
        log = self.query_one("#tools-results", RichLog)
        status = self.query_one("#tools-status", Static)

        log.clear()
        status.update("[cyan]Getting interface info...[/cyan]")
        log.write("[bold cyan]Network Interfaces[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ip", "-c", "addr", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                current_iface = ""
                for line in stdout.decode().strip().split('\n'):
                    if line and not line.startswith(' '):
                        # Interface line
                        match = re.match(r'\d+:\s+(\S+):', line)
                        if match:
                            current_iface = match.group(1)
                            state = "UP" if "UP" in line else "DOWN"
                            if state == "UP":
                                log.write(f"\n[bold green]{current_iface}[/bold green] [{state}]")
                            else:
                                log.write(f"\n[bold red]{current_iface}[/bold red] [{state}]")
                    elif "inet " in line:
                        # IPv4 address
                        match = re.search(r'inet (\S+)', line)
                        if match:
                            log.write(f"  [cyan]IPv4:[/cyan] {match.group(1)}")
                    elif "inet6" in line and "scope global" in line:
                        # Global IPv6 address
                        match = re.search(r'inet6 (\S+)', line)
                        if match:
                            log.write(f"  [cyan]IPv6:[/cyan] {match.group(1)}")
                    elif "link/ether" in line:
                        # MAC address
                        match = re.search(r'link/ether (\S+)', line)
                        if match:
                            mac = match.group(1)
                            vendor = lookup_mac_vendor(mac)
                            log.write(f"  [cyan]MAC:[/cyan]  {mac} ({vendor})")

            status.update("[green]Interface info loaded[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed to get interfaces[/red]")


class HTTPModule(Container):
    """HTTP inspection module."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("URL:", classes="form-label"),
                Input(placeholder="https://example.com", id="http-url"),
                classes="form-row",
            ),
            Horizontal(
                Label("Method:", classes="form-label"),
                Select([
                    ("GET", "GET"),
                    ("HEAD", "HEAD"),
                    ("POST", "POST"),
                    ("OPTIONS", "OPTIONS"),
                    ("PUT", "PUT"),
                    ("DELETE", "DELETE"),
                ], id="http-method", value="GET"),
                classes="form-row",
            ),
            Horizontal(
                Button("Send", id="btn-http-send", variant="primary"),
                Button("Headers", id="btn-http-headers"),
                Button("Redirects", id="btn-http-redirects"),
                Button("Clear", id="btn-http-clear", variant="error"),
                classes="form-row",
            ),
            Static("", id="http-status", classes="status-text"),
            RichLog(id="http-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-http-send")
    def do_send(self) -> None:
        url = self.query_one("#http-url", Input).value.strip()
        if not url:
            self.query_one("#http-status", Static).update("[red]Enter a URL[/red]")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self.query_one("#http-url", Input).value = url
        method = self.query_one("#http-method", Select).value
        self.send_request(url, method)

    @on(Button.Pressed, "#btn-http-headers")
    def do_headers(self) -> None:
        url = self.query_one("#http-url", Input).value.strip()
        if not url:
            self.query_one("#http-status", Static).update("[red]Enter a URL[/red]")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.get_headers(url)

    @on(Button.Pressed, "#btn-http-redirects")
    def do_redirects(self) -> None:
        url = self.query_one("#http-url", Input).value.strip()
        if not url:
            self.query_one("#http-status", Static).update("[red]Enter a URL[/red]")
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        self.trace_redirects(url)

    @on(Button.Pressed, "#btn-http-clear")
    def clear_results(self) -> None:
        self.query_one("#http-results", RichLog).clear()
        self.query_one("#http-status", Static).update("")

    @work(exclusive=True)
    async def send_request(self, url: str, method: str) -> None:
        log = self.query_one("#http-results", RichLog)
        status = self.query_one("#http-status", Static)

        log.clear()
        status.update(f"[cyan]Sending {method} request...[/cyan]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-o", "/dev/null", "-w",
                "%{http_code}|%{time_total}|%{size_download}|%{speed_download}|%{remote_ip}",
                "-X", method, "-L", "--max-time", "30", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                parts = stdout.decode().strip().split("|")
                if len(parts) >= 5:
                    code, time_s, size, speed, ip = parts[:5]
                    code_int = int(code) if code.isdigit() else 0

                    log.write(f"[bold cyan]HTTP Response[/bold cyan]\n")
                    log.write(f"[green]URL:[/green] {url}")
                    log.write(f"[green]Method:[/green] {method}")
                    log.write(f"[green]Remote IP:[/green] {ip}")

                    # Color code status
                    if 200 <= code_int < 300:
                        log.write(f"[green]Status Code:[/green] [bold green]{code}[/bold green]")
                    elif 300 <= code_int < 400:
                        log.write(f"[green]Status Code:[/green] [bold yellow]{code}[/bold yellow]")
                    elif 400 <= code_int < 500:
                        log.write(f"[green]Status Code:[/green] [bold red]{code}[/bold red]")
                    else:
                        log.write(f"[green]Status Code:[/green] [bold magenta]{code}[/bold magenta]")

                    log.write(f"[green]Response Time:[/green] {float(time_s)*1000:.0f} ms")
                    size_kb = int(size) / 1024
                    log.write(f"[green]Content Size:[/green] {size_kb:.1f} KB")
                    speed_kb = float(speed) / 1024
                    log.write(f"[green]Download Speed:[/green] {speed_kb:.1f} KB/s")

            status.update("[green]Request complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Request failed[/red]")

    @work(exclusive=True)
    async def get_headers(self, url: str) -> None:
        log = self.query_one("#http-results", RichLog)
        status = self.query_one("#http-status", Static)

        log.clear()
        status.update("[cyan]Fetching headers...[/cyan]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-I", "-L", "--max-time", "30", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                log.write(f"[bold cyan]HTTP Headers: {url}[/bold cyan]\n")
                for line in stdout.decode().strip().split('\n'):
                    if line.startswith("HTTP/"):
                        log.write(f"[bold magenta]{line}[/bold magenta]")
                    elif ":" in line:
                        key, _, value = line.partition(":")
                        key_lower = key.lower()
                        # Highlight security headers
                        if any(h in key_lower for h in ['security', 'x-frame', 'x-xss', 'x-content', 'strict-transport', 'content-security']):
                            log.write(f"[green]{key}:[/green][cyan]{value}[/cyan]")
                        elif any(h in key_lower for h in ['server', 'x-powered']):
                            log.write(f"[yellow]{key}:[/yellow]{value}")
                        else:
                            log.write(f"[green]{key}:[/green]{value}")
                    elif line.strip():
                        log.write(line)

            status.update("[green]Headers retrieved[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def trace_redirects(self, url: str) -> None:
        log = self.query_one("#http-results", RichLog)
        status = self.query_one("#http-status", Static)

        log.clear()
        status.update("[cyan]Tracing redirects...[/cyan]")

        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-L", "-w", "%{url_effective}", "-o", "/dev/null",
                "--max-redirs", "10", "--max-time", "30",
                "-D", "-", url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                log.write(f"[bold cyan]Redirect Chain: {url}[/bold cyan]\n")
                output = stdout.decode()
                lines = output.split('\n')

                hop = 0
                for line in lines:
                    if line.startswith("HTTP/"):
                        log.write(f"\n[bold yellow]Hop {hop}:[/bold yellow] {line.strip()}")
                        hop += 1
                    elif line.lower().startswith("location:"):
                        log.write(f"  [cyan]→ {line.split(':', 1)[1].strip()}[/cyan]")

                # Final URL is the last part
                final = lines[-1] if lines else url
                if not final.startswith("HTTP"):
                    log.write(f"\n[bold green]Final URL:[/bold green] {final}")

            status.update("[green]Redirect trace complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")


class SecurityModule(Container):
    """Security checking module."""

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Target:", classes="form-label"),
                Input(placeholder="domain.com or IP", id="sec-target"),
                classes="form-row",
            ),
            Horizontal(
                Button("HTTP Security", id="btn-sec-http", variant="primary"),
                Button("Email Security", id="btn-sec-email"),
                Button("Banner Grab", id="btn-sec-banner"),
                Button("Clear", id="btn-sec-clear", variant="error"),
                classes="form-row",
            ),
            Horizontal(
                Label("Port:", classes="form-label"),
                Input(placeholder="22, 80, 443...", id="sec-port", value="22"),
                classes="form-row",
            ),
            Static("", id="sec-status", classes="status-text"),
            RichLog(id="sec-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-sec-http")
    def do_http_security(self) -> None:
        target = self.query_one("#sec-target", Input).value.strip()
        if not target:
            self.query_one("#sec-status", Static).update("[red]Enter a target[/red]")
            return
        self.check_http_security(target)

    @on(Button.Pressed, "#btn-sec-email")
    def do_email_security(self) -> None:
        target = self.query_one("#sec-target", Input).value.strip()
        if not target:
            self.query_one("#sec-status", Static).update("[red]Enter a domain[/red]")
            return
        self.check_email_security(target)

    @on(Button.Pressed, "#btn-sec-banner")
    def do_banner(self) -> None:
        target = self.query_one("#sec-target", Input).value.strip()
        port = self.query_one("#sec-port", Input).value.strip()
        if not target:
            self.query_one("#sec-status", Static).update("[red]Enter a target[/red]")
            return
        self.grab_banner(target, port or "22")

    @on(Button.Pressed, "#btn-sec-clear")
    def clear_results(self) -> None:
        self.query_one("#sec-results", RichLog).clear()
        self.query_one("#sec-status", Static).update("")

    @work(exclusive=True)
    async def check_http_security(self, target: str) -> None:
        log = self.query_one("#sec-results", RichLog)
        status = self.query_one("#sec-status", Static)

        log.clear()
        if not target.startswith(("http://", "https://")):
            target = "https://" + target

        status.update("[cyan]Checking HTTP security headers...[/cyan]")
        log.write(f"[bold cyan]HTTP Security Check: {target}[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "curl", "-s", "-I", "-L", "--max-time", "15", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            headers_found = {}
            if stdout:
                for line in stdout.decode().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        headers_found[key.lower().strip()] = value.strip()

            # Security headers checklist
            security_headers = {
                'strict-transport-security': ('HSTS', 'Enforces HTTPS'),
                'x-frame-options': ('X-Frame-Options', 'Clickjacking protection'),
                'x-content-type-options': ('X-Content-Type-Options', 'MIME sniffing protection'),
                'x-xss-protection': ('X-XSS-Protection', 'XSS filter'),
                'content-security-policy': ('CSP', 'Content Security Policy'),
                'referrer-policy': ('Referrer-Policy', 'Referrer control'),
                'permissions-policy': ('Permissions-Policy', 'Feature control'),
            }

            log.write("[bold cyan]Security Headers:[/bold cyan]")
            for header, (name, desc) in security_headers.items():
                if header in headers_found:
                    log.write(f"[green]✓ {name}:[/green] {headers_found[header][:50]}")
                else:
                    log.write(f"[red]✗ {name}:[/red] Missing ({desc})")

            # Check for information disclosure
            log.write("\n[bold cyan]Information Disclosure:[/bold cyan]")
            if 'server' in headers_found:
                log.write(f"[yellow]⚠ Server:[/yellow] {headers_found['server']}")
            if 'x-powered-by' in headers_found:
                log.write(f"[yellow]⚠ X-Powered-By:[/yellow] {headers_found['x-powered-by']}")

            status.update("[green]Security check complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Check failed[/red]")

    @work(exclusive=True)
    async def check_email_security(self, domain: str) -> None:
        log = self.query_one("#sec-results", RichLog)
        status = self.query_one("#sec-status", Static)

        log.clear()
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

        status.update("[cyan]Checking email security records...[/cyan]")
        log.write(f"[bold cyan]Email Security Check: {domain}[/bold cyan]\n")

        try:
            # SPF
            log.write("[bold cyan]SPF Record:[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "dig", "+short", "TXT", domain,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            spf_found = False
            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if 'spf' in line.lower():
                        log.write(f"[green]✓ {line}[/green]")
                        spf_found = True
            if not spf_found:
                log.write("[red]✗ No SPF record found[/red]")

            # DMARC
            log.write("\n[bold cyan]DMARC Record:[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "dig", "+short", "TXT", f"_dmarc.{domain}",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if stdout and stdout.decode().strip():
                log.write(f"[green]✓ {stdout.decode().strip()}[/green]")
            else:
                log.write("[red]✗ No DMARC record found[/red]")

            # DKIM (common selectors)
            log.write("\n[bold cyan]DKIM Records:[/bold cyan]")
            dkim_selectors = ['default', 'google', 'selector1', 'selector2', 'k1', 'mail']
            dkim_found = False
            for selector in dkim_selectors:
                proc = await asyncio.create_subprocess_exec(
                    "dig", "+short", "TXT", f"{selector}._domainkey.{domain}",
                    stdout=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if stdout and stdout.decode().strip() and 'DKIM' not in stdout.decode():
                    if 'v=DKIM' in stdout.decode() or 'p=' in stdout.decode():
                        log.write(f"[green]✓ {selector}._domainkey: Found[/green]")
                        dkim_found = True
                        break
            if not dkim_found:
                log.write("[yellow]⚠ No common DKIM selectors found[/yellow]")

            # MX records
            log.write("\n[bold cyan]MX Records:[/bold cyan]")
            proc = await asyncio.create_subprocess_exec(
                "dig", "+short", "MX", domain,
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if line.strip():
                        log.write(f"[green]{line}[/green]")
            else:
                log.write("[red]✗ No MX records found[/red]")

            status.update("[green]Email security check complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Check failed[/red]")

    @work(exclusive=True)
    async def grab_banner(self, target: str, port: str) -> None:
        log = self.query_one("#sec-results", RichLog)
        status = self.query_one("#sec-status", Static)

        log.clear()
        status.update(f"[cyan]Grabbing banner from {target}:{port}...[/cyan]")
        log.write(f"[bold cyan]Banner Grab: {target}:{port}[/bold cyan]\n")

        try:
            # Use nmap for banner grabbing
            proc = await asyncio.create_subprocess_exec(
                "nmap", "-sV", "--script=banner", "-p", port, target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if stdout:
                for line in stdout.decode().split('\n'):
                    if 'open' in line.lower():
                        log.write(f"[green]{line}[/green]")
                    elif 'banner' in line.lower() or 'service' in line.lower():
                        log.write(f"[cyan]{line}[/cyan]")
                    elif line.strip() and not line.startswith('Starting') and not line.startswith('Nmap done'):
                        log.write(line)

            status.update("[green]Banner grab complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Banner grab failed[/red]")


class BluetoothModule(Container):
    """Bluetooth scanner module."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scanning = False

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Button("Scan Devices", id="btn-bt-scan", variant="primary"),
                Button("Paired Devices", id="btn-bt-paired"),
                Button("Controller Info", id="btn-bt-info"),
                Button("Clear", id="btn-bt-clear", variant="error"),
                classes="form-row",
            ),
            Static("", id="bt-status", classes="status-text"),
            RichLog(id="bt-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-bt-scan")
    def do_scan(self) -> None:
        if self._scanning:
            self._scanning = False
            self.query_one("#bt-status", Static).update("[yellow]Stopping scan...[/yellow]")
        else:
            self._scanning = True
            self.scan_devices()

    @on(Button.Pressed, "#btn-bt-paired")
    def do_paired(self) -> None:
        self._scanning = False
        self.show_paired()

    @on(Button.Pressed, "#btn-bt-info")
    def do_info(self) -> None:
        self._scanning = False
        self.show_controller()

    @on(Button.Pressed, "#btn-bt-clear")
    def clear_results(self) -> None:
        self._scanning = False
        self.query_one("#bt-results", RichLog).clear()
        self.query_one("#bt-status", Static).update("")

    @work(exclusive=True)
    async def scan_devices(self) -> None:
        log = self.query_one("#bt-results", RichLog)
        status = self.query_one("#bt-status", Static)

        log.clear()
        status.update("[cyan]Scanning for Bluetooth devices (10s)...[/cyan]")
        log.write("[bold cyan]Bluetooth Device Scan[/bold cyan]\n")

        try:
            # Start scan
            await asyncio.create_subprocess_exec(
                "bluetoothctl", "scan", "on",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            await asyncio.sleep(10)

            # Stop scan
            await asyncio.create_subprocess_exec(
                "bluetoothctl", "scan", "off",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )

            # Get devices
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "devices",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                devices = stdout.decode().strip().split('\n')
                log.write(f"[cyan]Found {len(devices)} device(s):[/cyan]\n")
                for device in devices:
                    if device.strip():
                        parts = device.split(' ', 2)
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = parts[2] if len(parts) > 2 else "Unknown"
                            vendor = lookup_mac_vendor(mac)
                            log.write(f"[green]{name}[/green]")
                            log.write(f"  MAC: {mac} ({vendor})")
            else:
                log.write("[yellow]No devices found[/yellow]")

            status.update("[green]Scan complete[/green]")
            self._scanning = False

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Scan failed[/red]")
            self._scanning = False

    @work(exclusive=True)
    async def show_paired(self) -> None:
        log = self.query_one("#bt-results", RichLog)
        status = self.query_one("#bt-status", Static)

        log.clear()
        status.update("[cyan]Getting paired devices...[/cyan]")
        log.write("[bold cyan]Paired Bluetooth Devices[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "paired-devices",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                devices = stdout.decode().strip().split('\n')
                for device in devices:
                    if device.strip():
                        parts = device.split(' ', 2)
                        if len(parts) >= 3:
                            mac = parts[1]
                            name = parts[2]

                            # Get connection status
                            proc2 = await asyncio.create_subprocess_exec(
                                "bluetoothctl", "info", mac,
                                stdout=asyncio.subprocess.PIPE,
                            )
                            info_out, _ = await proc2.communicate()
                            connected = "Connected: yes" in info_out.decode()

                            if connected:
                                log.write(f"[green]● {name}[/green] [bold green](connected)[/bold green]")
                            else:
                                log.write(f"[yellow]○ {name}[/yellow]")
                            log.write(f"  MAC: {mac}")
            else:
                log.write("[yellow]No paired devices[/yellow]")

            status.update("[green]Done[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def show_controller(self) -> None:
        log = self.query_one("#bt-results", RichLog)
        status = self.query_one("#bt-status", Static)

        log.clear()
        status.update("[cyan]Getting controller info...[/cyan]")
        log.write("[bold cyan]Bluetooth Controller Info[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "bluetoothctl", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                for line in stdout.decode().strip().split('\n'):
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        if key == "Powered":
                            color = "green" if value == "yes" else "red"
                            log.write(f"[{color}]{key}: {value}[/{color}]")
                        elif key == "Discoverable" or key == "Pairable":
                            color = "yellow" if value == "yes" else "gray"
                            log.write(f"[{color}]{key}: {value}[/{color}]")
                        else:
                            log.write(f"[cyan]{key}:[/cyan] {value}")

            status.update("[green]Done[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")


class PacketModule(Container):
    """Packet capture module (tcpdump wrapper)."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._capturing = False
        self._proc = None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Horizontal(
                Label("Interface:", classes="form-label"),
                Input(placeholder="any, wlan0, eth0...", id="pkt-iface", value="any"),
                classes="form-row",
            ),
            Horizontal(
                Label("Filter:", classes="form-label"),
                Input(placeholder="port 80, host 192.168.1.1, tcp...", id="pkt-filter"),
                classes="form-row",
            ),
            Horizontal(
                Label("Count:", classes="form-label"),
                Input(placeholder="Number of packets (0=unlimited)", id="pkt-count", value="50"),
                classes="form-row",
            ),
            Horizontal(
                Button("Capture", id="btn-pkt-start", variant="primary"),
                Button("Stop", id="btn-pkt-stop", variant="error"),
                Button("Connections", id="btn-pkt-conns"),
                Button("Clear", id="btn-pkt-clear"),
                classes="form-row",
            ),
            Static("", id="pkt-status", classes="status-text"),
            RichLog(id="pkt-results", highlight=True, markup=True),
            classes="module-container",
        )

    @on(Button.Pressed, "#btn-pkt-start")
    def do_start(self) -> None:
        if self._capturing:
            return
        iface = self.query_one("#pkt-iface", Input).value.strip() or "any"
        filter_exp = self.query_one("#pkt-filter", Input).value.strip()
        count = self.query_one("#pkt-count", Input).value.strip() or "50"
        self.start_capture(iface, filter_exp, count)

    @on(Button.Pressed, "#btn-pkt-stop")
    def do_stop(self) -> None:
        self.stop_capture()

    @on(Button.Pressed, "#btn-pkt-conns")
    def do_conns(self) -> None:
        self.show_connections()

    @on(Button.Pressed, "#btn-pkt-clear")
    def clear_results(self) -> None:
        self.stop_capture()
        self.query_one("#pkt-results", RichLog).clear()
        self.query_one("#pkt-status", Static).update("")

    def stop_capture(self) -> None:
        self._capturing = False
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
        self.query_one("#pkt-status", Static).update("[yellow]Capture stopped[/yellow]")

    @work(exclusive=True)
    async def start_capture(self, iface: str, filter_exp: str, count: str) -> None:
        log = self.query_one("#pkt-results", RichLog)
        status = self.query_one("#pkt-status", Static)

        log.clear()
        self._capturing = True
        status.update(f"[cyan]Capturing on {iface}...[/cyan]")
        log.write(f"[bold cyan]Packet Capture: {iface}[/bold cyan]")
        if filter_exp:
            log.write(f"[cyan]Filter: {filter_exp}[/cyan]")
        log.write("")

        try:
            cmd = ["sudo", "tcpdump", "-i", iface, "-n", "-l"]
            if count and count != "0":
                cmd.extend(["-c", count])
            if filter_exp:
                cmd.append(filter_exp)

            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async for line in self._proc.stdout:
                if not self._capturing:
                    break
                text = line.decode().rstrip()
                # Color code by protocol
                if ' > ' in text:
                    if 'HTTP' in text or '.80:' in text or ':80 ' in text:
                        log.write(f"[green]{text}[/green]")
                    elif 'HTTPS' in text or '.443:' in text or ':443 ' in text:
                        log.write(f"[cyan]{text}[/cyan]")
                    elif 'DNS' in text or '.53:' in text or ':53 ' in text:
                        log.write(f"[yellow]{text}[/yellow]")
                    elif 'SSH' in text or '.22:' in text or ':22 ' in text:
                        log.write(f"[magenta]{text}[/magenta]")
                    elif 'ICMP' in text:
                        log.write(f"[blue]{text}[/blue]")
                    else:
                        log.write(text)
                else:
                    log.write(f"[gray]{text}[/gray]")

            await self._proc.wait()
            status.update("[green]Capture complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Capture failed[/red]")
        finally:
            self._capturing = False
            self._proc = None

    @work(exclusive=True)
    async def show_connections(self) -> None:
        log = self.query_one("#pkt-results", RichLog)
        status = self.query_one("#pkt-status", Static)

        log.clear()
        status.update("[cyan]Getting active connections...[/cyan]")
        log.write("[bold cyan]Active Network Connections[/bold cyan]\n")

        try:
            proc = await asyncio.create_subprocess_exec(
                "ss", "-tunap",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            if stdout:
                lines = stdout.decode().strip().split('\n')
                for i, line in enumerate(lines):
                    if i == 0:
                        log.write(f"[cyan]{line}[/cyan]")
                    elif 'ESTAB' in line:
                        log.write(f"[green]{line}[/green]")
                    elif 'LISTEN' in line:
                        log.write(f"[yellow]{line}[/yellow]")
                    elif 'TIME-WAIT' in line:
                        log.write(f"[gray]{line}[/gray]")
                    else:
                        log.write(line)

            status.update("[green]Done[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")


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
    """NetRunner v3.0 - Cyberpunk Network Toolkit."""

    TITLE = "NETRUNNER"
    CSS_PATH = "netrunner.tcss"

    BINDINGS = [
        Binding("1", "tab_scanner", "Scan", show=True),
        Binding("2", "tab_dns", "DNS", show=True),
        Binding("3", "tab_wifi", "WiFi", show=True),
        Binding("4", "tab_ping", "Ping", show=True),
        Binding("5", "tab_speed", "Speed", show=True),
        Binding("6", "tab_monitor", "Mon", show=True),
        Binding("7", "tab_tools", "Tools", show=True),
        Binding("8", "tab_geo", "Geo", show=True),
        Binding("9", "tab_http", "HTTP", show=True),
        Binding("0", "tab_security", "Sec", show=True),
        Binding("minus", "tab_bluetooth", "BT", show=True),
        Binding("equal", "tab_packets", "Pkt", show=True),
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
            with TabPane("HTTP", id="tab-http"):
                yield HTTPModule()
            with TabPane("Security", id="tab-security"):
                yield SecurityModule()
            with TabPane("Bluetooth", id="tab-bluetooth"):
                yield BluetoothModule()
            with TabPane("Packets", id="tab-packets"):
                yield PacketModule()
        yield Footer()

    def on_mount(self) -> None:
        """Set up the app on mount."""
        self.title = f"NETRUNNER v3.0 | {get_local_ip()}"
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

    def action_tab_http(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-http"

    def action_tab_security(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-security"

    def action_tab_bluetooth(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-bluetooth"

    def action_tab_packets(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-packets"

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        self.title = f"NETRUNNER v3.0 | {get_local_ip()}"
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
            "tab-http": "#http-results",
            "tab-security": "#sec-results",
            "tab-bluetooth": "#bt-results",
            "tab-packets": "#pkt-results",
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
