# NetRunner v4.0 Improvement Plan

**Document Version:** 1.1
**Created:** 2026-01-27
**Updated:** 2026-01-27
**Target:** NetRunner network toolkit for Cyberboy handheld
**Current State:** v3.2, ~5800 lines Python, 16 modules, Textual TUI
**Repository:** `~/netrunner-v4/` (new git repo, separate from ~/customization/)

---

## Executive Summary

This plan outlines a phased approach to improving NetRunner's functionality, UI/UX, and code architecture. The implementation will be orchestrated by AI agents with strict context management (30% context limit per agent session) to ensure code quality and prevent degradation.

**Important:** All phases are executed sequentially. No parallelization of phases or tasks unless explicitly marked as parallel-safe within a phase.

---

## Phase Overview

| Phase | Focus | Priority | Tasks |
|-------|-------|----------|-------|
| 0 | Infrastructure & Testing Setup | Critical | 10 |
| 1 | Quick Wins & Foundation | High | 8 |
| 2 | Core UX Improvements | High | 7 |
| 3 | Data Persistence & History | Medium | 7 |
| 4 | Advanced Features | Medium | 9 |
| 5 | Architecture Refactor | Low | 5 |
| 6 | Polish & Documentation | Low | 5 |

**Total Tasks:** 51

**Execution Model:** Sequential only. Complete each task fully before starting the next. No parallel task execution.

---

## Phase 0: Infrastructure & Testing Setup

**Goal:** Establish testing framework, tooling, and CI patterns before making changes.

### Task 0.1: Initialize Repository Structure
```
~/netrunner-v4/
├── netrunner.py             # Copy from ~/customization/
├── netrunner.tcss           # Copy from ~/customization/
├── requirements.txt         # Dependencies
├── pyproject.toml           # Project config (ruff, pytest)
├── tests/
│   ├── __init__.py
│   ├── conftest.py          # pytest fixtures
│   ├── test_utils.py        # Unit tests for utility functions
│   ├── test_modules/
│   │   ├── test_scanner.py
│   │   ├── test_dns.py
│   │   └── ...
│   └── test_integration.py  # Full app integration tests
└── docs/
    └── ARCHITECTURE.md
```

**Actions:**
- Copy source files from ~/customization/ to ~/netrunner-v4/
- Initialize git repo (already done)
- Create directory structure
- Create initial commit

### Task 0.2: Write Unit Tests for Existing Utilities
**File:** `tests/test_utils.py`
- `test_get_local_ip()` - Mock socket, verify IP format
- `test_get_default_gateway()` - Mock subprocess, verify parsing
- `test_get_network_cidr()` - Various IP inputs
- `test_lookup_mac_vendor()` - Known MACs, unknown MACs, malformed
- `test_parse_version()` - Various version strings (7.4p1, 2.4.49, 1.0)
- `test_lookup_cves()` - Known vulnerable versions, safe versions
- `test_calculate_subnet()` - Valid CIDR, invalid input, edge cases
- `test_create_wol_packet()` - Valid MAC, invalid MAC
- `test_wrap_text()` - Long lines, short lines, empty string

### Task 0.3: Create Module Test Fixtures
**File:** `tests/conftest.py`
```python
# Fixtures needed:
- mock_nmap_output
- mock_arp_scan_output
- mock_dns_response
- mock_ssl_cert
- mock_wifi_scan
- mock_speedtest_result
- sample_packet_capture
```

### Task 0.4: Write Integration Test Harness
**File:** `tests/test_integration.py`
- Test app launches without error
- Test each module tab can be activated
- Test keyboard navigation works
- Test help screen opens/closes

### Task 0.5: Create Test Runner Script
**File:** `~/netrunner-v4/run_tests.sh`
```bash
#!/bin/bash
cd ~/netrunner-v4
python -m pytest tests/ -v --tb=short
```

### Task 0.6: Verify Source Preservation
**Action:** Confirm original v3.2 source is preserved in ~/customization/
```bash
# Verify originals exist and are readable
ls -la ~/customization/netrunner.py ~/customization/netrunner.tcss

# Note: No backup copies needed - originals remain untouched in ~/customization/
# All development happens in ~/netrunner-v4/ (new git repo)
```

### Task 0.7: Create Development Branch Strategy
- `main` - stable releases
- `dev` - integration branch
- `feature/*` - individual features

### Task 0.8: Document Current Module Structure
Create `docs/ARCHITECTURE.md` documenting:
- Module class hierarchy
- Event flow
- CSS class conventions
- Data flow patterns

### Task 0.9: Verify External Tool Dependencies
**File:** `tools_check.py` (utility script)
**Required Tools:**
| Tool | Min Version | Purpose |
|------|-------------|---------|
| nmap | 7.80 | Network scanning |
| tcpdump | 4.9 | Packet capture |
| wl-copy | 2.0 | Clipboard (Wayland) |
| hostapd | 2.9 | RogueAP |
| dnsmasq | 2.80 | RogueAP DNS |
| arp-scan | 1.9 | ARP scanning |
| speedtest-cli | 2.1 | Speed tests |
| nmcli | 1.0 | WiFi management |

**Actions:**
- Create script to verify all tools present
- Check version compatibility
- Report missing/outdated tools
- Document installation commands for missing tools

### Task 0.10: Setup Linting and Formatting
**File:** `pyproject.toml`
**Tools:** ruff (linting + formatting)
```toml
[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "C4", "SIM"]
ignore = ["E501"]  # Line length handled separately

[tool.ruff.format]
quote-style = "double"
```

**Actions:**
- Configure ruff in pyproject.toml
- Run initial lint check (report only, don't fix)
- Document existing lint issues for later cleanup
- Do NOT auto-fix yet (prevents unintended changes)

---

## Phase 1: Quick Wins & Foundation

**Goal:** High-impact improvements plus foundational systems needed by later phases.

### Task 1.1: Configuration Management System
**File:** `netrunner_config.py` (new)
**Rationale:** Many later features (history, profiles, themes) need config storage. Establishing this early prevents inconsistent approaches.

**Schema:**
```python
DEFAULT_CONFIG = {
    "version": "4.0",
    "general": {
        "sounds_enabled": True,
        "theme": "cyberpunk",
        "save_directory": "~/netrunner-results/"
    },
    "history": {
        "max_targets": 20,
        "max_scans": 1000
    },
    "scanner": {
        "default_ports": "1-1000",
        "timeout": 30
    },
    "ui": {
        "compact_mode": False,
        "vim_keys": True
    }
}
```

**Features:**
- Config file: `~/.config/netrunner/config.json`
- Schema validation with defaults
- Migration support for version upgrades
- Thread-safe read/write
- CLI: `netrunner --config` to edit

**Tests:**
- `test_config_load_creates_default()`
- `test_config_save_preserves_values()`
- `test_config_migration_v3_to_v4()`
- `test_config_validation_rejects_invalid()`

### Task 1.2: Error Handling Improvements
**File:** `netrunner.py`
**Goal:** Replace bare try/except blocks with specific exception handling.

**Changes:**
- Audit all try/except blocks
- Replace `except:` and `except Exception:` with specific types
- Add user-friendly error messages
- Log errors to `~/.config/netrunner/error.log`
- Add `--debug` flag for verbose error output

**Common patterns to fix:**
```python
# BAD
try:
    result = subprocess.run(cmd)
except:
    pass

# GOOD
try:
    result = subprocess.run(cmd, timeout=30)
except subprocess.TimeoutExpired:
    self.show_error("Scan timed out after 30 seconds")
except FileNotFoundError:
    self.show_error(f"Tool not found: {cmd[0]}")
except PermissionError:
    self.show_error(f"Permission denied. Try: sudo {' '.join(cmd)}")
```

**Tests:**
- `test_missing_tool_shows_helpful_error()`
- `test_timeout_shows_message()`
- `test_permission_error_suggests_sudo()`

### Task 1.3: Add Vim-style Navigation Keys
**File:** `netrunner.py` lines 6676-6707 (BINDINGS)
**Changes:**
- Add `h` → `tab_prev`
- Add `l` → `tab_next`
- Add `j` → `focus_next`
- Add `k` → `focus_prev`

**Tests:**
- `test_vim_navigation_h_moves_left()`
- `test_vim_navigation_l_moves_right()`
- `test_vim_navigation_jk_moves_focus()`

### Task 1.4: Add Clipboard Support (wl-copy)
**File:** `netrunner.py`
**Changes:**
- Add new function `copy_to_clipboard(text: str)`
- Add keybinding `y` → `copy_selected`
- Copy current line or selected text from results

**Tests:**
- `test_copy_to_clipboard_calls_wlcopy()`
- `test_y_key_copies_result_line()`

### Task 1.5: Increase Touch Target Size
**File:** `netrunner.tcss` lines 539-545
**Changes:**
```css
.sidebar Button {
    height: 2;  /* was 1 */
    min-height: 2;
}
```

**Tests:**
- Visual inspection on device
- Touch accuracy test (manual)

### Task 1.6: Fullscreen Results Toggle
**File:** `netrunner.py`
**Changes:**
- Add keybinding `f` → `toggle_fullscreen_results`
- Add CSS class `.sidebar-hidden` with `display: none`
- Toggle sidebar visibility

**Tests:**
- `test_f_hides_sidebar()`
- `test_f_again_shows_sidebar()`
- `test_fullscreen_results_fill_width()`

### Task 1.7: Last Target Persistence
**File:** `netrunner.py`
**Uses:** Config system from Task 1.1
**Changes:**
- Use config system for history storage
- Save last target on scan
- Load and populate on startup

**Tests:**
- `test_target_saved_after_scan()`
- `test_target_loaded_on_startup()`
- `test_handles_missing_history_file()`

### Task 1.8: Scanning Animation Enhancement
**File:** `netrunner.py`
**Changes:**
- Create `AnimatedStatus` widget
- Cycle through hacker quotes during scan
- Show elapsed time

**Tests:**
- `test_animated_status_cycles_quotes()`
- `test_elapsed_time_updates()`

---

## Phase 2: Core UX Improvements

**Goal:** Significantly improve navigation and results interaction.

### Task 2.1: Result Line Selection & Actions
**File:** `netrunner.py`
**Changes:**
- Track cursor position in results
- Highlight current line
- `Enter` on IP opens action menu
- Actions: Scan, Traceroute, Geo, Copy

**Tests:**
- `test_cursor_movement_in_results()`
- `test_enter_on_ip_shows_menu()`
- `test_action_menu_scan_works()`

### Task 2.2: Search/Filter in Results
**File:** `netrunner.py`
**Changes:**
- Add keybinding `/` → `start_search`
- Show search input overlay
- Filter results to matching lines
- `Esc` clears filter
- `n`/`N` for next/prev match

**Tests:**
- `test_slash_opens_search()`
- `test_search_filters_results()`
- `test_escape_clears_filter()`
- `test_n_jumps_to_next_match()`

### Task 2.3: Tab Groups Visual Indicator
**File:** `netrunner.tcss`
**Changes:**
- Add footer section showing tab groups
- Color-code groups: Recon (cyan), Monitor (green), Attack (red), Tools (yellow)
- Show current group name

**Tests:**
- `test_footer_shows_tab_groups()`
- `test_correct_group_highlighted()`

### Task 2.4: Collapsible Result Sections
**File:** `netrunner.py`
**Changes:**
- Parse results into sections (Hosts, Ports, Services)
- Wrap in `Collapsible` widgets
- Allow expand/collapse with `+`/`-` or click

**Tests:**
- `test_results_grouped_into_sections()`
- `test_section_collapse_toggle()`

### Task 2.5: Recent Targets Dropdown
**File:** `netrunner.py`
**Changes:**
- Store last 20 targets in history
- `Ctrl+R` in target input shows dropdown
- Select to populate input

**Tests:**
- `test_ctrl_r_shows_history()`
- `test_history_limited_to_20()`
- `test_select_history_populates_input()`

### Task 2.6: Quick Jump Navigation
**File:** `netrunner.py`
**Changes:**
- Add keybinding `g` → `start_quick_jump`
- Show overlay "Press 1-0 for tab"
- Direct jump to module

**Tests:**
- `test_g_shows_jump_overlay()`
- `test_g1_jumps_to_scanner()`

### Task 2.7: Compact Mode Toggle
**File:** `netrunner.py`, `netrunner.tcss`
**Changes:**
- Add keybinding `c` → `toggle_compact`
- Hide button text, show only icons/hotkeys
- Reduce sidebar to 8 chars

**Tests:**
- `test_c_enables_compact_mode()`
- `test_compact_sidebar_narrower()`
- `test_buttons_show_only_hotkey()`

---

## Phase 3: Data Persistence & History

**Goal:** Enable scan history, baselines, and data management.

### Task 3.1: SQLite Database Schema with Migration Support
**File:** `netrunner_db.py` (new)
**Rationale:** Include migration support from the start to avoid painful retrofitting when schema changes are needed mid-phase.

**Schema:**
```sql
-- Schema version tracking
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE scans (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    module TEXT,
    target TEXT,
    scan_type TEXT,
    results_json TEXT,
    is_baseline BOOLEAN DEFAULT 0
);

CREATE TABLE targets (
    id INTEGER PRIMARY KEY,
    target TEXT UNIQUE,
    last_scanned DATETIME,
    scan_count INTEGER,
    is_favorite BOOLEAN DEFAULT 0,
    notes TEXT
);

CREATE TABLE alerts (
    id INTEGER PRIMARY KEY,
    timestamp DATETIME,
    scan_id INTEGER,
    alert_type TEXT,
    message TEXT,
    acknowledged BOOLEAN DEFAULT 0
);
```

**Migration System:**
```python
MIGRATIONS = {
    1: "initial_schema.sql",
    2: "add_scan_duration.sql",  # Example future migration
}

def migrate_db(conn):
    """Apply pending migrations."""
    current = get_schema_version(conn)
    for version, migration in MIGRATIONS.items():
        if version > current:
            apply_migration(conn, version, migration)
```

**Tests:**
- `test_database_creation()`
- `test_scan_insert_and_retrieve()`
- `test_target_upsert()`
- `test_migration_applies_in_order()`
- `test_migration_skips_already_applied()`

### Task 3.2: Scan History Storage
**File:** `netrunner.py`
**Changes:**
- After each scan, save to database
- Store raw results as JSON
- Link to target record

**Tests:**
- `test_scan_saved_to_db()`
- `test_scan_results_retrievable()`

### Task 3.3: History Browser Module
**File:** `netrunner.py`
**Changes:**
- New module `[Tab]` or repurpose existing
- DataTable showing past scans
- Filter by module, target, date
- Select to view full results

**Tests:**
- `test_history_module_shows_scans()`
- `test_history_filter_by_module()`
- `test_history_view_full_results()`

### Task 3.4: Baseline Scan Feature
**File:** `netrunner.py`
**Changes:**
- Add "Set Baseline" button in Scanner
- Mark scan as baseline in DB
- Compare current scan to baseline
- Highlight new/removed/changed items

**Tests:**
- `test_set_baseline_marks_scan()`
- `test_comparison_shows_new_hosts()`
- `test_comparison_shows_removed_hosts()`

### Task 3.5: Favorites System
**File:** `netrunner.py`
**Changes:**
- Add `*` keybinding to toggle favorite
- Show star indicator for favorites
- Filter to show only favorites
- Quick-access favorites dropdown

**Tests:**
- `test_star_toggles_favorite()`
- `test_favorites_persisted()`
- `test_favorites_dropdown()`

### Task 3.6: Target Notes
**File:** `netrunner.py`
**Changes:**
- Add `n` keybinding for notes
- Open modal to add/edit notes
- Show notes indicator in history
- Display notes on hover/select

**Tests:**
- `test_n_opens_notes_modal()`
- `test_notes_saved_to_db()`
- `test_notes_displayed_in_history()`

### Task 3.7: Export Improvements
**File:** `netrunner.py`
**Changes:**
- Add HTML report export
- Include scan metadata, timestamps
- Cyberpunk-styled HTML template
- Export multiple scans as report

**Tests:**
- `test_html_export_creates_file()`
- `test_html_includes_metadata()`
- `test_html_renders_correctly()`

---

## Phase 4: Advanced Features

**Goal:** Add powerful new capabilities.

### Task 4.1: Network Topology Map
**File:** `netrunner.py`
**Changes:**
- Parse scan results for network structure
- Generate ASCII topology diagram
- Show gateway → switch → hosts
- Update on new scans

**Example Output:**
```
    [Gateway: 192.168.1.1]
           │
    ┌──────┼──────┐
    │      │      │
  [.10]  [.15]  [.20]
  Pi     Phone  Laptop
```

**Tests:**
- `test_topology_parses_hosts()`
- `test_topology_identifies_gateway()`
- `test_topology_renders_ascii()`

### Task 4.2: Scheduled Scans (systemd Integration)
**Files:**
- `netrunner-scan@.service` (systemd service template)
- `netrunner-scan@.timer` (systemd timer template)
- `netrunner_cli.py` (CLI for headless scans)

**Rationale:** Use systemd timers instead of custom daemon to avoid process management complexity and leverage existing system infrastructure.

**Changes:**
- Create CLI mode for headless scans: `netrunner --scan <profile> --output <file>`
- Generate systemd service/timer files from schedule config
- Store schedules in `~/.config/netrunner/schedules.json`
- Results saved to database automatically
- Generate alerts on changes via mako-notify

**Example systemd files:**
```ini
# ~/.config/systemd/user/netrunner-scan@.service
[Unit]
Description=NetRunner scheduled scan: %i

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 ~/netrunner-v4/netrunner_cli.py --scan %i
```

```ini
# ~/.config/systemd/user/netrunner-scan@.timer
[Unit]
Description=NetRunner scan timer: %i

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

**Management:**
- `netrunner --schedule add <profile> <cron>` - Create schedule
- `netrunner --schedule list` - Show active schedules
- `netrunner --schedule remove <name>` - Remove schedule

**Tests:**
- `test_cli_scan_executes()`
- `test_cli_scan_saves_to_db()`
- `test_schedule_generates_systemd_files()`
- `test_alert_generated_on_change()`

### Task 4.3: Alert System
**File:** `netrunner.py`
**Changes:**
- Alert rules engine
- Conditions: new host, port change, service down
- Actions: notification, sound, log
- Alert history view

**Tests:**
- `test_alert_rule_creation()`
- `test_alert_triggered_on_condition()`
- `test_alert_notification_sent()`

### Task 4.4: Multi-Target Queue
**File:** `netrunner.py`
**Changes:**
- Queue multiple targets for scanning
- Show queue status
- Process sequentially
- Aggregate results view

**Tests:**
- `test_queue_accepts_multiple_targets()`
- `test_queue_processes_in_order()`
- `test_aggregate_results_displayed()`

### Task 4.5: Profile System
**File:** `netrunner.py`
**Changes:**
- Save scan configuration as named profile
- Include: target, scan type, ports, options
- Load profile to restore settings
- Share profiles as JSON files

**Tests:**
- `test_profile_save()`
- `test_profile_load_restores_settings()`
- `test_profile_export_import()`

### Task 4.6: Enhanced OUI Database
**File:** `netrunner.py`, `oui_lookup.py` (new)
**Rationale:** The IEEE OUI file is ~3MB. Use Wireshark's compact `manuf` format (~500KB) instead.

**Changes:**
- Use Wireshark manuf file format (smaller, well-maintained)
- Download from: `https://www.wireshark.org/download/automated/data/manuf`
- Parse into dict for O(1) lookup
- Cache in `~/.config/netrunner/manuf`
- Update command: `netrunner --update-oui`
- Fall back to embedded subset (~100 common vendors) if offline

**Embedded fallback (common vendors):**
```python
COMMON_VENDORS = {
    "00:00:0C": "Cisco",
    "00:1A:2B": "Ayecom",
    "DC:A6:32": "Raspberry Pi",
    "B8:27:EB": "Raspberry Pi",
    # ... ~100 entries
}
```

**Tests:**
- `test_oui_lookup_full_database()`
- `test_oui_update_downloads_manuf()`
- `test_oui_fallback_to_embedded()`
- `test_oui_handles_malformed_mac()`

### Task 4.7: PCAP Export
**File:** `netrunner.py` (Packets module)
**Changes:**
- Add "Save PCAP" button
- Write tcpdump output to .pcap file
- Include metadata header
- Open with Wireshark option

**Tests:**
- `test_pcap_file_created()`
- `test_pcap_valid_format()`

### Task 4.8: Service Enumeration Scripts
**File:** `netrunner.py`
**Changes:**
- Add common nmap scripts integration
- http-enum, ssl-enum-ciphers, ssh-auth-methods
- Select scripts per port/service
- Parse and display script output

**Tests:**
- `test_nse_script_execution()`
- `test_script_output_parsed()`

### Task 4.9: Custom Lisgd Gesture Integration
**File:** `~/.config/lisgd/netrunner.conf`
**Changes:**
- Swipe left/right for tab navigation
- Swipe up for fullscreen toggle
- Two-finger tap for action menu
- Document gestures in help

**Tests:**
- Manual gesture testing
- `test_gesture_config_valid()`

---

## Phase 5: Architecture Refactor

**Goal:** Improve code quality and maintainability.

### Task 5.1: Extract Base Module Class
**File:** `netrunner_base.py` (new)
**Changes:**
```python
class BaseModule(Container):
    """Base class for all NetRunner modules."""

    MODULE_NAME: str
    MODULE_ICON: str

    def compose(self) -> ComposeResult: ...
    def run_action(self, action: str) -> None: ...
    def clear_results(self) -> None: ...
    def get_results_text(self) -> str: ...
    def get_results_json(self) -> dict: ...
    def save_results(self, format: str) -> Path: ...
```

**Tests:**
- `test_base_module_interface()`
- `test_module_inherits_correctly()`

### Task 5.2: Refactor Scanner Module
**File:** `netrunner.py`
**Changes:**
- Inherit from BaseModule
- Extract scan logic to methods
- Standardize result formatting
- Use common patterns

**Tests:**
- `test_scanner_inherits_base()`
- `test_scanner_methods_work()`

### Task 5.3: Refactor All Modules
**Files:** All module classes in `netrunner.py`
**Changes:**
- Apply BaseModule pattern to all 16 modules
- Extract shared code
- Consistent method naming

**Tests:**
- `test_all_modules_inherit_base()`
- `test_all_modules_have_required_methods()`

### Task 5.4: Async Task Queue
**File:** `netrunner_tasks.py` (new)
**Changes:**
- Task queue for async operations
- Priority levels
- Cancellation support
- Progress reporting
- Error handling

**Tests:**
- `test_task_queue_processing()`
- `test_task_cancellation()`
- `test_task_priority()`

### Task 5.5: Code Cleanup Pass
**File:** `netrunner.py`
**Changes:**
- Run ruff fixes (deferred from Phase 0)
- Remove dead code
- Consolidate duplicate logic
- Standardize naming conventions
- Add type hints to public methods

**Tests:**
- `ruff check --fix` passes
- All existing tests still pass
- No new lint warnings introduced

**Note:** Plugin System deferred to v5.0 roadmap - too complex for initial v4.0 release.

---

## Phase 6: Polish & Documentation

**Goal:** Final polish and comprehensive documentation.

### Task 6.1: Theme Variants
**Files:** `netrunner_themes/` (new directory)
**Changes:**
- Extract theme to separate files
- Create variants: Classic, High Contrast, Minimal
- Theme selector in settings
- Custom theme support

**Tests:**
- `test_theme_loading()`
- `test_theme_switching()`

### Task 6.2: Comprehensive Help System
**File:** `netrunner.py`
**Changes:**
- Context-sensitive help
- Tutorial mode for new users
- Searchable help content
- Examples in help pages

**Tests:**
- `test_context_help_shows_relevant()`
- `test_help_search()`

### Task 6.3: Update README
**File:** `~/customization/README.md`
**Content:**
- Installation
- Quick start
- Module reference
- Keybindings
- Configuration
- Troubleshooting
- Contributing

### Task 6.4: Man Page
**File:** `netrunner.1`
**Content:**
- Standard man page format
- Installation to `/usr/local/share/man/`

### Task 6.5: Release Checklist
**File:** `RELEASE.md`
**Content:**
- Version bump procedure
- Changelog format
- Testing checklist
- Backup procedure
- Rollback procedure

---

## AI Orchestration Strategy

### Context Management Rules

**Critical:** No AI agent should continue coding past 30% context usage.

```
Context Limit: 30%
Checkpoint Frequency: After each task
Handoff Protocol: Document state before context limit
```

### Agent Roles

| Agent | Role | Scope |
|-------|------|-------|
| **Orchestrator** | Plans, assigns, reviews | Never writes code directly |
| **Coder** | Implements single tasks | One task per session |
| **Tester** | Writes and runs tests | Test files only |
| **Reviewer** | Reviews PRs, suggests fixes | Read-only analysis |

### Task Assignment Protocol

```
1. Orchestrator reads current plan state
2. Orchestrator selects next unblocked task
3. Orchestrator spawns Coder agent with:
   - Task description
   - Relevant file paths
   - Test requirements
   - Acceptance criteria
4. Coder implements until:
   - Task complete, OR
   - 25% context reached (checkpoint)
5. Coder reports status:
   - COMPLETE: Task done, tests pass
   - CHECKPOINT: Partial progress, document state
   - BLOCKED: Need clarification
6. Orchestrator spawns Tester to verify
7. Orchestrator spawns Reviewer for code review
8. Orchestrator updates plan state
```

### Checkpoint Format

When an agent hits 25% context:

```markdown
## Checkpoint: Task X.Y

### Git State
- Commit: `abc1234` (short hash)
- Branch: `feature/task-x.y`
- Clean working tree: yes/no

### Completed
- [x] Item 1
- [x] Item 2

### In Progress
- [ ] Item 3 (50% done)
  - Subitems completed: A, B
  - Remaining: C, D

### State
- Current file: `netrunner.py`
- Current line: 1234
- Variables/context needed for resumption:
  - Function being modified: `do_scan()`
  - Pattern being applied: BaseModule inheritance

### Next Steps
1. Continue with Item 3 part C
2. Then Item 3 part D
3. Run tests
```

**Important:** Always include git commit hash so resuming agents can reliably checkout the exact state. Line numbers alone are insufficient if other commits have modified the file.

### Agent Prompts

#### Coder Agent Prompt Template
```
You are implementing Task {X.Y}: {task_name}

## Context
- File: {file_path}
- Lines: {start_line}-{end_line} (if applicable)
- Related files: {related_files}

## Requirements
{task_description}

## Acceptance Criteria
{acceptance_criteria}

## Tests Required
{test_list}

## Rules
1. Implement ONLY this task
2. Do NOT refactor unrelated code
3. Match existing code style
4. Add comments for complex logic
5. At 25% context, create checkpoint and stop

## Previous Checkpoint (if any)
{checkpoint_content}
```

#### Tester Agent Prompt Template
```
You are testing Task {X.Y}: {task_name}

## Files Modified
{modified_files}

## Tests to Write/Run
{test_list}

## Test Location
{test_file_path}

## Rules
1. Write pytest tests only
2. Use existing fixtures from conftest.py
3. Mock external dependencies (subprocess, network)
4. Verify all acceptance criteria
5. Report: PASS / FAIL with details
```

#### Reviewer Agent Prompt Template
```
You are reviewing Task {X.Y}: {task_name}

## Changes
{diff_or_file_list}

## Review Checklist
- [ ] Follows existing code patterns
- [ ] No security vulnerabilities introduced
- [ ] No hardcoded values that should be config
- [ ] Error handling present
- [ ] Edge cases considered
- [ ] Tests are comprehensive
- [ ] No unnecessary changes outside task scope

## Output Format
APPROVED / CHANGES_REQUESTED
{feedback_details}
```

### Orchestration State File

**File:** `~/netrunner-v4/.plan_state.json`

```json
{
  "version": "1.0",
  "last_updated": "2026-01-27T10:00:00Z",
  "current_phase": 1,
  "tasks": {
    "0.1": {"status": "complete", "agent": "coder-001", "completed_at": "..."},
    "0.2": {"status": "complete", "agent": "tester-001", "completed_at": "..."},
    "1.1": {"status": "in_progress", "agent": "coder-002", "checkpoint": "..."},
    "1.2": {"status": "blocked", "blocked_by": ["1.1"]},
    "1.3": {"status": "pending"}
  },
  "checkpoints": {
    "1.1": {
      "created_at": "...",
      "agent": "coder-002",
      "context_pct": 25,
      "content": "..."
    }
  }
}
```

### Dependency Graph

```
Phase 0 (all parallel):
  0.1 ─┬─> 0.3 ──> 0.4
  0.2 ─┘
  0.5 (independent)
  0.6 (independent)
  0.7 (independent)
  0.8 ──> Phase 1

Phase 1:
  1.1 (independent - can start immediately)
  1.2 (independent)
  1.3 (independent)
  1.4 (depends on 1.1 for pattern)
  1.5 (independent)
  1.6 (independent)

Phase 2:
  2.1 ──> 2.2 (search builds on selection)
  2.3 (independent)
  2.4 (independent)
  2.5 (depends on 1.5 history)
  2.6 (independent)
  2.7 (independent)
  2.8 (independent)

Phase 3:
  3.1 ──> 3.2 ──> 3.3
       └──> 3.4
       └──> 3.5
       └──> 3.6
  3.7 (depends on 3.2)

Phase 4:
  4.1 (depends on 3.2 for data)
  4.2 ──> 4.3 (alerts need scheduler)
  4.4 (independent)
  4.5 (independent)
  4.6 (independent)
  4.7 (independent)
  4.8 (independent)
  4.9 (independent)

Phase 5:
  5.1 ──> 5.2 ──> 5.3
  5.4 (independent)
  5.5 (depends on all above - final cleanup)

Phase 6:
  All tasks sequential (no parallelization per execution model)
```

---

## Risk Mitigation

### Backup Strategy
- Original source preserved in `~/customization/` (unchanged)
- Development happens in `~/netrunner-v4/` (new git repo)
- After each task: git commit with descriptive message
- After each phase: git tag (e.g., `v4.0-phase1`)
- Weekly: push to remote (if configured)

### Rollback Procedure
```bash
# Rollback to last known good commit
git checkout HEAD~1 -- netrunner.py netrunner.tcss

# Rollback to phase tag
git checkout v4.0-phase1 -- netrunner.py netrunner.tcss

# Full rollback to original v3.2
cp ~/customization/netrunner.py ~/netrunner-v4/netrunner.py
cp ~/customization/netrunner.tcss ~/netrunner-v4/netrunner.tcss
```

### Testing Gates
- No task marked complete without passing tests
- Integration tests run after each phase
- Manual testing on device after phases 1, 2, 4

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Startup time | ~2s | <2s |
| Module switch time | ~100ms | <100ms |
| Lines of code | ~5800 | <7000 (with features) |
| Test coverage | 0% | >60% |
| Modules | 16 | 16 (no bloat) |
| Touch accuracy | ~70% | >90% |

---

## Appendix: File Inventory

### Repository Location
`~/netrunner-v4/` (new git repo, separate from ~/customization/)

### Files to Modify
- `netrunner.py` - Main application
- `netrunner.tcss` - Styles

### Files to Create
| File | Phase | Purpose |
|------|-------|---------|
| `tests/` | 0 | Test directory structure |
| `tests/conftest.py` | 0 | Pytest fixtures |
| `tests/test_*.py` | 0+ | Unit and integration tests |
| `tools_check.py` | 0 | External tool verification |
| `pyproject.toml` | 0 | Project config (ruff, pytest) |
| `docs/ARCHITECTURE.md` | 0 | Architecture documentation |
| `netrunner_config.py` | 1 | Configuration management |
| `netrunner_db.py` | 3 | SQLite database module |
| `netrunner_cli.py` | 4 | CLI for headless/scheduled scans |
| `oui_lookup.py` | 4 | MAC vendor lookup (Wireshark manuf) |
| `netrunner_base.py` | 5 | Base module classes |
| `netrunner_tasks.py` | 5 | Async task queue |
| `netrunner_themes/` | 6 | Theme variants directory |
| `docs/RELEASE.md` | 6 | Release process documentation |

### Systemd Files (Task 4.2)
- `~/.config/systemd/user/netrunner-scan@.service`
- `~/.config/systemd/user/netrunner-scan@.timer`

### Original Source (Preserved)
- `~/customization/netrunner.py` - v3.2 original
- `~/customization/netrunner.tcss` - v3.2 original

---

## How to Use This Plan

### For Human Operator
1. Review and approve plan
2. Verify `~/netrunner-v4/` git repo exists (already initialized)
3. Copy source files from ~/customization/ to ~/netrunner-v4/ (Task 0.1)
4. Start orchestrating agents phase by phase (sequential execution only)

### For Orchestrator AI
1. Load this plan document
2. Load state file (create if missing)
3. Identify next unblocked task
4. Spawn appropriate agent
5. Monitor for checkpoint/completion
6. Update state file
7. Repeat

### For Coder AI
1. Receive task assignment
2. Read relevant files
3. Implement changes
4. Write basic tests inline
5. Checkpoint at 25% context
6. Report status

### For Tester AI
1. Receive test assignment
2. Read implementation
3. Write comprehensive tests
4. Run tests
5. Report results

---

## Deferred to v5.0 Roadmap

The following features were considered but deferred to reduce v4.0 scope:

| Feature | Reason for Deferral |
|---------|---------------------|
| **Plugin System** | Complex to implement correctly; requires stable base architecture first |
| **Split Pane Mode** | 480px display width makes side-by-side modules impractical |
| **Custom Scripting Engine** | Scope creep; users can extend via plugins in v5.0 |
| **Remote Control API** | Security implications need careful design |

These may be revisited after v4.0 stabilizes.

---

*End of Plan Document v1.1*
