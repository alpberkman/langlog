# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file desktop app (`main.py`) for logging personal language-learning practice sessions. Built with Tkinter/ttk (GUI), sqlite3 (storage), and matplotlib (charts, embedded via `FigureCanvasTkAgg`). There is no package structure and no build step — the app lives entirely in `main.py`; a `unittest` regression suite lives alongside it in `test_main.py`.

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

No linter is configured. To validate changes:

```bash
python -m py_compile main.py          # syntax check
python -m unittest test_main.py -v    # regression suite (Database, helpers, CLI smoke test)
python main.py --list-templates       # quick smoke test against DB code path without opening the GUI
```

`test_main.py` covers the date/formatting helpers, the `Database` layer (temp sqlite files, never the real `sessions.db`), the reference data tables (FSI/CEFR/HSK/JLPT/TOPIK — guards against typos in those hand-maintained dicts), the projection math (`_project_levels`, `_incremental_levels`, `_format_days_in_unit`), the `_sort_treeview` Treeview-sort helper, the `ProjectionTab` pace slider and native-system rows (built against a real `Tk`/`Treeview`, not mocked), and an end-to-end CLI smoke test that shells out to `python main.py --template ...`. Tests that build real Tk widgets are skipped automatically when no `$DISPLAY` is available. It intentionally does not drive most of the Tkinter tab classes (`LogTab`, `HistoryTab`, `StatsTab`, etc.) — those are exercised manually.

For GUI changes, actually launch the app (`python main.py -f <scratch-db>`) and exercise the affected tab/dialog — a screenshot via `import -window root <file>.png` (ImageMagick) works if there's an active `$DISPLAY`. Don't rely on py_compile or the unit tests alone to confirm a UI change works.

## Architecture

Everything is in `main.py`, organized top-to-bottom as:

1. **Module-level constants**: `LANGUAGES` (code→name map), `ACTIVITIES` (activity type → list of specific activities), `_CHART_COLORS`, `FSI_CATEGORIES`/`LANGUAGE_DIFFICULTY` (FSI language-difficulty reference data, including each category's `hours_est` numeric anchor, used by the Learning Time and Projection tabs), and `CEFR_WORD_COUNTS`/`NATIVE_LEVEL_SYSTEMS` (CEFR/HSK/JLPT/TOPIK vocabulary-size reference data used by the Vocabulary and Projection tabs). Free functions above the classes (`_fmt_time`, `_period_key`, `_all_periods`, `_extract_lang_code`, `_lang_display`, `_prepare_chart_data`, `_load_chart_context`, `_summary_line`, `_project_levels`, `_incremental_levels`, `_format_days_in_unit`, `_validate_session_fields`, `_build_mpl_frame`, `_sort_treeview`) are shared helpers used across multiple tabs — check here before adding a new helper, since date/period/formatting/sorting logic is centralized rather than duplicated per-tab.

2. **`Database`** — thin wrapper around a single sqlite3 connection. Schema is created idempotently in `_init_schema()` (`CREATE TABLE IF NOT EXISTS`), and default preference rows are seeded once in `_seed_prefs()`. Tables: `sessions` (the actual logged practice sessions), `templates` (reusable session presets for quick logging / CLI use), `pref_languages`, `pref_activity_types`, `pref_specific_activities` (all user-configurable enable/disable lists driven from the Settings tab), and `pref_activity_colors` (per-activity chart colors). `language_time_stats(lang_code)` aggregates total minutes / first / last session date for one language, feeding the Projection tab. All queries are parameterized — follow that pattern for any new query.

3. **`FilterBar`** — shared widget (language/date-range/grouping filter + quick-range presets) reused by the Stats and Cumulative tabs. `_load_chart_context(db, filter_bar)` is the shared refresh step both chart tabs call: it parses the filter bar's date range (showing the error dialog and returning `None` if invalid), fetches rows via `Database.get_chart_rows`, and runs them through `_prepare_chart_data`. `_summary_line(rows, p_keys, grouping)` builds the "Sessions: N · Total: ... · Avg session: ... · Avg per {grouping}: ... · Top activity: ..." strip both tabs display above their chart.

4. **`DatePickerPopup`** — standalone calendar popup used by the date field in Log Session.

5. **Tabs**, each a `ttk.Frame` subclass, added to a single `ttk.Notebook` in `LanguageLoggerApp`:
   - `LogTab` — the session-entry form plus the saved-templates panel (scrollable button list; its row/column weights let the panel grow when the window is resized).
   - `TimerTab` — a start/pause/finish stopwatch that, on Finish, writes the elapsed minutes into `LogTab.var_duration` and switches the notebook to the Log tab.
   - `HistoryTab` — filterable `ttk.Treeview` of all sessions, sortable via `_sort_treeview`; double-click row opens an edit dialog; supports CSV export and delete.
   - `StatsTab` — stacked bar + pie chart over a date range (via `FilterBar` + `_load_chart_context`), plus a `_summary_line` strip; the bar chart also draws a dashed `axhline` at the average duration per period.
   - `CumulativeTab` — stacked cumulative-area chart, same data pipeline and summary strip as Stats.
   - `LearningTimeTab` — static reference table (FSI-based language difficulty/time estimates), sortable via `_sort_treeview`; highlights rows for languages the user has actually logged (`Database.distinct_languages()`), independent of the sessions/prefs CRUD flow.
   - `VocabTab` — static reference table of approximate vocabulary size per proficiency level (CEFR for every language, plus HSK/JLPT/TOPIK where applicable), filterable to the user's enabled languages (`Database.pref_languages()`).
   - `ProjectionTab` — for languages the user has actually logged sessions for, has two inner sub-tabs sharing one language filter and a Day/Week/Month/Year pace slider: "To Reach Level" projects estimated remaining duration and a target date to reach each level via `_project_levels` (scales hours-needed off the language's FSI `hours_est`, anchored so CEFR C1 == that FSI hour estimate, divided by historical average pace from `Database.language_time_stats`); "Per-Level Effort" shows the incremental words/hours/duration to go from each level to the next via `_incremental_levels`, independent of actual progress. Both sub-tabs run once for CEFR and again for the language's native scale (HSK/JLPT/TOPIK) via `NATIVE_LEVEL_SYSTEMS`, shown in a "System" column — `_project_levels`/`_incremental_levels` take a `word_counts` table so either can be scaled the same way. The slider's chosen unit rescales the pace figure and the remaining/needed duration (via `_format_days_in_unit`) but not the target date.
   - `SettingsTab` — its own inner `ttk.Notebook` (Languages / Activity Types / Specific Activities / Theme sub-tabs) that edits the `pref_*` tables and ttk theme; a single "Save Settings" button commits all sub-tabs at once and calls back into `LanguageLoggerApp._on_prefs_changed` to refresh comboboxes on the other tabs.

6. **`LanguageLoggerApp`** (the `tk.Tk` root) — wires all tabs into one `ttk.Notebook`, preloads matplotlib on a background thread (`_preload_matplotlib`) so the first chart render isn't slow, binds Ctrl+S to save-in-current-tab, and refreshes tab-specific data on `<<NotebookTabChanged>>` (History/Stats/Cumulative/Learning Time/Projection all lazily refresh only when selected rather than eagerly; Vocabulary instead refreshes from `_on_prefs_changed` since its data only depends on language prefs, not on sessions).

7. **CLI plumbing** (`_parse_args`, `_cli_list_templates`, `_cli_log`) at the bottom — argparse drives either a GUI launch or a one-shot headless template log, decided in the `if __name__ == "__main__":` block.

### Conventions worth following

- Language values are stored as ISO codes (e.g. `"ja"`) and only converted to `"Name (code)"` display strings at the UI boundary (`_lang_display` / `_extract_lang_code`) — don't store display strings in the DB.
- Preference tables (`pref_*`) are the single source of truth for what shows up in dropdowns elsewhere; a new enable/disable-able concept should follow that same enabled-flag-table + seed pattern rather than a hardcoded list.
- New tabs that show data derived from `sessions` should refresh lazily on tab-select (see `_on_tab_change`); tabs whose data only derives from `pref_*` can instead refresh from `_on_prefs_changed` (see `VocabTab`) — either way, avoid refreshing on every keystroke/edit.
- Any new sortable `ttk.Treeview` should use the shared `_sort_treeview(tree, column, state, numeric_columns=...)` helper rather than a bespoke per-tab `_sort` method.
- A frame that should grow when the window is resized needs its row/column weight set explicitly (`rowconfigure`/`columnconfigure`) all the way down the widget tree — `pack(fill=..., expand=True)` on an ancestor alone doesn't cascade weight to a `grid()`-managed descendant.
