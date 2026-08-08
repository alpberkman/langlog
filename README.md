# Language Learning Logger

A single-file desktop app for logging your language-learning practice sessions, then seeing how much you've studied and roughly how much more it would take to reach a given proficiency level.

## Requirements

- Python 3.10+
- [matplotlib](https://matplotlib.org/) (for the Stats/Cumulative charts)
- Tkinter (usually bundled with Python; on Debian/Ubuntu install it separately with `sudo apt install python3-tk` if `import tkinter` fails)

Everything else (`sqlite3`, `csv`, `argparse`, ...) is in the Python standard library.

```bash
pip install -r requirements.txt
```

## Running the app

```bash
python main.py
```

By default, data is stored in a SQLite database at `~/.config/utils/db/langlog.db` (created automatically on first run). To use a different file (e.g. to keep separate data for testing, or per-project):

```bash
python main.py -f path/to/sessions.db
```

## The tabs

- **Log Session** — the main entry form: language, activity type, specific activity, duration, date, and optional notes. Save a session, or save the current form as a reusable **Template** for one-click (or CLI) logging later.
- **Timer** — a simple start/pause/finish stopwatch. Finishing writes the elapsed time into the Log Session form's duration field.
- **History** — a filterable, sortable table of every session you've logged. Double-click a row to edit it, or select one and delete it. Export the current filtered view to CSV.
- **Stats** — a stacked bar chart (time per day/week/month) plus a pie chart (time by activity), over a date range. Use the "Quick" dropdown for common ranges (including "All time", which jumps to your very first logged session for the selected language), or set From/To manually.
- **Cumulative** — the same filters as Stats, but shows running-total time per activity over the date range instead of per-period totals.
- **Learning Time** — a reference table of how long it typically takes to reach professional working proficiency in each language, based on the U.S. Foreign Service Institute's difficulty categories. Languages you've actually logged sessions for are highlighted. Its "Vocabulary" sub-tab is a reference table of approximate vocabulary size needed for each CEFR level (plus HSK/JLPT/TOPIK for Chinese/Japanese/Korean), for your enabled languages.
- **Projection** — for languages you've logged sessions for, projects how much longer it would take to reach each level, and a target date, using either your historical average pace or a custom assumed minutes/day. A second sub-tab shows the incremental effort to go from each level to the next. A third, "Current Level", lets you record a level you were already at *before* you started logging sessions here — the other two sub-tabs then treat that level as a starting baseline: it's always already reached, and hours you log afterward count toward the levels above it on top of that baseline (not just compared against it).
- **Settings** — choose which languages, activity types, and specific activities show up in the dropdowns elsewhere, add your own custom specific activities, pick a chart color per activity type, and switch the ttk theme.

Press **Ctrl+S** while on the Log Session or Settings tab to save without reaching for the mouse.

## CLI mode (no GUI)

Useful for logging a quick session from a script, cron job, or terminal alias, using a template you've already saved from the GUI.

```bash
python main.py --list-templates                 # or -l — list saved template names
python main.py --template "anki-15"              # or -t — log that template for today
python main.py --template "kr-podcast-30" --duration 45 --date "2026-06-18"
                                                  # -m to override duration, -d to override date
```

`-f/--db` also works in CLI mode, to log against a specific database file.
