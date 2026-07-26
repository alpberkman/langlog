# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file desktop app (`main.py`) for logging personal language-learning practice sessions. Built with Tkinter/ttk (GUI), sqlite3 (storage), and matplotlib (charts, embedded via `FigureCanvasTkAgg`). There is no package structure, no build step, and no test suite — everything lives in `main.py`.

## Running

```bash
python main.py                       # launch the GUI (default db: ~/.config/utils/db/langlog.db)
python main.py -f sessions.db        # use a specific db file (repo has a local sessions.db for dev/testing)
```

CLI mode (no GUI) — logs a saved template as a session and exits:

```bash
python main.py --list-templates                                  # or -l
python main.py --template "anki-15"                               # or -t
python main.py --template "kr-podcast-30" --duration 45 --date "2026-06-18"   # -m to override duration, -d to override date
```

## Verifying changes

There is no test suite or linter configured. To validate changes:

```bash
python -m py_compile main.py         # syntax check
python main.py --list-templates       # quick smoke test against DB code path without opening the GUI
```

For GUI changes, actually launch the app (`python main.py -f <scratch-db>`) and exercise the affected tab/dialog — a screenshot via `import -window root <file>.png` (ImageMagick) works if there's an active `$DISPLAY`. Don't rely on py_compile alone to confirm a UI change works.

## Architecture

Everything is in `main.py`, organized top-to-bottom as:

1. **Module-level constants**: `LANGUAGES` (code→name map), `ACTIVITIES` (activity type → list of specific activities), `_CHART_COLORS`, and `FSI_CATEGORIES`/`LANGUAGE_DIFFICULTY` (language-difficulty reference data). Free functions above the classes (`_fmt_time`, `_period_key`, `_all_periods`, `_extract_lang_code`, `_lang_display`, `_prepare_chart_data`, `_validate_session_fields`, `_build_mpl_frame`) are shared helpers used across multiple tabs — check here before adding a new helper, since date/period/formatting logic is centralized rather than duplicated per-tab.

2. **`Database`** — thin wrapper around a single sqlite3 connection. Schema is created idempotently in `_init_schema()` (`CREATE TABLE IF NOT EXISTS`), and default preference rows are seeded once in `_seed_prefs()`. Tables: `sessions` (the actual logged practice sessions), `templates` (reusable session presets for quick logging / CLI use), `pref_languages`, `pref_activity_types`, `pref_specific_activities` (all user-configurable enable/disable lists driven from the Settings tab), and `pref_activity_colors` (per-activity chart colors). All queries are parameterized — follow that pattern for any new query.

3. **`FilterBar`** — shared widget (language/date-range/grouping filter + quick-range presets) reused by the Stats and Cumulative tabs. `_prepare_chart_data` is the shared aggregation step both chart tabs call after pulling rows via `Database.get_chart_rows`.

4. **`DatePickerPopup`** — standalone calendar popup used by the date field in Log Session.

5. **Tabs**, each a `ttk.Frame` subclass, added to a single `ttk.Notebook` in `LanguageLoggerApp`:
   - `LogTab` — the session-entry form plus the saved-templates panel (scrollable button list).
   - `TimerTab` — a start/pause/finish stopwatch that, on Finish, writes the elapsed minutes into `LogTab.var_duration` and switches the notebook to the Log tab.
   - `HistoryTab` — filterable/sortable `ttk.Treeview` of all sessions; double-click row opens an edit dialog; supports CSV export and delete.
   - `StatsTab` — stacked bar + pie chart over a date range (via `FilterBar` + `_prepare_chart_data`).
   - `CumulativeTab` — stacked cumulative-area chart + summary line, same data pipeline as Stats.
   - `LearningTimeTab` — static reference table (FSI-based language difficulty/time estimates); highlights rows for languages the user has actually logged (`Database.distinct_languages()`), independent of the sessions/prefs CRUD flow.
   - `SettingsTab` — its own inner `ttk.Notebook` (Languages / Activity Types / Specific Activities / Theme sub-tabs) that edits the `pref_*` tables and ttk theme; a single "Save Settings" button commits all sub-tabs at once and calls back into `LanguageLoggerApp._on_prefs_changed` to refresh comboboxes on the other tabs.

6. **`LanguageLoggerApp`** (the `tk.Tk` root) — wires all tabs into one `ttk.Notebook`, preloads matplotlib on a background thread (`_preload_matplotlib`) so the first chart render isn't slow, binds Ctrl+S to save-in-current-tab, and refreshes tab-specific data on `<<NotebookTabChanged>>` (History/Stats/Cumulative/Learning Time all lazily refresh only when selected rather than eagerly).

7. **CLI plumbing** (`_parse_args`, `_cli_list_templates`, `_cli_log`) at the bottom — argparse drives either a GUI launch or a one-shot headless template log, decided in the `if __name__ == "__main__":` block.

### Conventions worth following

- Language values are stored as ISO codes (e.g. `"ja"`) and only converted to `"Name (code)"` display strings at the UI boundary (`_lang_display` / `_extract_lang_code`) — don't store display strings in the DB.
- Preference tables (`pref_*`) are the single source of truth for what shows up in dropdowns elsewhere; a new enable/disable-able concept should follow that same enabled-flag-table + seed pattern rather than a hardcoded list.
- New tabs that show data derived from `sessions`/`pref_*` should refresh lazily on tab-select (see `_on_tab_change`) rather than on every keystroke/edit, matching the existing tabs.
