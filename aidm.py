#!/usr/bin/env python3
"""
AI Dungeon Master - Cyberpunk 2020 & D&D 5e
A terminal-based AI game master powered by Ollama
"""

import asyncio
import json
import os
import random
import re
import shutil
import sys
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, ScrollableContainer
from textual.screen import Screen, ModalScreen
from textual.widgets import (
    Button, Footer, Header, Input, Label, ListItem, ListView,
    MarkdownViewer, RichLog, Select, Static, TabbedContent, TabPane, TextArea
)
from textual import work
from rich.text import Text
from rich.panel import Panel
from rich.table import Table

# Paths
HOME = Path.home()
CAMPAIGNS_DIR = HOME / ".aidm" / "campaigns"
CHARACTERS_DIR = HOME / ".aidm" / "characters"

# Ollama config
OLLAMA_MODEL = os.environ.get("AIDM_MODEL", "phi3:mini")
OLLAMA_URL = "http://localhost:11434"

# Game systems
GAME_SYSTEMS = {
    "cyberpunk2020": {
        "name": "Cyberpunk 2020",
        "dice": "d10",
        "stats": ["INT", "REF", "TECH", "COOL", "ATTR", "LUCK", "MA", "BODY", "EMP"],
        "derived": ["Run", "Leap", "Lift", "Save", "BTM", "Humanity"],
        "roles": ["Solo", "Netrunner", "Techie", "Media", "Cop", "Corporate", "Fixer", "Nomad", "Rockerboy", "MedTechie"],
        "setting": """Night City, 2020. A sprawling megalopolis on the California coast,
ruled by megacorporations, street gangs, and the omnipresent Net. Chrome gleams under
neon lights, cyberware is as common as tattoos, and life is cheap. The streets are
dangerous but full of opportunity for those with the skills and chrome to survive.""",
    },
    "dnd5e": {
        "name": "D&D 5th Edition",
        "dice": "d20",
        "stats": ["STR", "DEX", "CON", "INT", "WIS", "CHA"],
        "derived": ["AC", "HP", "Initiative", "Speed", "Proficiency"],
        "roles": ["Fighter", "Wizard", "Rogue", "Cleric", "Barbarian", "Bard", "Druid", "Monk", "Paladin", "Ranger", "Sorcerer", "Warlock"],
        "setting": """A world of magic and mystery, where brave adventurers delve into
ancient dungeons, battle fearsome monsters, and seek glory and treasure. From the
bustling cities to the wild frontier, danger and opportunity await at every turn.""",
    }
}

# Cyberpunk flavor
CYBERPUNK_QUOTES = [
    "The street finds its own uses for things.",
    "Style over substance.",
    "Attitude is everything.",
    "Live on the Edge.",
    "Break the rules.",
    "Never leave a friend behind.",
    "The future is now, choomba.",
]

DND_QUOTES = [
    "Roll for initiative!",
    "You can certainly try...",
    "Are you sure you want to do that?",
    "The dice gods demand sacrifice!",
    "Critical hit!",
    "Nat 20, baby!",
]

# All available commands with descriptions
COMMANDS = [
    ("/new", "Create new campaign"),
    ("/load", "Load saved campaign"),
    ("/save", "Save current campaign"),
    ("/char", "Create/edit character"),
    ("/loadchar", "Load saved character"),
    ("/stats", "Show character stats"),
    ("/hp", "View/adjust HP (+/-N)"),
    ("/money", "View/adjust money (+/-N)"),
    ("/inventory", "Show inventory"),
    ("/additem", "Add item to inventory"),
    ("/rmitem", "Remove item from inventory"),
    ("/addcyber", "Install cyberware"),
    ("/rmcyber", "Remove cyberware"),
    ("/addspell", "Learn spell"),
    ("/rmspell", "Forget spell"),
    ("/npcs", "List known NPCs"),
    ("/addnpc", "Add NPC (name - desc)"),
    ("/rmnpc", "Remove NPC"),
    ("/quests", "List active quests"),
    ("/addquest", "Add quest"),
    ("/rmquest", "Complete/remove quest"),
    ("/location", "View/set location"),
    ("/roll", "Roll dice (e.g., 2d6+3)"),
    ("/look", "Look around"),
    ("/system", "Switch game system"),
    ("/quote", "Random quote"),
    ("/help", "Show all commands"),
    ("/clear", "Clear game log"),
]


def ensure_dirs():
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)


def get_terminal_width() -> int:
    """Get terminal width, defaulting to 80 for small screens."""
    try:
        width = shutil.get_terminal_size().columns
        # Account for borders, padding, and scrollbar (about 6 chars)
        return max(40, width - 6)
    except:
        return 74


def wrap_text(text: str, width: int = 0) -> str:
    """Wrap text to fit terminal width."""
    if width <= 0:
        width = get_terminal_width()
    # Wrap each paragraph separately to preserve intentional line breaks
    paragraphs = text.split('\n')
    wrapped = []
    for para in paragraphs:
        if para.strip():
            wrapped.append(textwrap.fill(para, width=width))
        else:
            wrapped.append('')
    return '\n'.join(wrapped)


def roll_dice(notation: str) -> tuple[int, list[int], str]:
    """
    Roll dice using standard notation (e.g., 2d6+3, 1d20, 3d8-2).
    Returns (total, individual_rolls, description).
    """
    notation = notation.lower().strip()

    # Parse notation: NdS+M or NdS-M or NdS
    match = re.match(r'(\d*)d(\d+)([+-]\d+)?', notation)
    if not match:
        return 0, [], f"Invalid notation: {notation}"

    num_dice = int(match.group(1)) if match.group(1) else 1
    sides = int(match.group(2))
    modifier = int(match.group(3)) if match.group(3) else 0

    rolls = [random.randint(1, sides) for _ in range(num_dice)]
    total = sum(rolls) + modifier

    mod_str = f"+{modifier}" if modifier > 0 else str(modifier) if modifier < 0 else ""
    desc = f"{num_dice}d{sides}{mod_str}: [{', '.join(map(str, rolls))}]{mod_str} = {total}"

    return total, rolls, desc


def get_stat_modifier(stat: int) -> int:
    """Get D&D-style modifier from stat."""
    return (stat - 10) // 2


class Character:
    """Character sheet for any game system."""

    def __init__(self, name: str = "", system: str = "cyberpunk2020"):
        self.name = name
        self.system = system
        self.role = ""
        self.level = 1
        self.stats = {}
        self.skills = {}
        self.inventory = []
        self.cyberware = []  # Cyberpunk
        self.spells = []     # D&D
        self.hp = 0
        self.max_hp = 0
        self.armor = 0
        self.money = 0
        self.notes = ""
        self.background = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "system": self.system,
            "role": self.role,
            "level": self.level,
            "stats": self.stats,
            "skills": self.skills,
            "inventory": self.inventory,
            "cyberware": self.cyberware,
            "spells": self.spells,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "armor": self.armor,
            "money": self.money,
            "notes": self.notes,
            "background": self.background,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Character":
        char = cls(data.get("name", ""), data.get("system", "cyberpunk2020"))
        char.role = data.get("role", "")
        char.level = data.get("level", 1)
        char.stats = data.get("stats", {})
        char.skills = data.get("skills", {})
        char.inventory = data.get("inventory", [])
        char.cyberware = data.get("cyberware", [])
        char.spells = data.get("spells", [])
        char.hp = data.get("hp", 0)
        char.max_hp = data.get("max_hp", 0)
        char.armor = data.get("armor", 0)
        char.money = data.get("money", 0)
        char.notes = data.get("notes", "")
        char.background = data.get("background", "")
        return char

    def save(self):
        ensure_dirs()
        filename = f"{self.name.lower().replace(' ', '_')}_{self.system}.json"
        filepath = CHARACTERS_DIR / filename
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load(cls, filepath: Path) -> "Character":
        with open(filepath) as f:
            return cls.from_dict(json.load(f))

    def summary(self) -> str:
        """Get a brief summary for the AI."""
        system_info = GAME_SYSTEMS.get(self.system, {})
        lines = [
            f"Name: {self.name}",
            f"System: {system_info.get('name', self.system)}",
            f"Role/Class: {self.role}",
            f"Level: {self.level}",
            f"HP: {self.hp}/{self.max_hp}",
        ]
        if self.stats:
            stats_str = ", ".join(f"{k}:{v}" for k, v in self.stats.items())
            lines.append(f"Stats: {stats_str}")
        if self.cyberware:
            lines.append(f"Cyberware: {', '.join(self.cyberware[:5])}")
        if self.spells:
            lines.append(f"Spells: {', '.join(self.spells[:5])}")
        return "\n".join(lines)


class Campaign:
    """Campaign state and history."""

    def __init__(self, name: str = "", system: str = "cyberpunk2020"):
        self.name = name
        self.system = system
        self.created = datetime.now().isoformat()
        self.modified = self.created
        self.characters = []  # Character names
        self.history = []     # List of {role, content, timestamp}
        self.location = ""
        self.npcs = []
        self.quests = []
        self.notes = ""
        self.session_count = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "system": self.system,
            "created": self.created,
            "modified": self.modified,
            "characters": self.characters,
            "history": self.history[-100:],  # Keep last 100 entries
            "location": self.location,
            "npcs": self.npcs,
            "quests": self.quests,
            "notes": self.notes,
            "session_count": self.session_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Campaign":
        camp = cls(data.get("name", ""), data.get("system", "cyberpunk2020"))
        camp.created = data.get("created", camp.created)
        camp.modified = data.get("modified", camp.modified)
        camp.characters = data.get("characters", [])
        camp.history = data.get("history", [])
        camp.location = data.get("location", "")
        camp.npcs = data.get("npcs", [])
        camp.quests = data.get("quests", [])
        camp.notes = data.get("notes", "")
        camp.session_count = data.get("session_count", 0)
        return camp

    def save(self):
        ensure_dirs()
        self.modified = datetime.now().isoformat()
        filename = f"{self.name.lower().replace(' ', '_')}.json"
        filepath = CAMPAIGNS_DIR / filename
        with open(filepath, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
        return filepath

    @classmethod
    def load(cls, filepath: Path) -> "Campaign":
        with open(filepath) as f:
            return cls.from_dict(json.load(f))

    def add_message(self, role: str, content: str):
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })

    def get_context(self, limit: int = 20) -> str:
        """Get recent history for AI context."""
        recent = self.history[-limit:]
        lines = []
        for entry in recent:
            role = "DM" if entry["role"] == "dm" else "Player"
            lines.append(f"{role}: {entry['content']}")
        return "\n".join(lines)


class DiceRollScreen(ModalScreen):
    """Modal for dice rolling."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, result: str):
        super().__init__()
        self.result = result

    def compose(self) -> ComposeResult:
        yield Container(
            Static(self.result, id="dice-result"),
            Button("Close", id="close-btn", variant="primary"),
            id="dice-modal"
        )

    def on_button_pressed(self, event: Button.Pressed):
        self.dismiss()


class CharacterScreen(ModalScreen):
    """Character creation/editing screen."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def __init__(self, character: Optional[Character] = None, system: str = "cyberpunk2020"):
        super().__init__()
        self.character = character or Character(system=system)
        self.system = system

    def compose(self) -> ComposeResult:
        system_info = GAME_SYSTEMS.get(self.system, GAME_SYSTEMS["cyberpunk2020"])

        with Container(id="char-modal"):
            yield Static(f"[cyan]Character - {system_info['name']}[/]", id="char-title")

            with Horizontal():
                yield Label("Name:")
                yield Input(self.character.name, id="char-name", placeholder="Name")

            with Horizontal():
                yield Label("Role:")
                yield Select(
                    [(r, r) for r in system_info["roles"]],
                    id="char-role",
                    value=self.character.role or system_info["roles"][0]
                )

            with Horizontal():
                yield Label("Lvl:")
                yield Input(str(self.character.level), id="char-level", placeholder="1")
                yield Label("HP:")
                yield Input(str(self.character.hp), id="char-hp", placeholder="0")
                yield Label("/")
                yield Input(str(self.character.max_hp), id="char-maxhp", placeholder="0")

            yield Label("Stats (STAT:VAL per line):")
            default_stats = "\n".join(f"{s}:" for s in system_info["stats"])
            current_stats = "\n".join(f"{k}:{v}" for k, v in self.character.stats.items()) or default_stats
            yield TextArea(current_stats, id="char-stats")

            with Horizontal(id="char-buttons"):
                yield Button("Save", id="save-char", variant="success")
                yield Button("Rand", id="random-stats", variant="warning")
                yield Button("X", id="cancel-char", variant="error")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-char":
            self.dismiss(None)
        elif event.button.id == "random-stats":
            self._random_stats()
        elif event.button.id == "save-char":
            self._save_character()

    def _random_stats(self):
        system_info = GAME_SYSTEMS.get(self.system, GAME_SYSTEMS["cyberpunk2020"])
        stats_area = self.query_one("#char-stats", TextArea)

        if self.system == "dnd5e":
            # 4d6 drop lowest
            lines = []
            for stat in system_info["stats"]:
                rolls = sorted([random.randint(1, 6) for _ in range(4)], reverse=True)[:3]
                lines.append(f"{stat}:{sum(rolls)}")
            stats_area.text = "\n".join(lines)
        else:
            # Cyberpunk: 2-10 range
            lines = []
            for stat in system_info["stats"]:
                lines.append(f"{stat}:{random.randint(2, 10)}")
            stats_area.text = "\n".join(lines)

    def _save_character(self):
        name_input = self.query_one("#char-name", Input)
        role_select = self.query_one("#char-role", Select)
        level_input = self.query_one("#char-level", Input)
        hp_input = self.query_one("#char-hp", Input)
        maxhp_input = self.query_one("#char-maxhp", Input)
        stats_area = self.query_one("#char-stats", TextArea)

        self.character.name = name_input.value or "Unnamed"
        self.character.role = str(role_select.value) if role_select.value else ""
        self.character.level = int(level_input.value or 1)
        self.character.hp = int(hp_input.value or 0)
        self.character.max_hp = int(maxhp_input.value or 0)
        self.character.system = self.system

        # Parse stats
        self.character.stats = {}
        for line in stats_area.text.strip().split("\n"):
            if ":" in line:
                key, val = line.split(":", 1)
                try:
                    self.character.stats[key.strip().upper()] = int(val.strip())
                except ValueError:
                    pass

        self.character.save()
        self.dismiss(self.character)


class NewCampaignScreen(ModalScreen):
    """Screen for creating a new campaign."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="new-campaign-modal"):
            yield Static("[bold cyan]New Campaign[/]", id="nc-title")

            yield Label("Campaign Name:")
            yield Input(id="campaign-name", placeholder="Enter campaign name")

            yield Label("Game System:")
            yield Select(
                [(info["name"], key) for key, info in GAME_SYSTEMS.items()],
                id="game-system",
                value="cyberpunk2020"
            )

            yield Label("Starting Location:")
            yield Input(id="start-location", placeholder="Where does the story begin?")

            with Horizontal(id="nc-buttons"):
                yield Button("Create", id="create-campaign", variant="success")
                yield Button("Cancel", id="cancel-campaign", variant="error")

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "cancel-campaign":
            self.dismiss(None)
        elif event.button.id == "create-campaign":
            name = self.query_one("#campaign-name", Input).value
            system = self.query_one("#game-system", Select).value
            location = self.query_one("#start-location", Input).value

            if name:
                campaign = Campaign(name, str(system))
                campaign.location = location or "Unknown"
                campaign.save()
                self.dismiss(campaign)
            else:
                self.notify("Please enter a campaign name", severity="error")


class AIDM(App):
    """AI Dungeon Master Application."""

    CSS = """
    Screen {
        background: $surface;
    }

    #main-container {
        height: 100%;
        width: 100%;
    }

    #game-log {
        height: 1fr;
        width: 100%;
        border: solid $primary;
        background: $surface-darken-1;
        padding: 0 1;
        scrollbar-gutter: stable;
    }

    #player-input {
        width: 100%;
    }

    #status-bar {
        height: 1;
        background: $surface-darken-2;
        padding: 0 1;
    }

    .status-item {
        margin-right: 1;
    }

    /* Compact modal styles for 800x480 */
    #dice-modal, #char-modal, #new-campaign-modal {
        align: center middle;
        width: 95%;
        height: auto;
        max-height: 95%;
        background: $surface;
        border: solid $primary;
        padding: 1;
    }

    #dice-result {
        text-align: center;
        padding: 1;
        text-style: bold;
    }

    #char-form {
        height: auto;
    }

    #char-left, #char-right {
        width: 50%;
        padding: 0;
    }

    #char-stats {
        height: 8;
    }

    #char-buttons, #nc-buttons {
        align: center middle;
        height: 3;
    }

    Button {
        margin: 0 1;
    }

    Label {
        height: auto;
        padding: 0;
        margin: 0;
    }

    Input {
        height: auto;
        min-height: 3;
    }

    Select {
        height: auto;
    }

    TextArea {
        height: 8;
    }

    /* Command autocomplete dropdown */
    #cmd-suggestions {
        width: 100%;
        height: auto;
        max-height: 6;
        background: $surface-darken-1;
        border: solid $accent;
        padding: 0 1;
    }

    #cmd-suggestions.hidden {
        display: none;
    }

    #input-wrapper {
        height: auto;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "roll_dice", "Roll Dice"),
        Binding("c", "character", "Character"),
        Binding("n", "new_campaign", "New Campaign"),
        Binding("l", "load_campaign", "Load Campaign"),
        Binding("s", "save_campaign", "Save"),
        Binding("h", "show_help", "Help"),
        Binding("ctrl+l", "clear_log", "Clear"),
    ]

    def __init__(self):
        super().__init__()
        self.campaign: Optional[Campaign] = None
        self.character: Optional[Character] = None
        self.system = "cyberpunk2020"
        self._campaign_list: list[Path] = []
        self._character_list: list[Path] = []
        self._pending_selection: Optional[str] = None  # "campaign" or "character"
        self._suggestions_visible = False
        self._filtered_commands: list[tuple[str, str]] = []
        self._selected_idx = 0
        ensure_dirs()

    def compose(self) -> ComposeResult:
        with Container(id="main-container"):
            yield RichLog(id="game-log", highlight=True, markup=True, wrap=True, auto_scroll=True)

            with Container(id="input-wrapper"):
                yield Static("", id="cmd-suggestions", classes="hidden")
                yield Input(id="player-input", placeholder="> action or /cmd")

            with Horizontal(id="status-bar"):
                yield Static("[dim]No Campaign[/]", id="campaign-status", classes="status-item")
                yield Static("", id="char-status", classes="status-item")
                yield Static("", id="hp-status", classes="status-item")

    def on_mount(self):
        self.title = "AI Dungeon Master"
        self.sub_title = "Cyberpunk 2020 / D&D 5e"

        log = self.query_one("#game-log", RichLog)
        log.write("[bold cyan]AI Dungeon Master[/] - Cyberpunk 2020 / D&D 5e")
        log.write("[yellow]/new[/] campaign | [yellow]/char[/] create | [yellow]/help[/] commands")
        log.write(f"[dim]{random.choice(CYBERPUNK_QUOTES)}[/]")

    def _update_status(self):
        """Update status bar."""
        campaign_label = self.query_one("#campaign-status", Static)
        char_label = self.query_one("#char-status", Static)
        hp_label = self.query_one("#hp-status", Static)

        if self.campaign:
            campaign_label.update(f"[cyan]{self.campaign.name}[/]")
        else:
            campaign_label.update("[dim]No Campaign[/]")

        if self.character:
            char_label.update(f"[green]{self.character.name}[/]")
            hp_label.update(f"[red]{self.character.hp}/{self.character.max_hp}[/]")
        else:
            char_label.update("")
            hp_label.update("")

    def _update_suggestions(self, text: str):
        """Update command suggestions based on input."""
        try:
            if not text.startswith("/"):
                self._hide_suggestions()
                return

            # Filter commands matching input
            query = text.lower()
            self._filtered_commands = [
                (cmd, desc) for cmd, desc in COMMANDS
                if cmd.startswith(query)
            ]

            if not self._filtered_commands:
                self._hide_suggestions()
                return

            # Update Static with matches
            suggestions = self.query_one("#cmd-suggestions", Static)
            lines = []
            for i, (cmd, desc) in enumerate(self._filtered_commands[:6]):
                marker = ">" if i == self._selected_idx else " "
                lines.append(f"{marker} [cyan]{cmd}[/] [dim]{desc}[/]")
            suggestions.update("\n".join(lines))
            self._show_suggestions()
        except Exception:
            self._hide_suggestions()

    def _show_suggestions(self):
        """Show the suggestions dropdown."""
        if not self._suggestions_visible:
            try:
                suggestions = self.query_one("#cmd-suggestions", Static)
                suggestions.remove_class("hidden")
                self._suggestions_visible = True
            except Exception:
                pass

    def _hide_suggestions(self):
        """Hide the suggestions dropdown."""
        if self._suggestions_visible:
            try:
                suggestions = self.query_one("#cmd-suggestions", Static)
                suggestions.add_class("hidden")
                suggestions.update("")
                self._suggestions_visible = False
                self._filtered_commands = []
                self._selected_idx = 0
            except Exception:
                pass

    def on_input_changed(self, event: Input.Changed):
        """Handle input changes for autocomplete."""
        try:
            if event.input.id == "player-input":
                self._update_suggestions(event.value)
        except Exception:
            pass

    def on_key(self, event) -> None:
        """Handle key events for autocomplete navigation."""
        # Only handle keys when suggestions are visible
        if not self._suggestions_visible or not self._filtered_commands:
            return

        # Only handle specific keys for autocomplete
        if event.key not in ("down", "up", "tab", "escape"):
            return

        try:
            player_input = self.query_one("#player-input", Input)
            max_idx = min(len(self._filtered_commands), 6) - 1

            if event.key == "down":
                if self._selected_idx < max_idx:
                    self._selected_idx += 1
                    self._update_suggestions(player_input.value)
                event.prevent_default()
                event.stop()
            elif event.key == "up":
                if self._selected_idx > 0:
                    self._selected_idx -= 1
                    self._update_suggestions(player_input.value)
                event.prevent_default()
                event.stop()
            elif event.key == "tab":
                # Complete the command
                cmd, _ = self._filtered_commands[self._selected_idx]
                player_input.value = cmd + " "
                player_input.cursor_position = len(player_input.value)
                self._hide_suggestions()
                event.prevent_default()
                event.stop()
            elif event.key == "escape":
                self._hide_suggestions()
                event.prevent_default()
                event.stop()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted):
        """Handle player input."""
        try:
            # Hide suggestions on submit
            self._hide_suggestions()

            text = event.value.strip()
            if not text:
                return

            event.input.value = ""
            log = self.query_one("#game-log", RichLog)

            # Handle pending selections (campaign/character by number)
            if self._pending_selection and text.isdigit():
                num = int(text) - 1
                if self._pending_selection == "campaign" and 0 <= num < len(self._campaign_list):
                    await self._select_campaign(num)
                    return
                elif self._pending_selection == "character" and 0 <= num < len(self._character_list):
                    await self._select_character(num)
                    return
                else:
                    log.write(f"[red]Invalid selection: {text}[/]")
                    self._pending_selection = None
                    return

            # Clear pending selection on any other input
            self._pending_selection = None

            # Handle commands
            if text.startswith("/"):
                await self._handle_command(text)
                return

            # Regular game input
            if not self.campaign:
                log.write("[red]No campaign loaded. Use /new or /load first.[/]")
                return

            # Log player action
            log.write(f"\n[bold green]> {text}[/]")
            self.campaign.add_message("player", text)

            # Get AI response (worker, don't await)
            self._get_dm_response(text)
        except Exception as e:
            try:
                log = self.query_one("#game-log", RichLog)
                log.write(f"[red]Error: {e}[/]")
            except:
                pass

    async def _handle_command(self, cmd: str):
        """Handle slash commands."""
        log = self.query_one("#game-log", RichLog)
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if command == "/new":
            self.action_new_campaign()

        elif command == "/load":
            await self._load_campaign_list()

        elif command == "/char":
            self.action_character()

        elif command == "/roll":
            notation = args or ("d10" if self.system == "cyberpunk2020" else "d20")
            total, rolls, desc = roll_dice(notation)
            log.write(f"\n[bold magenta]🎲 {desc}[/]")
            if self.campaign:
                self.campaign.add_message("system", f"Dice roll: {desc}")

        elif command == "/look":
            if self.campaign:
                self._get_dm_response("I look around and observe my surroundings carefully.")
            else:
                log.write("[red]No campaign loaded.[/]")

        elif command == "/inventory":
            if self.character:
                inv = self.character.inventory or ["Empty"]
                log.write(f"\n[cyan]Inventory:[/] {', '.join(inv)}")
                if self.character.cyberware:
                    log.write(f"[cyan]Cyberware:[/] {', '.join(self.character.cyberware)}")
                if self.character.spells:
                    log.write(f"[cyan]Spells:[/] {', '.join(self.character.spells)}")
            else:
                log.write("[red]No character loaded.[/]")

        elif command == "/stats":
            if self.character:
                log.write(f"\n[cyan]{self.character.summary()}[/]")
            else:
                log.write("[red]No character loaded.[/]")

        elif command == "/save":
            self.action_save_campaign()

        elif command == "/help":
            self._show_help()

        elif command == "/clear":
            log.clear()

        elif command == "/system":
            if args in GAME_SYSTEMS:
                self.system = args
                log.write(f"[cyan]Switched to {GAME_SYSTEMS[args]['name']}[/]")
            else:
                log.write(f"[cyan]Available systems: {', '.join(GAME_SYSTEMS.keys())}[/]")

        elif command == "/quote":
            quotes = CYBERPUNK_QUOTES if self.system == "cyberpunk2020" else DND_QUOTES
            log.write(f"\n[dim italic]{random.choice(quotes)}[/]")

        elif command == "/loadchar":
            await self._load_character_list()

        # Inventory management
        elif command == "/additem":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /additem <item name>[/]")
            else:
                self.character.inventory.append(args)
                self.character.save()
                log.write(f"[green]Added to inventory:[/] {args}")

        elif command == "/rmitem":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /rmitem <item name>[/]")
            elif args in self.character.inventory:
                self.character.inventory.remove(args)
                self.character.save()
                log.write(f"[yellow]Removed from inventory:[/] {args}")
            else:
                log.write(f"[red]Item not found:[/] {args}")

        # Cyberware management (Cyberpunk)
        elif command == "/addcyber":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /addcyber <cyberware name>[/]")
            else:
                self.character.cyberware.append(args)
                self.character.save()
                log.write(f"[cyan]Installed cyberware:[/] {args}")

        elif command == "/rmcyber":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /rmcyber <cyberware name>[/]")
            elif args in self.character.cyberware:
                self.character.cyberware.remove(args)
                self.character.save()
                log.write(f"[yellow]Removed cyberware:[/] {args}")
            else:
                log.write(f"[red]Cyberware not found:[/] {args}")

        # Spell management (D&D)
        elif command == "/addspell":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /addspell <spell name>[/]")
            else:
                self.character.spells.append(args)
                self.character.save()
                log.write(f"[magenta]Learned spell:[/] {args}")

        elif command == "/rmspell":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /rmspell <spell name>[/]")
            elif args in self.character.spells:
                self.character.spells.remove(args)
                self.character.save()
                log.write(f"[yellow]Forgot spell:[/] {args}")
            else:
                log.write(f"[red]Spell not found:[/] {args}")

        # NPC management
        elif command == "/npcs":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not self.campaign.npcs:
                log.write("[dim]No NPCs recorded yet.[/]")
            else:
                log.write("\n[cyan]Known NPCs:[/]")
                for npc in self.campaign.npcs:
                    log.write(f"  • {npc}")

        elif command == "/addnpc":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /addnpc <name - description>[/]")
            else:
                self.campaign.npcs.append(args)
                self.campaign.save()
                log.write(f"[green]NPC added:[/] {args}")

        elif command == "/rmnpc":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /rmnpc <name>[/]")
            else:
                # Match by start of string for convenience
                removed = None
                for npc in self.campaign.npcs:
                    if npc.lower().startswith(args.lower()):
                        removed = npc
                        break
                if removed:
                    self.campaign.npcs.remove(removed)
                    self.campaign.save()
                    log.write(f"[yellow]NPC removed:[/] {removed}")
                else:
                    log.write(f"[red]NPC not found:[/] {args}")

        # Quest management
        elif command == "/quests":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not self.campaign.quests:
                log.write("[dim]No active quests.[/]")
            else:
                log.write("\n[cyan]Active Quests:[/]")
                for i, quest in enumerate(self.campaign.quests, 1):
                    log.write(f"  {i}. {quest}")

        elif command == "/addquest":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /addquest <quest description>[/]")
            else:
                self.campaign.quests.append(args)
                self.campaign.save()
                log.write(f"[green]Quest added:[/] {args}")

        elif command == "/rmquest":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not args:
                log.write("[yellow]Usage: /rmquest <number or text>[/]")
            else:
                removed = None
                # Try by number first
                if args.isdigit():
                    idx = int(args) - 1
                    if 0 <= idx < len(self.campaign.quests):
                        removed = self.campaign.quests.pop(idx)
                else:
                    # Match by text
                    for quest in self.campaign.quests:
                        if args.lower() in quest.lower():
                            removed = quest
                            break
                    if removed:
                        self.campaign.quests.remove(removed)
                if removed:
                    self.campaign.save()
                    log.write(f"[yellow]Quest completed/removed:[/] {removed}")
                else:
                    log.write(f"[red]Quest not found:[/] {args}")

        # Location management
        elif command == "/location":
            if not self.campaign:
                log.write("[red]No campaign loaded.[/]")
            elif not args:
                log.write(f"[cyan]Current location:[/] {self.campaign.location or 'Unknown'}")
            else:
                self.campaign.location = args
                self.campaign.save()
                log.write(f"[cyan]Location updated:[/] {args}")

        # HP management
        elif command == "/hp":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                log.write(f"[red]HP:[/] {self.character.hp}/{self.character.max_hp}")
            else:
                try:
                    if args.startswith("+"):
                        self.character.hp = min(self.character.max_hp, self.character.hp + int(args[1:]))
                    elif args.startswith("-"):
                        self.character.hp = max(0, self.character.hp - int(args[1:]))
                    else:
                        self.character.hp = int(args)
                    self.character.save()
                    self._update_status()
                    log.write(f"[red]HP:[/] {self.character.hp}/{self.character.max_hp}")
                except ValueError:
                    log.write("[yellow]Usage: /hp <value> or /hp +/-<amount>[/]")

        # Money management
        elif command == "/money":
            if not self.character:
                log.write("[red]No character loaded.[/]")
            elif not args:
                currency = "eb" if self.system == "cyberpunk2020" else "gp"
                log.write(f"[yellow]Money:[/] {self.character.money} {currency}")
            else:
                try:
                    if args.startswith("+"):
                        self.character.money += int(args[1:])
                    elif args.startswith("-"):
                        self.character.money = max(0, self.character.money - int(args[1:]))
                    else:
                        self.character.money = int(args)
                    self.character.save()
                    currency = "eb" if self.system == "cyberpunk2020" else "gp"
                    log.write(f"[yellow]Money:[/] {self.character.money} {currency}")
                except ValueError:
                    log.write("[yellow]Usage: /money <value> or /money +/-<amount>[/]")

        else:
            log.write(f"[red]Unknown command: {command}[/]")

    async def _load_campaign_list(self):
        """Show list of campaigns to load."""
        log = self.query_one("#game-log", RichLog)
        campaigns = list(CAMPAIGNS_DIR.glob("*.json"))

        if not campaigns:
            log.write("[yellow]No saved campaigns found. Use /new to create one.[/]")
            return

        log.write("\n[cyan]Available Campaigns:[/]")
        valid_campaigns = []
        for path in campaigns:
            try:
                camp = Campaign.load(path)
                system_info = GAME_SYSTEMS.get(camp.system, {})
                valid_campaigns.append(path)
                log.write(f"  {len(valid_campaigns)}. [green]{camp.name}[/] ({system_info.get('name', '')}) - {camp.location}")
            except:
                continue

        log.write("\n[dim]Type campaign number to load, or /new for new campaign[/]")

        # Store for selection
        self._campaign_list = valid_campaigns
        self._pending_selection = "campaign"

    async def _select_campaign(self, index: int):
        """Load a campaign by index."""
        log = self.query_one("#game-log", RichLog)
        self._pending_selection = None

        try:
            path = self._campaign_list[index]
            self.campaign = Campaign.load(path)
            self.system = self.campaign.system
            self._update_status()
            log.write(f"\n[cyan]Campaign loaded: {self.campaign.name}[/]")
            log.write(f"[yellow]Location: {self.campaign.location}[/]")
            if self.campaign.history:
                log.write(f"[dim]Session {self.campaign.session_count}, {len(self.campaign.history)} events in history[/]")
        except Exception as e:
            log.write(f"[red]Failed to load campaign: {e}[/]")

    async def _load_character_list(self):
        """Show list of characters to load."""
        log = self.query_one("#game-log", RichLog)
        characters = list(CHARACTERS_DIR.glob("*.json"))

        if not characters:
            log.write("[yellow]No saved characters found. Use /char to create one.[/]")
            return

        log.write("\n[cyan]Available Characters:[/]")
        valid_chars = []
        for path in characters:
            try:
                char = Character.load(path)
                system_info = GAME_SYSTEMS.get(char.system, {})
                valid_chars.append(path)
                log.write(f"  {len(valid_chars)}. [green]{char.name}[/] - {char.role} ({system_info.get('name', '')})")
            except:
                continue

        log.write("\n[dim]Type character number to load, or /char for new character[/]")

        self._character_list = valid_chars
        self._pending_selection = "character"

    async def _select_character(self, index: int):
        """Load a character by index."""
        log = self.query_one("#game-log", RichLog)
        self._pending_selection = None

        try:
            path = self._character_list[index]
            self.character = Character.load(path)
            self._update_status()
            log.write(f"\n[cyan]Character loaded: {self.character.name}[/]")
            log.write(f"[dim]{self.character.role} - HP: {self.character.hp}/{self.character.max_hp}[/]")
        except Exception as e:
            log.write(f"[red]Failed to load character: {e}[/]")

    def _show_help(self):
        """Show help."""
        log = self.query_one("#game-log", RichLog)
        log.write("[bold cyan]── Campaign ──[/]")
        log.write("  /new /load /save /location <place>")
        log.write("[bold cyan]── Character ──[/]")
        log.write("  /char /loadchar /stats /hp +/-N /money +/-N")
        log.write("[bold cyan]── Inventory ──[/]")
        log.write("  /inventory /additem /rmitem /addcyber /rmcyber /addspell /rmspell")
        log.write("[bold cyan]── World ──[/]")
        log.write("  /npcs /addnpc /rmnpc /quests /addquest /rmquest")
        log.write("[bold cyan]── Game ──[/]")
        log.write("  /roll <dice> /look /system /quote /clear")
        log.write("[bold cyan]── Keys ──[/]")
        log.write("  r=roll c=char n=new l=load s=save q=quit")
        log.write("[dim]Type actions naturally. AI DM responds.[/]")

    @work(exclusive=True)
    async def _get_dm_response(self, player_input: str):
        """Get AI DM response with streaming."""
        log = self.query_one("#game-log", RichLog)

        if not self.campaign:
            return

        system_info = GAME_SYSTEMS.get(self.campaign.system, GAME_SYSTEMS["cyberpunk2020"])

        # Build context
        char_context = self.character.summary() if self.character else "No character sheet."
        history_context = self.campaign.get_context(limit=10)

        # Include NPCs and quests in context for better continuity
        npc_context = f"Known NPCs: {', '.join(self.campaign.npcs[:10])}" if self.campaign.npcs else ""
        quest_context = f"Active quests: {', '.join(self.campaign.quests[:5])}" if self.campaign.quests else ""

        prompt = f"""You are an expert Game Master for {system_info['name']}.

SETTING: {system_info['setting']}

CURRENT LOCATION: {self.campaign.location or 'Unknown'}
{npc_context}
{quest_context}

PLAYER CHARACTER:
{char_context}

RECENT HISTORY:
{history_context}

PLAYER ACTION: {player_input}

Respond as the DM. Describe what happens, include NPC dialogue if relevant, and present choices or consequences. Be vivid and atmospheric. Keep response under 200 words. If combat or skill checks are needed, tell the player what to roll.

DM RESPONSE:"""

        log.write("[dim]The DM speaks...[/]")

        try:
            import httpx
            full_response = ""
            buffer = ""
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": True,
                        "options": {
                            "temperature": 0.8,
                            "num_predict": 400,
                        }
                    }
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                token = data.get("response", "")
                                if token:
                                    full_response += token
                                    buffer += token
                                    # Write sentences as they complete for progressive display
                                    if any(p in buffer for p in '.!?\n'):
                                        # Find last sentence boundary
                                        last_break = max(
                                            buffer.rfind('.'),
                                            buffer.rfind('!'),
                                            buffer.rfind('?'),
                                            buffer.rfind('\n')
                                        )
                                        if last_break > 0:
                                            to_write = buffer[:last_break + 1].strip()
                                            if to_write:
                                                log.write(f"[bold yellow]{wrap_text(to_write)}[/]")
                                            buffer = buffer[last_break + 1:]
                            except json.JSONDecodeError:
                                pass

            # Write any remaining text
            if buffer.strip():
                log.write(f"[bold yellow]{wrap_text(buffer.strip())}[/]")

            # Save to campaign
            self.campaign.add_message("dm", full_response.strip())
            self.campaign.save()

        except Exception as e:
            error_msg = str(e) if str(e) else type(e).__name__
            log.write(f"[red]DM Error: {error_msg}[/]")
            log.write("[dim]Tip: Make sure Ollama is running with phi3:mini[/]")

    def action_roll_dice(self):
        """Quick dice roll based on system."""
        notation = "d10" if self.system == "cyberpunk2020" else "d20"
        total, rolls, desc = roll_dice(notation)

        log = self.query_one("#game-log", RichLog)
        log.write(f"\n[bold magenta]🎲 {desc}[/]")

        if self.campaign:
            self.campaign.add_message("system", f"Dice roll: {desc}")

    def action_character(self):
        """Open character screen."""
        def on_dismiss(char: Optional[Character]):
            if char:
                self.character = char
                self._update_status()
                log = self.query_one("#game-log", RichLog)
                log.write(f"\n[cyan]Character loaded: {char.name}[/]")

        self.push_screen(
            CharacterScreen(self.character, self.system),
            on_dismiss
        )

    def action_new_campaign(self):
        """Create new campaign."""
        def on_dismiss(campaign: Optional[Campaign]):
            if campaign:
                self.campaign = campaign
                self.system = campaign.system
                self._update_status()
                log = self.query_one("#game-log", RichLog)
                log.write(f"\n[cyan]Campaign created: {campaign.name}[/]")
                log.write(f"[yellow]Location: {campaign.location}[/]")

                # Get opening scene
                self._get_opening_scene()

        self.push_screen(NewCampaignScreen(), on_dismiss)

    @work(exclusive=True)
    async def _get_opening_scene(self):
        """Generate opening scene for new campaign with streaming."""
        if not self.campaign:
            return

        log = self.query_one("#game-log", RichLog)
        system_info = GAME_SYSTEMS.get(self.campaign.system, {})

        prompt = f"""You are an expert Game Master for {system_info['name']}.

SETTING: {system_info['setting']}

Create an atmospheric opening scene for a new campaign starting in: {self.campaign.location}

Set the mood, describe the environment, and end with a hook that draws the player in. Keep it under 150 words.

OPENING SCENE:"""

        log.write("\n[dim]The story begins...[/]")

        try:
            import httpx
            full_response = ""
            buffer = ""
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_URL}/api/generate",
                    json={
                        "model": OLLAMA_MODEL,
                        "prompt": prompt,
                        "stream": True,
                        "options": {"temperature": 0.9, "num_predict": 300}
                    }
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                token = data.get("response", "")
                                if token:
                                    full_response += token
                                    buffer += token
                                    # Write sentences as they complete
                                    if any(p in buffer for p in '.!?\n'):
                                        last_break = max(
                                            buffer.rfind('.'),
                                            buffer.rfind('!'),
                                            buffer.rfind('?'),
                                            buffer.rfind('\n')
                                        )
                                        if last_break > 0:
                                            to_write = buffer[:last_break + 1].strip()
                                            if to_write:
                                                log.write(f"[bold yellow]{wrap_text(to_write)}[/]")
                                            buffer = buffer[last_break + 1:]
                            except json.JSONDecodeError:
                                pass

            # Write remaining text
            if buffer.strip():
                log.write(f"[bold yellow]{wrap_text(buffer.strip())}[/]")

            self.campaign.add_message("dm", full_response.strip())
            self.campaign.session_count = 1
            self.campaign.save()

        except Exception as e:
            log.write(f"\n[red]Could not generate opening: {e}[/]")
            log.write("[yellow]The DM awaits your first action...[/]")

    def action_load_campaign(self):
        """Load a campaign."""
        # Trigger load list
        self.call_later(lambda: asyncio.create_task(self._load_campaign_list()))

    def action_save_campaign(self):
        """Save current campaign."""
        log = self.query_one("#game-log", RichLog)
        if self.campaign:
            path = self.campaign.save()
            log.write(f"\n[cyan]Campaign saved: {path}[/]")
        else:
            log.write("[red]No campaign to save.[/]")

    def action_show_help(self):
        self._show_help()

    def action_clear_log(self):
        log = self.query_one("#game-log", RichLog)
        log.clear()


def main():
    # Install httpx if needed
    try:
        import httpx
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "httpx"],
                      capture_output=True)

    app = AIDM()
    app.run()


if __name__ == "__main__":
    main()
