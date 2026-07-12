#!/usr/bin/env python

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog, colorchooser
import sqlite3
import csv
import os
import sys
import argparse
import threading
import time
import calendar
from collections import defaultdict, namedtuple
from datetime import date, timedelta, datetime

_DEFAULT_DB = os.path.join(os.path.expanduser("~"), ".config", "utils", "db", "langlog.db")

def _parse_args():
    p = argparse.ArgumentParser(description="Language Learning Logger")
    p.add_argument("-f", "--db", default=_DEFAULT_DB, metavar="PATH",
                   help="Path to the SQLite database (default: sessions.db next to this script)")
    p.add_argument("-t", "--template", metavar="NAME",
                   help="Log a session using this template name and exit without opening the GUI")
    p.add_argument("-d", "--date", metavar="YYYY-MM-DD", default=date.today().isoformat(),
                   help="Date for the session (default: today)")
    p.add_argument("-m", "--duration", metavar="MINUTES", type=int,
                   help="Override the template's duration (minutes)")
    p.add_argument("-l", "--list-templates", action="store_true",
                   help="Print all saved template names and exit")
    return p.parse_args()

_ARGS = _parse_args()
DB_PATH = _ARGS.db

LANGUAGES = {
    "af": "Afrikaans", "sq": "Albanian",  "ar": "Arabic",     "hy": "Armenian",
    "az": "Azerbaijani","eu": "Basque",    "be": "Belarusian", "bn": "Bengali",
    "bs": "Bosnian",   "bg": "Bulgarian", "ca": "Catalan",    "zh": "Chinese",
    "hr": "Croatian",  "cs": "Czech",     "da": "Danish",     "nl": "Dutch",
    "en": "English",   "et": "Estonian",  "fi": "Finnish",    "fr": "French",
    "gl": "Galician",  "ka": "Georgian",  "de": "German",     "el": "Greek",
    "gu": "Gujarati",  "ht": "Haitian Creole", "he": "Hebrew","hi": "Hindi",
    "hu": "Hungarian", "is": "Icelandic", "id": "Indonesian", "ga": "Irish",
    "it": "Italian",   "ja": "Japanese",  "kn": "Kannada",    "kk": "Kazakh",
    "ko": "Korean",    "ku": "Kurdish",   "lv": "Latvian",    "lt": "Lithuanian",
    "mk": "Macedonian","ms": "Malay",     "ml": "Malayalam",  "mt": "Maltese",
    "mr": "Marathi",   "mn": "Mongolian", "ne": "Nepali",     "no": "Norwegian",
    "fa": "Persian",   "pl": "Polish",    "pt": "Portuguese", "pa": "Punjabi",
    "ro": "Romanian",  "ru": "Russian",   "sr": "Serbian",    "sk": "Slovak",
    "sl": "Slovenian", "es": "Spanish",   "sw": "Swahili",    "sv": "Swedish",
    "tl": "Tagalog",   "ta": "Tamil",     "te": "Telugu",     "th": "Thai",
    "tr": "Turkish",   "uk": "Ukrainian", "ur": "Urdu",       "uz": "Uzbek",
    "vi": "Vietnamese","cy": "Welsh",     "yi": "Yiddish",
}
LANGUAGE_OPTIONS = sorted(
    [f"{name} ({code})" for code, name in LANGUAGES.items()],
    key=lambda s: s.lower(),
)

ACTIVITIES = {
    "Listening":  ["Podcast", "Audiobook", "Music", "Radio", "TV/Video", "Movie", "Other"],
    "Reading":    ["Book", "Article", "News", "Manga/Comic", "Subtitles", "Other"],
    "Speaking":   ["Conversation", "Language Exchange", "Tutor/Class", "Shadowing", "Monologue", "Other"],
    "Writing":    ["Journal", "Translation", "Chat/Messaging", "Grammar Exercises", "Other"],
    "Vocabulary": ["Flashcards (Anki)", "App (Duolingo etc.)", "Word List", "Dictionary Study", "Other"],
    "Grammar":    ["Textbook", "Exercises", "Online Course", "Other"],
    "Watching":   ["Movie", "TV Series", "YouTube", "Other"],
}

_CHART_COLORS = [
    "#4e79a7", "#f28e2b", "#e15759", "#76b7b2",
    "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
]

# FSI (U.S. Foreign Service Institute) difficulty categories for native English
# speakers, and roughly how long each takes to reach professional working
# proficiency in a classroom setting.
FSI_CATEGORIES = {
    "I":   {"hours": "600-750",  "weeks": "24-30", "desc": "Languages closely related to English"},
    "II":  {"hours": "900",      "weeks": "36",    "desc": "Similar languages"},
    "III": {"hours": "1100",     "weeks": "44",    "desc": "Languages with significant linguistic/cultural differences"},
    "IV":  {"hours": "2200",     "weeks": "88",    "desc": "Exceptionally difficult for English speakers"},
}

# code -> (FSI category, is_estimated). is_estimated=True means the language is
# not on FSI's official list and the category is extrapolated from its closest
# relatives / typological profile.
LANGUAGE_DIFFICULTY = {
    "af": ("I", False),   "sq": ("III", False), "ar": ("IV", False),  "hy": ("III", False),
    "az": ("III", False), "eu": ("IV", True),   "be": ("III", True),  "bn": ("III", False),
    "bs": ("III", False), "bg": ("III", False), "ca": ("I", True),    "zh": ("IV", False),
    "hr": ("III", False), "cs": ("III", False), "da": ("I", False),   "nl": ("I", False),
    "et": ("III", False), "fi": ("III", False), "fr": ("I", False),   "gl": ("I", True),
    "ka": ("III", False), "de": ("II", False),  "el": ("III", False), "gu": ("III", True),
    "ht": ("II", False),  "he": ("III", False), "hi": ("III", False), "hu": ("III", False),
    "is": ("III", False), "id": ("II", False),  "ga": ("IV", True),   "it": ("I", False),
    "ja": ("IV", False),  "kn": ("III", True),  "kk": ("III", False), "ko": ("IV", False),
    "ku": ("III", True),  "lv": ("III", False), "lt": ("III", False), "mk": ("III", True),
    "ms": ("II", False),  "ml": ("III", True),  "mt": ("III", True),  "mr": ("III", True),
    "mn": ("III", False), "ne": ("III", False), "no": ("I", False),   "fa": ("III", False),
    "pl": ("III", False), "pt": ("I", False),   "pa": ("III", False), "ro": ("I", False),
    "ru": ("III", False), "sr": ("III", False), "sk": ("III", False), "sl": ("III", False),
    "es": ("I", False),   "sw": ("II", False),  "sv": ("I", False),   "tl": ("III", False),
    "ta": ("III", False), "te": ("III", False), "th": ("III", False), "tr": ("III", False),
    "uk": ("III", False), "ur": ("III", False), "uz": ("III", False), "vi": ("III", False),
    "cy": ("IV", True),   "yi": ("II", True),
}


def _fmt_time(total_minutes: float) -> str:
    m = int(round(total_minutes))
    d, rem = divmod(m, 1440)
    h, mn  = divmod(rem, 60)
    if d > 0:
        return f"{d:02d}:{h:02d}:{mn:02d}"
    return f"{h:02d}:{mn:02d}"


def _months_ago(n: int) -> date:
    today = date.today()
    year, month = today.year, today.month - n
    while month <= 0:
        month += 12
        year  -= 1
    try:
        return date(year, month, today.day)
    except ValueError:
        return date(year, month + 1, 1) - timedelta(days=1)


def _period_key(d_str: str, grouping: str) -> str:
    d = datetime.strptime(d_str, "%Y-%m-%d").date()
    if grouping == "Day":
        return d.isoformat()
    if grouping == "Week":
        return (d - timedelta(days=d.weekday())).isoformat()
    return d_str[:7]


def _all_periods(s: date, e: date, grouping: str) -> list:
    result = []
    if grouping == "Day":
        d = s
        while d <= e:
            result.append((d.isoformat(), d.strftime("%b %d")))
            d += timedelta(days=1)
    elif grouping == "Week":
        ws = s - timedelta(days=s.weekday())
        while ws <= e:
            result.append((ws.isoformat(), ws.strftime("%b %d")))
            ws += timedelta(weeks=1)
    else:
        d = date(s.year, s.month, 1)
        while d <= e:
            result.append((d.strftime("%Y-%m"), d.strftime("%b '%y")))
            nxt = d.month % 12 + 1
            d   = date(d.year + (1 if d.month == 12 else 0), nxt, 1)
    return result


def _extract_lang_code(display_value: str) -> str:
    if display_value.endswith(")") and "(" in display_value:
        return display_value.rsplit("(", 1)[-1].rstrip(")")
    return display_value.strip()


def _lang_display(lang_code: str) -> str:
    if not lang_code:
        return ""
    name = LANGUAGES.get(lang_code, "")
    return f"{name} ({lang_code})" if name else lang_code


def _contrasting_fg(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return "#000000" if (r * 299 + g * 587 + b * 114) / 1000 > 128 else "#ffffff"


_ChartData = namedtuple("_ChartData", ["all_acts", "color_map", "p_keys", "p_labels", "by_act_period"])


def _prepare_chart_data(rows, start_date, end_date, grouping, user_colors=None):
    """Shared computation for Stats and Cumulative charts. Returns None when rows is empty."""
    if not rows:
        return None
    _uc       = user_colors or {}
    all_acts  = sorted(set(act for _, act, _ in rows))
    color_map = {act: (_uc.get(act) or _CHART_COLORS[i % len(_CHART_COLORS)]) for i, act in enumerate(all_acts)}
    data_dates = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]
    eff_start  = start_date or min(data_dates)
    eff_end    = end_date   or max(data_dates)
    periods    = _all_periods(eff_start, eff_end, grouping)
    p_keys     = [p[0] for p in periods]
    p_labels   = [p[1] for p in periods]
    by_act_period = defaultdict(lambda: defaultdict(float))
    for d_str, act, dur in rows:
        by_act_period[act][_period_key(d_str, grouping)] += dur / 60
    return _ChartData(all_acts, color_map, p_keys, p_labels, by_act_period)


def _validate_session_fields(lang_display, activity_type, dur_raw, date_str, db, parent=None):
    """Returns (lang_code, duration) on success, None after showing an error dialog."""
    if lang_display and lang_display not in db.pref_languages():
        messagebox.showerror("Validation Error",
            "Language must be selected from the dropdown list or left empty.", parent=parent)
        return None
    if not activity_type:
        messagebox.showerror("Validation Error", "Activity Type is required.", parent=parent)
        return None
    try:
        duration = int(float(str(dur_raw)))
        if duration < 1:
            raise ValueError
    except (ValueError, tk.TclError):
        messagebox.showerror("Validation Error", "Duration must be a positive integer.", parent=parent)
        return None
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        messagebox.showerror("Validation Error", "Date must be in YYYY-MM-DD format.", parent=parent)
        return None
    return _extract_lang_code(lang_display) if lang_display else None, duration


def _build_mpl_frame(parent, canvas_row: int, **adjust_kw):
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
    fig = Figure(figsize=(8, 4), dpi=96)
    fig.subplots_adjust(**adjust_kw)
    canvas = FigureCanvasTkAgg(fig, master=parent)
    canvas.get_tk_widget().grid(row=canvas_row, column=0, sticky=tk.NSEW)
    toolbar_frame = ttk.Frame(parent)
    toolbar_frame.grid(row=canvas_row + 1, column=0, sticky=tk.EW)
    NavigationToolbar2Tk(canvas, toolbar_frame)
    return fig, canvas


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class Database:
    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.conn = sqlite3.connect(path)
        self._init_schema()
        self._seed_prefs()

    def _init_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                language          TEXT,
                activity_type     TEXT    NOT NULL,
                specific_activity TEXT,
                duration_minutes  INTEGER NOT NULL,
                date              TEXT    NOT NULL,
                notes             TEXT
            );
            CREATE TABLE IF NOT EXISTS pref_languages (
                code    TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS pref_activity_types (
                name    TEXT PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS pref_specific_activities (
                activity_type TEXT    NOT NULL,
                name          TEXT    NOT NULL,
                enabled       INTEGER NOT NULL DEFAULT 1,
                is_custom     INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (activity_type, name)
            );
            CREATE TABLE IF NOT EXISTS templates (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                name              TEXT    NOT NULL UNIQUE,
                language          TEXT,
                activity_type     TEXT    NOT NULL,
                specific_activity TEXT,
                duration_minutes  INTEGER NOT NULL,
                notes             TEXT
            );
            CREATE TABLE IF NOT EXISTS pref_activity_colors (
                activity_type TEXT PRIMARY KEY,
                color         TEXT NOT NULL
            );
        """)
        self.conn.commit()

    def _seed_prefs(self):
        if self.conn.execute("SELECT COUNT(*) FROM pref_languages").fetchone()[0] == 0:
            self.conn.executemany(
                "INSERT OR IGNORE INTO pref_languages VALUES (?, 0)",
                [(code,) for code in LANGUAGES],
            )
        if self.conn.execute("SELECT COUNT(*) FROM pref_activity_types").fetchone()[0] == 0:
            self.conn.executemany(
                "INSERT OR IGNORE INTO pref_activity_types VALUES (?, 1)",
                [(name,) for name in ACTIVITIES],
            )
        if self.conn.execute("SELECT COUNT(*) FROM pref_specific_activities").fetchone()[0] == 0:
            self.conn.executemany(
                "INSERT OR IGNORE INTO pref_specific_activities VALUES (?, ?, ?, ?)",
                [(act, spec, 1, 0) for act, specs in ACTIVITIES.items() for spec in specs],
            )
        self.conn.commit()

    # ---------- preference readers ----------

    def pref_languages(self) -> list:
        enabled = {r[0] for r in self.conn.execute("SELECT code FROM pref_languages WHERE enabled=1")}
        if not enabled:
            return LANGUAGE_OPTIONS
        return [o for o in LANGUAGE_OPTIONS if _extract_lang_code(o) in enabled]

    def pref_activity_types(self) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM pref_activity_types WHERE enabled=1"
        )]

    def pref_specifics(self, activity_type: str) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM pref_specific_activities "
            "WHERE activity_type=? AND enabled=1 ORDER BY is_custom, name",
            (activity_type,),
        )]

    def enabled_lang_codes(self) -> set:
        return {r[0] for r in self.conn.execute("SELECT code FROM pref_languages WHERE enabled=1")}

    def enabled_activity_names(self) -> set:
        return {r[0] for r in self.conn.execute("SELECT name FROM pref_activity_types WHERE enabled=1")}

    def load_spec_state(self) -> dict:
        result = {}
        for act_type in ACTIVITIES:
            rows = self.conn.execute(
                "SELECT name, is_custom, enabled FROM pref_specific_activities "
                "WHERE activity_type=? ORDER BY is_custom, name",
                (act_type,),
            ).fetchall()
            result[act_type] = {
                "items":    [(r[0], bool(r[1])) for r in rows],
                "selected": {r[0] for r in rows if r[2]},
            }
        return result

    # ---------- sessions ----------

    def _build_where(self, lang_code=None, activity=None, start=None, end=None):
        conditions, params = [], []
        if lang_code is not None:
            if lang_code == "":
                conditions.append("(language IS NULL OR language = '')")
            else:
                conditions.append("language = ?")
                params.append(lang_code)
        if activity:
            conditions.append("activity_type = ?")
            params.append(activity)
        if start:
            conditions.append("date >= ?")
            params.append(start)
        if end:
            conditions.append("date <= ?")
            params.append(end)
        return ("WHERE " + " AND ".join(conditions)) if conditions else "", params

    def get_sessions(self, lang_code=None, activity=None, start=None, end=None) -> list:
        where, params = self._build_where(lang_code, activity, start, end)
        return self.conn.execute(
            f"SELECT id, date, language, activity_type, specific_activity, duration_minutes, notes "
            f"FROM sessions {where} ORDER BY date DESC",
            params,
        ).fetchall()

    def get_chart_rows(self, lang_code=None, start=None, end=None) -> list:
        where, params = self._build_where(lang_code, start=start, end=end)
        return self.conn.execute(
            f"SELECT date, activity_type, duration_minutes FROM sessions {where}", params
        ).fetchall()

    def get_session(self, session_id: int) -> tuple:
        return self.conn.execute(
            "SELECT language, activity_type, specific_activity, duration_minutes, date, notes "
            "FROM sessions WHERE id=?", (session_id,)
        ).fetchone()

    def insert_session(self, language, activity_type, specific, duration, date_str, notes):
        self.conn.execute(
            "INSERT INTO sessions "
            "(language, activity_type, specific_activity, duration_minutes, date, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (language, activity_type, specific, duration, date_str, notes),
        )
        self.conn.commit()

    def update_session(self, session_id, language, activity_type, specific, duration, date_str, notes):
        self.conn.execute(
            "UPDATE sessions SET language=?, activity_type=?, specific_activity=?, "
            "duration_minutes=?, date=?, notes=? WHERE id=?",
            (language, activity_type, specific, duration, date_str, notes, session_id),
        )
        self.conn.commit()

    def delete_session(self, session_id: int):
        self.conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))
        self.conn.commit()

    def distinct_languages(self) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT language FROM sessions WHERE language IS NOT NULL ORDER BY language"
        ).fetchall()]

    def distinct_activities(self) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT activity_type FROM sessions ORDER BY activity_type"
        ).fetchall()]

    # ---------- templates ----------

    def get_templates(self) -> list:
        return self.conn.execute("SELECT id, name FROM templates ORDER BY name").fetchall()

    def get_template(self, template_id: int) -> tuple:
        return self.conn.execute(
            "SELECT language, activity_type, specific_activity, duration_minutes, notes "
            "FROM templates WHERE id=?", (template_id,)
        ).fetchone()

    def get_template_by_name(self, name: str) -> tuple | None:
        return self.conn.execute(
            "SELECT language, activity_type, specific_activity, duration_minutes, notes "
            "FROM templates WHERE name=?", (name,)
        ).fetchone()

    def insert_template(self, name, language, activity_type, specific, duration, notes):
        self.conn.execute(
            "INSERT INTO templates "
            "(name, language, activity_type, specific_activity, duration_minutes, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (name, language, activity_type, specific, duration, notes),
        )
        self.conn.commit()

    def delete_template(self, template_id: int):
        self.conn.execute("DELETE FROM templates WHERE id=?", (template_id,))
        self.conn.commit()

    def get_activity_colors(self) -> dict:
        return {r[0]: r[1] for r in self.conn.execute(
            "SELECT activity_type, color FROM pref_activity_colors"
        )}

    def save_activity_colors(self, colors: dict):
        self.conn.execute("DELETE FROM pref_activity_colors")
        self.conn.executemany(
            "INSERT INTO pref_activity_colors (activity_type, color) VALUES (?, ?)",
            colors.items(),
        )
        self.conn.commit()

    # ---------- preference saves ----------

    def save_lang_prefs(self, selected_codes: set):
        self.conn.executemany(
            "INSERT OR REPLACE INTO pref_languages (code, enabled) VALUES (?, ?)",
            [(code, 1 if code in selected_codes else 0) for code in LANGUAGES],
        )
        self.conn.commit()

    def save_activity_prefs(self, enabled_map: dict):
        self.conn.executemany(
            "INSERT OR REPLACE INTO pref_activity_types (name, enabled) VALUES (?, ?)",
            [(name, 1 if enabled else 0) for name, enabled in enabled_map.items()],
        )
        self.conn.commit()

    def save_specific_prefs(self, spec_state: dict):
        for act_type, state in spec_state.items():
            existing = {r[0] for r in self.conn.execute(
                "SELECT name FROM pref_specific_activities WHERE activity_type=?", (act_type,)
            )}
            current = {item[0] for item in state["items"]}
            for name in existing - current:
                self.conn.execute(
                    "DELETE FROM pref_specific_activities WHERE activity_type=? AND name=?",
                    (act_type, name),
                )
            for name, is_custom in state["items"]:
                self.conn.execute(
                    "INSERT OR REPLACE INTO pref_specific_activities "
                    "(activity_type, name, enabled, is_custom) VALUES (?, ?, ?, ?)",
                    (act_type, name, 1 if name in state["selected"] else 0, 1 if is_custom else 0),
                )
        self.conn.commit()


# ---------------------------------------------------------------------------
# FilterBar — shared widget for Stats and Cumulative tabs
# ---------------------------------------------------------------------------

class FilterBar(ttk.Frame):
    def __init__(self, parent, db: Database, on_refresh):
        super().__init__(parent)
        self.db         = db
        self._on_refresh = on_refresh
        self._build()

    def _build(self):
        _lang_w = max(len(o) for o in LANGUAGE_OPTIONS)

        ttk.Label(self, text="Language:").pack(side=tk.LEFT)
        self.var_lang = tk.StringVar(value="All")
        self.cb_lang = ttk.Combobox(
            self, textvariable=self.var_lang,
            values=["All", "(No language)"] + self.db.pref_languages(), width=_lang_w, state="readonly",
        )
        self.cb_lang.pack(side=tk.LEFT, padx=(4, 10))

        eight_ago = (date.today() - timedelta(weeks=8)).isoformat()
        ttk.Label(self, text="From:").pack(side=tk.LEFT)
        self.var_start = tk.StringVar(value=eight_ago)
        ttk.Entry(self, textvariable=self.var_start, width=11).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(self, text="To:").pack(side=tk.LEFT)
        self.var_end = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(self, textvariable=self.var_end, width=11).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(self, text="By:").pack(side=tk.LEFT)
        self.var_groupby = tk.StringVar(value="Week")
        ttk.Combobox(
            self, textvariable=self.var_groupby,
            values=["Day", "Week", "Month"], width=6, state="readonly",
        ).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Label(self, text="Quick:").pack(side=tk.LEFT)
        self.var_preset = tk.StringVar()
        cb_preset = ttk.Combobox(
            self, textvariable=self.var_preset,
            values=["Last week", "Last month", "Last 3 months", "Last 6 months", "Last year"],
            width=13, state="readonly",
        )
        cb_preset.pack(side=tk.LEFT, padx=(4, 10))
        cb_preset.bind("<<ComboboxSelected>>", self._apply_preset)

        ttk.Button(self, text="Refresh", command=self._on_refresh).pack(side=tk.LEFT)

    def _apply_preset(self, event=None):
        preset = self.var_preset.get()
        today  = date.today()
        starts = {
            "Last week":     today - timedelta(weeks=1),
            "Last month":    _months_ago(1),
            "Last 3 months": _months_ago(3),
            "Last 6 months": _months_ago(6),
            "Last year":     _months_ago(12),
        }
        start = starts.get(preset)
        if start:
            self.var_start.set(start.isoformat())
            self.var_end.set(today.isoformat())
            self._on_refresh()

    def refresh_lang_options(self):
        self.cb_lang["values"] = ["All", "(No language)"] + self.db.pref_languages()

    @property
    def lang_code(self):
        v = self.var_lang.get()
        if v == "All":
            return None
        if v == "(No language)":
            return ""
        return _extract_lang_code(v)

    @property
    def lang_display(self):
        return self.var_lang.get()

    @property
    def start_str(self):
        return self.var_start.get().strip()

    @property
    def end_str(self):
        return self.var_end.get().strip()

    @property
    def grouping(self):
        return self.var_groupby.get()


# ---------------------------------------------------------------------------
# Date picker popup
# ---------------------------------------------------------------------------

class DatePickerPopup(tk.Toplevel):
    def __init__(self, anchor_widget, var: tk.StringVar):
        root = anchor_widget.winfo_toplevel()
        super().__init__(root)
        self.withdraw()
        self.var   = var
        self._app_root = root
        self.overrideredirect(True)
        self.resizable(False, False)

        try:
            cur = datetime.strptime(var.get(), "%Y-%m-%d").date()
        except ValueError:
            cur = date.today()
        self.year  = cur.year
        self.month = cur.month
        self._sel  = cur

        self._build()
        self._draw_days()

        self.update_idletasks()
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 2
        self.geometry(f"+{x}+{y}")
        self.deiconify()

        self.focus_set()
        self.bind("<Escape>", lambda e: self.destroy())
        self._bind_id = root.bind("<ButtonPress>", self._outside_click, add=True)

    def _outside_click(self, event):
        # Walk up from the clicked widget — if we find this popup, click was inside
        w = event.widget
        while w is not None:
            if w is self:
                return
            try:
                w = w.master
            except AttributeError:
                break
        self.destroy()

    def destroy(self):
        try:
            self._app_root.unbind("<ButtonPress>", self._bind_id)
        except Exception:
            pass
        super().destroy()

    def _build(self):
        outer = ttk.Frame(self, relief="solid", borderwidth=1)
        outer.pack(fill=tk.BOTH, expand=True)

        # Month row
        month_nav = ttk.Frame(outer, padding=(6, 6, 6, 2))
        month_nav.pack(fill=tk.X)
        ttk.Button(month_nav, text="◀", width=2, command=self._prev_month).pack(side=tk.LEFT)
        ttk.Button(month_nav, text="▶", width=2, command=self._next_month).pack(side=tk.RIGHT)
        self.lbl_month = ttk.Label(month_nav, anchor=tk.CENTER, font=("", 10, "bold"))
        self.lbl_month.pack(side=tk.LEFT, expand=True)

        # Year row
        year_nav = ttk.Frame(outer, padding=(6, 0, 6, 4))
        year_nav.pack(fill=tk.X)
        ttk.Button(year_nav, text="◀", width=2, command=self._prev_year).pack(side=tk.LEFT)
        ttk.Button(year_nav, text="▶", width=2, command=self._next_year).pack(side=tk.RIGHT)
        self.lbl_year = ttk.Label(year_nav, anchor=tk.CENTER)
        self.lbl_year.pack(side=tk.LEFT, expand=True)

        self.day_frame = ttk.Frame(outer, padding=(6, 2, 6, 4))
        self.day_frame.pack()
        for i, d in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]):
            ttk.Label(self.day_frame, text=d, width=3, anchor=tk.CENTER).grid(row=0, column=i, padx=1)
        self._day_btns = [
            [ttk.Button(self.day_frame, text="", width=3) for _ in range(7)]
            for _ in range(6)
        ]
        for r, row in enumerate(self._day_btns):
            for c, btn in enumerate(row):
                btn.grid(row=r + 1, column=c, padx=1, pady=1)

        # Today button
        ttk.Button(outer, text="Today", command=self._select_today).pack(pady=(0, 6))

    def _draw_days(self):
        self.lbl_month.config(text=calendar.month_name[self.month])
        self.lbl_year.config(text=str(self.year))
        weeks = calendar.monthcalendar(self.year, self.month)
        for r in range(6):
            week = weeks[r] if r < len(weeks) else [0] * 7
            for c, day in enumerate(week):
                btn = self._day_btns[r][c]
                if day == 0:
                    btn.config(text="", state="disabled")
                else:
                    btn.config(text=str(day), state="normal",
                               command=lambda d=date(self.year, self.month, day): self._select(d))

    def _select(self, d: date):
        self.var.set(d.isoformat())
        self.destroy()

    def _select_today(self):
        self._select(date.today())

    def _prev_month(self):
        if self.month == 1:
            self.month, self.year = 12, self.year - 1
        else:
            self.month -= 1
        self._draw_days()

    def _next_month(self):
        if self.month == 12:
            self.month, self.year = 1, self.year + 1
        else:
            self.month += 1
        self._draw_days()

    def _prev_year(self):
        self.year -= 1
        self._draw_days()

    def _next_year(self):
        self.year += 1
        self._draw_days()


# ---------------------------------------------------------------------------
# Tab 1 — Log Session
# ---------------------------------------------------------------------------

class LogTab(ttk.Frame):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db = db
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        def lbl(text, r):
            ttk.Label(frame, text=text).grid(row=r, column=0, sticky=tk.W, pady=6, padx=(0, 12))

        lbl("Language:", 0)
        self.var_language = tk.StringVar()
        self.cb_language = ttk.Combobox(frame, textvariable=self.var_language, width=30)
        self.cb_language["values"] = self.db.pref_languages()
        self.cb_language.grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(frame, text="e.g. Japanese (ja)", foreground="gray").grid(
            row=0, column=2, sticky=tk.W, padx=(6, 0)
        )

        lbl("Activity Type:", 1)
        self.var_activity_type = tk.StringVar()
        self.cb_activity_type = ttk.Combobox(
            frame, textvariable=self.var_activity_type,
            values=self.db.pref_activity_types(), state="readonly", width=30,
        )
        self.cb_activity_type.grid(row=1, column=1, sticky=tk.EW)
        self.cb_activity_type.bind("<<ComboboxSelected>>", self._on_activity_type_change)

        lbl("Specific Activity:", 2)
        self.var_specific = tk.StringVar()
        self.cb_specific = ttk.Combobox(frame, textvariable=self.var_specific, width=30)
        self.cb_specific.grid(row=2, column=1, sticky=tk.EW)

        lbl("Duration (minutes):", 3)
        self.var_duration = tk.IntVar(value=30)
        ttk.Spinbox(
            frame, from_=1, to=600, increment=5,
            textvariable=self.var_duration, width=10,
        ).grid(row=3, column=1, sticky=tk.W)

        lbl("Date:", 4)
        self.var_date = tk.StringVar(value=date.today().isoformat())
        date_row = ttk.Frame(frame)
        date_row.grid(row=4, column=1, sticky=tk.W)
        ttk.Button(date_row, text="◀", width=2, command=lambda: self._shift_date(-1)).pack(side=tk.LEFT)
        self._date_entry = ttk.Entry(date_row, textvariable=self.var_date, width=12)
        self._date_entry.pack(side=tk.LEFT, padx=2)
        ttk.Button(date_row, text="▶", width=2, command=lambda: self._shift_date(1)).pack(side=tk.LEFT)
        ttk.Button(date_row, text="▼", width=2,
                   command=lambda: DatePickerPopup(self._date_entry, self.var_date)).pack(side=tk.LEFT, padx=(4, 0))

        lbl("Notes:", 5)
        self.txt_notes = tk.Text(frame, height=4, width=40, wrap=tk.WORD)
        self.txt_notes.grid(row=5, column=1, sticky=tk.EW, pady=(0, 4))
        sb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.txt_notes.yview)
        self.txt_notes.configure(yscrollcommand=sb.set)
        sb.grid(row=5, column=2, sticky=tk.NS)

        btn_bar = ttk.Frame(frame)
        btn_bar.grid(row=6, column=1, columnspan=2, sticky=tk.EW, pady=(12, 0))
        ttk.Button(btn_bar, text="Save Session", command=self.save_session).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text="Make Template", command=self._make_template).pack(side=tk.RIGHT)

        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(
            row=7, column=0, columnspan=3, sticky=tk.EW, pady=(14, 0)
        )
        tmpl_lf = ttk.LabelFrame(frame, text=" Saved Templates ", padding=(8, 6))
        tmpl_lf.grid(row=8, column=0, columnspan=3, sticky=tk.EW, pady=(4, 0))
        tmpl_lf.columnconfigure(0, weight=1)

        self.tmpl_canvas = tk.Canvas(tmpl_lf, highlightthickness=0)
        tmpl_vsb = ttk.Scrollbar(tmpl_lf, orient=tk.VERTICAL, command=self.tmpl_canvas.yview)
        self.tmpl_canvas.configure(yscrollcommand=tmpl_vsb.set)
        self.tmpl_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        tmpl_vsb.grid(row=0, column=1, sticky=tk.NS)

        self.tmpl_inner = ttk.Frame(self.tmpl_canvas)
        self._tmpl_win = self.tmpl_canvas.create_window((0, 0), window=self.tmpl_inner, anchor=tk.NW)

        self.tmpl_inner.bind("<Configure>", lambda e: self.tmpl_canvas.configure(
            scrollregion=self.tmpl_canvas.bbox("all")))
        self.tmpl_canvas.bind("<Configure>", lambda e: self.tmpl_canvas.itemconfig(
            self._tmpl_win, width=e.width))
        self.tmpl_canvas.bind("<MouseWheel>", self._tmpl_scroll)
        self.tmpl_canvas.bind("<Button-4>",   self._tmpl_scroll)
        self.tmpl_canvas.bind("<Button-5>",   self._tmpl_scroll)
        self._refresh_templates()

    def _tmpl_scroll(self, event):
        if event.num == 4:
            self.tmpl_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.tmpl_canvas.yview_scroll(1, "units")
        else:
            self.tmpl_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_tmpl_scroll(self, widget):
        widget.bind("<MouseWheel>", self._tmpl_scroll)
        widget.bind("<Button-4>",   self._tmpl_scroll)
        widget.bind("<Button-5>",   self._tmpl_scroll)
        for child in widget.winfo_children():
            self._bind_tmpl_scroll(child)

    def _on_activity_type_change(self, event=None):
        activity  = self.var_activity_type.get()
        specifics = self.db.pref_specifics(activity)
        self.cb_specific["values"] = specifics
        self.var_specific.set(specifics[0] if specifics else "")

    def _shift_date(self, days: int):
        try:
            d = datetime.strptime(self.var_date.get().strip(), "%Y-%m-%d").date()
            self.var_date.set((d + timedelta(days=days)).isoformat())
        except ValueError:
            pass

    def refresh_prefs(self):
        self.cb_language["values"]     = self.db.pref_languages()
        self.cb_activity_type["values"] = self.db.pref_activity_types()
        act = self.var_activity_type.get()
        if act:
            self.cb_specific["values"] = self.db.pref_specifics(act)

    def save_session(self):
        lang_display  = self.var_language.get().strip()
        activity_type = self.var_activity_type.get().strip()
        specific      = self.var_specific.get().strip() or None
        notes         = self.txt_notes.get("1.0", tk.END).strip() or None
        date_str      = self.var_date.get().strip()

        result = _validate_session_fields(
            lang_display, activity_type, self.var_duration.get(), date_str, self.db
        )
        if result is None:
            return
        language, duration = result

        self.db.insert_session(language, activity_type, specific, duration, date_str, notes)
        self.var_activity_type.set("")
        self.var_specific.set("")
        self.cb_specific["values"] = []
        self.var_duration.set(30)
        self.txt_notes.delete("1.0", tk.END)

    def _make_template(self):
        activity_type = self.var_activity_type.get().strip()
        if not activity_type:
            messagebox.showerror("Validation Error", "Activity Type is required to make a template.")
            return
        name = simpledialog.askstring("Template Name", "Enter a name for this template:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()

        lang_display = self.var_language.get().strip()
        language     = _extract_lang_code(lang_display) if lang_display else None
        specific     = self.var_specific.get().strip() or None
        notes        = self.txt_notes.get("1.0", tk.END).strip() or None
        try:
            duration = int(self.var_duration.get())
            if duration < 1:
                raise ValueError
        except (ValueError, tk.TclError):
            duration = 30

        try:
            self.db.insert_template(name, language, activity_type, specific, duration, notes)
            self._refresh_templates()
        except sqlite3.IntegrityError:
            messagebox.showerror("Duplicate Name", f'A template named "{name}" already exists.')

    def _apply_template(self, tid):
        row = self.db.get_template(tid)
        if not row:
            return
        lang, act, spec, dur, notes = row
        self.var_language.set(_lang_display(lang))
        self.var_activity_type.set(act)
        self._on_activity_type_change()
        self.var_specific.set(spec or "")
        self.var_duration.set(dur)
        self.var_date.set(date.today().isoformat())
        self.txt_notes.delete("1.0", tk.END)
        if notes:
            self.txt_notes.insert("1.0", notes)

    def _delete_template(self, tid):
        if messagebox.askyesno("Delete Template", "Delete this template?"):
            self.db.delete_template(tid)
            self._refresh_templates()

    def _refresh_templates(self):
        for w in self.tmpl_inner.winfo_children():
            w.destroy()
        rows = self.db.get_templates()
        if not rows:
            ttk.Label(self.tmpl_inner, text="No templates saved yet.", foreground="gray").pack(
                anchor=tk.W, padx=2, pady=2
            )
            return
        for tid, tname in rows:
            row_f = ttk.Frame(self.tmpl_inner)
            row_f.pack(fill=tk.X, pady=1)
            row_f.columnconfigure(0, weight=1)
            ttk.Button(row_f, text=tname, command=lambda t=tid: self._apply_template(t)).grid(
                row=0, column=0, sticky=tk.EW, padx=(0, 4)
            )
            ttk.Button(row_f, text="×", width=2, command=lambda t=tid: self._delete_template(t)).grid(
                row=0, column=1
            )
        self._bind_tmpl_scroll(self.tmpl_inner)


# ---------------------------------------------------------------------------
# Timer Tab
# ---------------------------------------------------------------------------

class TimerTab(ttk.Frame):
    def __init__(self, parent, log_tab: "LogTab"):
        super().__init__(parent)
        self._log_tab    = log_tab
        self._running    = False
        self._elapsed    = 0        # accumulated seconds before current run
        self._tick_start = 0.0      # monotonic time when last started/resumed
        self._after_id   = None
        self._build()

    def _build(self):
        outer = ttk.Frame(self, padding=40)
        outer.pack(expand=True)

        self.lbl_time = tk.Label(outer, text="00:00", font=("", 64, "bold"))
        self.lbl_time.pack(pady=(0, 8))

        self.lbl_status = ttk.Label(outer, text="Ready", foreground="gray")
        self.lbl_status.pack(pady=(0, 24))

        btn_row = ttk.Frame(outer)
        btn_row.pack()

        self.btn_startstop = ttk.Button(btn_row, text="Start", width=10,
                                        command=self._toggle)
        self.btn_startstop.pack(side=tk.LEFT, padx=6)

        ttk.Button(btn_row, text="Cancel", width=10,
                   command=self._cancel).pack(side=tk.LEFT, padx=6)

        ttk.Button(btn_row, text="Finish", width=10,
                   command=self._finish).pack(side=tk.LEFT, padx=6)

    def _total_seconds(self) -> int:
        if self._running:
            return self._elapsed + int(time.monotonic() - self._tick_start)
        return self._elapsed

    def _fmt(self, seconds: int) -> str:
        h, rem = divmod(seconds, 3600)
        m, s   = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"

    def _tick(self):
        self.lbl_time.config(text=self._fmt(self._total_seconds()))
        if self._running:
            self._after_id = self.after(1000, self._tick)

    def _toggle(self):
        if self._running:
            self._elapsed += int(time.monotonic() - self._tick_start)
            self._running  = False
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None
            self.btn_startstop.config(text="Resume")
            self.lbl_status.config(text="Paused")
        else:
            self._tick_start = time.monotonic()
            self._running    = True
            self.btn_startstop.config(text="Pause")
            self.lbl_status.config(text="Running…")
            self._tick()

    def _cancel(self):
        if self._running:
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None
            self._running = False
        self._elapsed = 0
        self.lbl_time.config(text="00:00")
        self.btn_startstop.config(text="Start")
        self.lbl_status.config(text="Ready")

    def _finish(self):
        if self._running:
            self._elapsed += int(time.monotonic() - self._tick_start)
            self._running  = False
            if self._after_id:
                self.after_cancel(self._after_id)
                self._after_id = None

        total = self._elapsed
        if total < 30:
            messagebox.showwarning("Timer", "Less than 30 seconds elapsed — nothing saved.")
            return

        minutes = max(1, round(total / 60))
        self._log_tab.var_duration.set(minutes)

        nb = self.master
        if isinstance(nb, ttk.Notebook):
            nb.select(self._log_tab)

        self._cancel()
        messagebox.showinfo("Timer", f"Duration set to {minutes} minute{'s' if minutes != 1 else ''} in Log Session.")


# ---------------------------------------------------------------------------
# Tab 2 — History
# ---------------------------------------------------------------------------

class HistoryTab(ttk.Frame):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db            = db
        self._tree_id_map  = {}
        self._sort_column  = "date"
        self._sort_reverse = True
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        # Filter bar
        fbar = ttk.Frame(frame)
        fbar.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 6))

        ttk.Label(fbar, text="Language:").pack(side=tk.LEFT)
        self.var_lang = tk.StringVar(value="All")
        self.cb_lang = ttk.Combobox(
            fbar, textvariable=self.var_lang, values=["All"], width=20, state="readonly"
        )
        self.cb_lang.pack(side=tk.LEFT, padx=(4, 12))
        self.cb_lang.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(fbar, text="Activity:").pack(side=tk.LEFT)
        self.var_act = tk.StringVar(value="All")
        self.cb_act = ttk.Combobox(
            fbar, textvariable=self.var_act, values=["All"], width=14, state="readonly"
        )
        self.cb_act.pack(side=tk.LEFT, padx=(4, 12))
        self.cb_act.bind("<<ComboboxSelected>>", lambda e: self.refresh())

        ttk.Label(fbar, text="From:").pack(side=tk.LEFT)
        self.var_from = tk.StringVar()
        ttk.Entry(fbar, textvariable=self.var_from, width=11).pack(side=tk.LEFT, padx=(4, 6))

        ttk.Label(fbar, text="To:").pack(side=tk.LEFT)
        self.var_to = tk.StringVar()
        ttk.Entry(fbar, textvariable=self.var_to, width=11).pack(side=tk.LEFT, padx=(4, 10))

        ttk.Button(fbar, text="Apply", command=self.refresh).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(fbar, text="Clear", command=self._clear_filter).pack(side=tk.LEFT)

        # Treeview
        columns = ("date", "language", "activity", "specific", "duration", "notes")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        col_cfg = [
            ("date",     "Date",              100),
            ("language", "Language",          140),
            ("activity", "Activity Type",     120),
            ("specific", "Specific Activity", 140),
            ("duration", "Duration (min)",    110),
            ("notes",    "Notes",             200),
        ]
        for col_id, heading, width in col_cfg:
            self.tree.heading(col_id, text=heading, command=lambda c=col_id: self._sort(c))
            self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL,   command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=1, column=0, sticky=tk.NSEW)
        vsb.grid(row=1, column=1, sticky=tk.NS)
        hsb.grid(row=2, column=0, sticky=tk.EW)
        self.tree.bind("<Double-1>", self._on_double_click)

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=3, column=0, columnspan=2, sticky=tk.EW, pady=(8, 0))
        ttk.Button(btn_row, text="Delete Selected", command=self._delete_selected).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Export as CSV",   command=self._export_csv).pack(side=tk.RIGHT)

    def _lang_code_filter(self):
        v = self.var_lang.get()
        return None if v == "All" else _extract_lang_code(v)

    def _activity_filter(self):
        v = self.var_act.get()
        return None if v == "All" else v

    def refresh(self):
        lang_codes = self.db.distinct_languages()
        lang_opts  = ["All"] + [_lang_display(c) for c in lang_codes]
        self.cb_lang["values"] = lang_opts
        self.cb_act["values"]  = ["All"] + self.db.distinct_activities()

        for item in self.tree.get_children():
            self.tree.delete(item)
        self._tree_id_map.clear()

        rows = self.db.get_sessions(
            lang_code=self._lang_code_filter(),
            activity=self._activity_filter(),
            start=self.var_from.get().strip() or None,
            end=self.var_to.get().strip() or None,
        )
        for db_id, date_val, lang, act, spec, dur, notes in rows:
            lang_disp = _lang_display(lang)
            iid = self.tree.insert(
                "", tk.END,
                values=(date_val, lang_disp, act, spec or "", dur, notes or ""),
            )
            self._tree_id_map[iid] = db_id

    def _delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Nothing selected", "Select a session to delete.")
            return
        iid   = selected[0]
        db_id = self._tree_id_map.get(iid)
        if db_id is None:
            return
        if not messagebox.askyesno("Confirm Delete", "Delete this session?"):
            return
        self.db.delete_session(db_id)
        self.tree.delete(iid)
        del self._tree_id_map[iid]

    def _sort(self, column):
        reverse = (column == self._sort_column) and not self._sort_reverse
        self._sort_column  = column
        self._sort_reverse = reverse
        items = [(self.tree.set(iid, column), iid) for iid in self.tree.get_children()]
        if column == "duration":
            items.sort(key=lambda x: int(x[0]) if x[0].isdigit() else 0, reverse=reverse)
        else:
            items.sort(reverse=reverse)
        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)

    def _clear_filter(self):
        self.var_lang.set("All")
        self.var_act.set("All")
        self.var_from.set("")
        self.var_to.set("")
        self.refresh()

    def _export_csv(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile="sessions.csv",
            title="Export sessions as CSV",
        )
        if not path:
            return
        rows = self.db.get_sessions(
            lang_code=self._lang_code_filter(),
            activity=self._activity_filter(),
            start=self.var_from.get().strip() or None,
            end=self.var_to.get().strip() or None,
        )
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Language", "Activity Type", "Specific Activity",
                             "Duration (min)", "Notes"])
            for db_id, date_val, lang, act, spec, dur, notes in rows:
                lang_disp = _lang_display(lang)
                writer.writerow([date_val, lang_disp, act, spec or "", dur, notes or ""])
        messagebox.showinfo("Export complete", f"Exported {len(rows)} session(s) to:\n{path}")

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return
        db_id = self._tree_id_map.get(item)
        if db_id is not None:
            self._open_edit_dialog(db_id)

    def _open_edit_dialog(self, db_id):
        row = self.db.get_session(db_id)
        if not row:
            return
        lang_code, act_type, spec_act, duration, date_str, notes = row

        lang_display = _lang_display(lang_code)

        dlg = tk.Toplevel(self)
        dlg.title("Edit Session")
        dlg.resizable(False, False)
        dlg.transient(self)

        frame = ttk.Frame(dlg, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        def lbl(text, r):
            ttk.Label(frame, text=text).grid(row=r, column=0, sticky=tk.W, pady=6, padx=(0, 12))

        lbl("Language:", 0)
        var_lang = tk.StringVar(value=lang_display)
        cb_lang  = ttk.Combobox(frame, textvariable=var_lang, width=28)
        cb_lang["values"] = self.db.pref_languages()
        cb_lang.grid(row=0, column=1, sticky=tk.EW)

        lbl("Activity Type:", 1)
        var_act = tk.StringVar(value=act_type or "")
        cb_act  = ttk.Combobox(
            frame, textvariable=var_act,
            values=self.db.pref_activity_types(), state="readonly", width=28,
        )
        cb_act.grid(row=1, column=1, sticky=tk.EW)

        lbl("Specific Activity:", 2)
        var_spec = tk.StringVar(value=spec_act or "")
        cb_spec  = ttk.Combobox(frame, textvariable=var_spec, width=28)
        cb_spec["values"] = self.db.pref_specifics(act_type) if act_type else []
        cb_spec.grid(row=2, column=1, sticky=tk.EW)
        cb_act.bind("<<ComboboxSelected>>",
                    lambda e: cb_spec.configure(values=self.db.pref_specifics(var_act.get())))

        lbl("Duration (min):", 3)
        var_dur = tk.StringVar(value=str(duration))
        ttk.Spinbox(frame, from_=1, to=600, increment=5, textvariable=var_dur, width=10).grid(
            row=3, column=1, sticky=tk.W
        )

        lbl("Date (YYYY-MM-DD):", 4)
        var_date = tk.StringVar(value=date_str)
        ttk.Entry(frame, textvariable=var_date, width=14).grid(row=4, column=1, sticky=tk.W)

        lbl("Notes:", 5)
        txt_notes = tk.Text(frame, height=3, width=34, wrap=tk.WORD)
        if notes:
            txt_notes.insert("1.0", notes)
        txt_notes.grid(row=5, column=1, sticky=tk.EW, pady=(0, 4))

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=6, column=0, columnspan=2, sticky=tk.E, pady=(12, 0))
        ttk.Button(
            btn_frame, text="Update",
            command=lambda: self._update_session(
                db_id, dlg, var_lang, var_act, var_spec, var_dur, var_date, txt_notes
            ),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_frame, text="Abort", command=dlg.destroy).pack(side=tk.LEFT)

        dlg.update_idletasks()
        dlg.minsize(dlg.winfo_reqwidth(), dlg.winfo_reqheight())
        dlg.grab_set()

    def _update_session(self, db_id, dlg, var_lang, var_act, var_spec, var_dur, var_date, txt_notes):
        lang_display  = var_lang.get().strip()
        activity_type = var_act.get().strip()
        specific      = var_spec.get().strip() or None
        notes         = txt_notes.get("1.0", tk.END).strip() or None
        date_str      = var_date.get().strip()

        result = _validate_session_fields(
            lang_display, activity_type, var_dur.get(), date_str, self.db, parent=dlg
        )
        if result is None:
            return
        language, duration = result

        self.db.update_session(db_id, language, activity_type, specific, duration, date_str, notes)
        dlg.destroy()
        self.refresh()


# ---------------------------------------------------------------------------
# Tab 3 — Stats
# ---------------------------------------------------------------------------

class StatsTab(ttk.Frame):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db  = db
        self.fig = None
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        self._chart_parent = frame

        self.filter_bar = FilterBar(frame, self.db, on_refresh=self.refresh)
        self.filter_bar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 8))

    def _init_chart(self):
        self.fig, self.canvas = _build_mpl_frame(
            self._chart_parent, canvas_row=1,
            left=0.08, right=0.95, bottom=0.15, top=0.88, wspace=0.4,
        )

    def refresh_prefs(self):
        self.filter_bar.refresh_lang_options()

    def refresh(self):
        if self.fig is None:
            self._init_chart()
        from matplotlib.ticker import FuncFormatter
        self.fig.clear()

        start_str = self.filter_bar.start_str
        end_str   = self.filter_bar.end_str
        grouping  = self.filter_bar.grouping

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else None
            end_date   = datetime.strptime(end_str,   "%Y-%m-%d").date() if end_str   else None
        except ValueError:
            messagebox.showerror("Invalid Date", "Dates must be in YYYY-MM-DD format.")
            return

        rows     = self.db.get_chart_rows(
            lang_code=self.filter_bar.lang_code,
            start=start_str or None,
            end=end_str or None,
        )
        ax_bar   = self.fig.add_subplot(1, 2, 1)
        ax_pie   = self.fig.add_subplot(1, 2, 2)
        prepared = _prepare_chart_data(rows, start_date, end_date, grouping,
                                       user_colors=self.db.get_activity_colors())

        if prepared is None:
            for ax in (ax_bar, ax_pie):
                ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                        transform=ax.transAxes, fontsize=12, color="gray")
                ax.set_axis_off()
            self.canvas.draw()
            return

        all_acts, color_map, p_keys, p_labels, by_act_period = prepared

        # Stacked bar chart
        x       = list(range(len(p_keys)))
        bottoms = [0.0] * len(p_keys)
        for act in all_acts:
            vals = [by_act_period[act].get(k, 0.0) for k in p_keys]
            ax_bar.bar(x, vals, bottom=bottoms, label=act, color=color_map[act])
            bottoms = [b + v for b, v in zip(bottoms, vals)]

        ax_bar.set_xticks(x)
        label_fs = max(5, min(8, 80 // max(len(p_keys), 1)))
        ax_bar.set_xticklabels(p_labels, rotation=40, ha="right", fontsize=label_fs)
        ax_bar.yaxis.set_major_formatter(FuncFormatter(lambda h, _: _fmt_time(h * 60)))
        ax_bar.set_ylabel("Duration")
        bar_title = f"Time per {grouping}"
        if self.filter_bar.lang_display != "All":
            bar_title += f"\n({self.filter_bar.lang_display})"
        ax_bar.set_title(bar_title, fontsize=9)
        ax_bar.legend(fontsize=6, loc="upper left", framealpha=0.7)

        # Pie chart
        by_act    = defaultdict(float)
        for _, act, dur in rows:
            by_act[act] += dur
        pie_labels = list(by_act.keys())
        sizes      = [by_act[l] for l in pie_labels]
        total_min  = sum(sizes)
        pie_colors = [color_map[l] for l in pie_labels]

        def _autopct(pct):
            return f"{pct:.1f}%\n{_fmt_time(pct * total_min / 100)}"

        ax_pie.pie(sizes, labels=pie_labels, colors=pie_colors,
                   autopct=_autopct, startangle=140, textprops={"fontsize": 7})
        ax_pie.set_title(f"Activity Breakdown  ·  Total: {_fmt_time(total_min)}", fontsize=9)

        self.canvas.draw()


# ---------------------------------------------------------------------------
# Tab 4 — Cumulative
# ---------------------------------------------------------------------------

class CumulativeTab(ttk.Frame):
    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db  = db
        self.fig = None
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(0, weight=1)
        self._chart_parent = frame

        self.filter_bar = FilterBar(frame, self.db, on_refresh=self.refresh)
        self.filter_bar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 4))

        self.var_summary = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.var_summary, foreground="#555555", anchor=tk.W).grid(
            row=1, column=0, sticky=tk.EW, padx=2, pady=(0, 4)
        )

    def _init_chart(self):
        self.fig, self.canvas = _build_mpl_frame(
            self._chart_parent, canvas_row=2,
            left=0.1, right=0.97, bottom=0.15, top=0.88,
        )

    def refresh_prefs(self):
        self.filter_bar.refresh_lang_options()

    def refresh(self):
        if self.fig is None:
            self._init_chart()
        from matplotlib.ticker import FuncFormatter
        self.fig.clear()

        start_str = self.filter_bar.start_str
        end_str   = self.filter_bar.end_str
        grouping  = self.filter_bar.grouping

        try:
            start_date = datetime.strptime(start_str, "%Y-%m-%d").date() if start_str else None
            end_date   = datetime.strptime(end_str,   "%Y-%m-%d").date() if end_str   else None
        except ValueError:
            messagebox.showerror("Invalid Date", "Dates must be in YYYY-MM-DD format.")
            return

        rows     = self.db.get_chart_rows(
            lang_code=self.filter_bar.lang_code,
            start=start_str or None,
            end=end_str or None,
        )
        ax       = self.fig.add_subplot(1, 1, 1)
        prepared = _prepare_chart_data(rows, start_date, end_date, grouping,
                                       user_colors=self.db.get_activity_colors())

        if prepared is None:
            self.var_summary.set("No data in the selected range.")
            ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                    transform=ax.transAxes, fontsize=12, color="gray")
            ax.set_axis_off()
            self.canvas.draw()
            return

        all_acts, color_map, p_keys, p_labels, by_act_period = prepared

        # Summary
        total_sessions = len(rows)
        total_min      = sum(dur for _, _, dur in rows)
        act_totals     = defaultdict(float)
        for _, act, dur in rows:
            act_totals[act] += dur
        top_act = max(act_totals, key=act_totals.get)
        self.var_summary.set(
            f"Sessions: {total_sessions}   ·   Total: {_fmt_time(total_min)}   ·   "
            f"Avg session: {_fmt_time(total_min / total_sessions)}   ·   Top activity: {top_act}"
        )

        # Cumulative series
        cumul   = {act: [] for act in all_acts}
        running = {act: 0.0 for act in all_acts}
        for k in p_keys:
            for act in all_acts:
                running[act] += by_act_period[act].get(k, 0.0)
                cumul[act].append(running[act])

        x = list(range(len(p_keys)))
        ax.stackplot(
            x, [cumul[act] for act in all_acts],
            labels=all_acts, colors=[color_map[act] for act in all_acts], alpha=0.85,
        )
        ax.set_xticks(x)
        label_fs = max(5, min(8, 80 // max(len(p_keys), 1)))
        ax.set_xticklabels(p_labels, rotation=40, ha="right", fontsize=label_fs)
        ax.yaxis.set_major_formatter(FuncFormatter(lambda h, _: _fmt_time(h * 60)))
        ax.set_ylabel("Cumulative Duration")
        title = f"Cumulative Time per {grouping}"
        if self.filter_bar.lang_display != "All":
            title += f"  ({self.filter_bar.lang_display})"
        ax.set_title(title, fontsize=10)
        ax.legend(fontsize=7, loc="upper left", framealpha=0.7)

        self.canvas.draw()


# ---------------------------------------------------------------------------
# Tab 5 — Learning Time
# ---------------------------------------------------------------------------

class LearningTimeTab(ttk.Frame):
    """Static reference table: how long it typically takes to learn a language,
    based on FSI difficulty categories. Highlights languages the user has
    actually logged sessions for."""

    def __init__(self, parent, db: Database):
        super().__init__(parent)
        self.db            = db
        self._sort_column  = "category"
        self._sort_reverse = False
        self._build()

    def _build(self):
        frame = ttk.Frame(self, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        ttk.Label(
            frame,
            text=("Estimated study time to reach professional working proficiency, based on the "
                  "U.S. Foreign Service Institute's language difficulty categories (assumes roughly "
                  "25 classroom hours/week; self-study usually takes longer). Rows highlighted in "
                  "green are languages you've already logged sessions for."),
            foreground="gray", wraplength=860, justify=tk.LEFT,
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        columns = ("language", "category", "hours", "weeks", "note")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        col_cfg = [
            ("language", "Language",         160),
            ("category", "FSI Category",     100),
            ("hours",    "Est. Class Hours", 120),
            ("weeks",    "Est. Weeks",       90),
            ("note",     "Notes",            320),
        ]
        for col_id, heading, width in col_cfg:
            self.tree.heading(col_id, text=heading, command=lambda c=col_id: self._sort(c))
            self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=1, column=0, sticky=tk.NSEW)
        vsb.grid(row=1, column=1, sticky=tk.NS)

        self.tree.tag_configure("studied", background="#dcf0dc")

        self.refresh()

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        studied = set(self.db.distinct_languages())
        rows = sorted(
            ((code, name) for code, name in LANGUAGES.items() if code in LANGUAGE_DIFFICULTY),
            key=lambda cn: (LANGUAGE_DIFFICULTY[cn[0]][0], cn[1]),
        )
        for code, name in rows:
            category, estimated = LANGUAGE_DIFFICULTY[code]
            info = FSI_CATEGORIES[category]
            note = info["desc"] + (" (estimated — not an official FSI rating)" if estimated else "")
            tags = ("studied",) if code in studied else ()
            self.tree.insert(
                "", tk.END,
                values=(f"{name} ({code})", category, info["hours"], info["weeks"], note),
                tags=tags,
            )
        self._sort(self._sort_column, force_reverse=self._sort_reverse)

    def _sort(self, column, force_reverse=None):
        reverse = force_reverse if force_reverse is not None else (
            (column == self._sort_column) and not self._sort_reverse
        )
        self._sort_column, self._sort_reverse = column, reverse
        items = [(self.tree.set(iid, column), iid) for iid in self.tree.get_children()]
        if column in ("hours", "weeks"):
            def num_key(pair):
                digits = "".join(ch if ch.isdigit() else " " for ch in pair[0]).split()
                return int(digits[0]) if digits else 0
            items.sort(key=num_key, reverse=reverse)
        else:
            items.sort(reverse=reverse)
        for index, (_, iid) in enumerate(items):
            self.tree.move(iid, "", index)


# ---------------------------------------------------------------------------
# Tab 6 — Settings
# ---------------------------------------------------------------------------

class SettingsTab(ttk.Frame):
    def __init__(self, parent, db: Database, on_prefs_changed):
        super().__init__(parent)
        self.db               = db
        self._on_prefs_changed = on_prefs_changed
        self._build()

    def _build(self):
        ttk.Button(self, text="Save Settings", command=self._save_all).pack(
            side=tk.BOTTOM, anchor=tk.W, padx=12, pady=(4, 8)
        )
        sub = ttk.Notebook(self)
        sub.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        st_lang  = ttk.Frame(sub)
        st_act   = ttk.Frame(sub)
        st_spec  = ttk.Frame(sub)
        st_theme = ttk.Frame(sub)

        sub.add(st_lang,  text="  Languages  ")
        sub.add(st_act,   text="  Activity Types  ")
        sub.add(st_spec,  text="  Specific Activities  ")
        sub.add(st_theme, text="  Theme  ")

        self._build_lang_tab(st_lang)
        self._build_activity_tab(st_act)
        self._build_specific_tab(st_spec)
        self._build_theme_tab(st_theme)

    def _build_theme_tab(self, parent):
        style   = ttk.Style()
        themes  = sorted(style.theme_names())
        current = style.theme_use()

        ttk.Label(parent, text="Application theme:").grid(row=0, column=0, padx=12, pady=(16, 4), sticky=tk.W)
        self.var_theme = tk.StringVar(value=current)
        cb = ttk.Combobox(parent, textvariable=self.var_theme, values=themes,
                          state="readonly", width=20)
        cb.grid(row=1, column=0, padx=12, sticky=tk.W)
        cb.bind("<<ComboboxSelected>>", self._apply_theme)

        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(
            row=2, column=0, columnspan=2, sticky=tk.EW, padx=12, pady=(16, 8)
        )
        ttk.Label(parent, text="Activity type colors:").grid(
            row=3, column=0, padx=12, pady=(0, 4), sticky=tk.W
        )

        saved = self.db.get_activity_colors()
        self._activity_colors = {}
        self._color_buttons   = {}
        for i, act in enumerate(sorted(ACTIVITIES)):
            color = saved.get(act, _CHART_COLORS[i % len(_CHART_COLORS)])
            self._activity_colors[act] = color
            row = 4 + i
            ttk.Label(parent, text=act).grid(row=row, column=0, padx=(24, 8), pady=2, sticky=tk.W)
            btn = tk.Button(
                parent, bg=color, fg=_contrasting_fg(color), text=color,
                width=9, relief="flat", command=lambda a=act: self._pick_color(a),
            )
            btn.grid(row=row, column=1, padx=(0, 12), pady=2, sticky=tk.W)
            self._color_buttons[act] = btn

    def _pick_color(self, act: str):
        current = self._activity_colors.get(act, "#ffffff")
        result  = colorchooser.askcolor(color=current, title=f"Color for {act}", parent=self)
        if result and result[1]:
            color = result[1]
            self._activity_colors[act] = color
            self._color_buttons[act].config(bg=color, fg=_contrasting_fg(color), text=color)

    def _save_activity_colors(self):
        self.db.save_activity_colors(self._activity_colors)

    def _apply_theme(self, event=None):
        ttk.Style().theme_use(self.var_theme.get())

    def _save_all(self):
        self._save_lang()
        self._save_activity()
        self._save_specific()
        self._save_activity_colors()
        self._on_prefs_changed()
        messagebox.showinfo("Saved", "Settings saved.")

    # -- Languages --

    def _build_lang_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        ttk.Label(
            frame,
            text="Select the languages you study. If none selected, all are shown in the Log form.",
            foreground="gray",
        ).grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 6))

        lb_frame = ttk.Frame(frame)
        lb_frame.grid(row=1, column=0, sticky=tk.NSEW)
        lb_frame.rowconfigure(0, weight=1)
        lb_frame.columnconfigure(0, weight=1)

        self.lb_languages = tk.Listbox(lb_frame, selectmode=tk.MULTIPLE, width=36, exportselection=False)
        vsb = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL, command=self.lb_languages.yview)
        self.lb_languages.configure(yscrollcommand=vsb.set)
        self.lb_languages.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)

        enabled_codes = self.db.enabled_lang_codes()
        for i, opt in enumerate(LANGUAGE_OPTIONS):
            self.lb_languages.insert(tk.END, opt)
            if _extract_lang_code(opt) in enabled_codes:
                self.lb_languages.selection_set(i)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Button(btn_frame, text="Select All",
                   command=lambda: self.lb_languages.selection_set(0, tk.END)).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(btn_frame, text="Clear All",
                   command=lambda: self.lb_languages.selection_clear(0, tk.END)).pack(side=tk.LEFT)

    def _save_lang(self):
        selected = {_extract_lang_code(LANGUAGE_OPTIONS[i]) for i in self.lb_languages.curselection()}
        self.db.save_lang_prefs(selected)

    # -- Activity Types --

    def _build_activity_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Choose which activity types appear in the Log Session form.",
            foreground="gray",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        enabled = self.db.enabled_activity_names()
        self._act_vars = {}
        for i, name in enumerate(ACTIVITIES):
            var = tk.BooleanVar(value=name in enabled)
            self._act_vars[name] = var
            ttk.Checkbutton(frame, text=name, variable=var).grid(row=i + 1, column=0, sticky=tk.W, pady=3)

    def _save_activity(self):
        self.db.save_activity_prefs({name: var.get() for name, var in self._act_vars.items()})

    # -- Specific Activities --

    def _build_specific_tab(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Select which specific activities appear. Add custom ones with the entry below.",
            foreground="gray",
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        left = ttk.LabelFrame(frame, text="Activity Type", padding=6)
        left.grid(row=1, column=0, sticky=tk.NSEW, padx=(0, 8))
        left.rowconfigure(0, weight=1)

        self.lb_act_sel = tk.Listbox(left, width=16, exportselection=False)
        act_vsb = ttk.Scrollbar(left, orient=tk.VERTICAL, command=self.lb_act_sel.yview)
        self.lb_act_sel.configure(yscrollcommand=act_vsb.set)
        self.lb_act_sel.grid(row=0, column=0, sticky=tk.NSEW)
        act_vsb.grid(row=0, column=1, sticky=tk.NS)
        for at in ACTIVITIES:
            self.lb_act_sel.insert(tk.END, at)

        right = ttk.LabelFrame(frame, text="Specific Activities  (selected = enabled)", padding=6)
        right.grid(row=1, column=1, sticky=tk.NSEW)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.lb_specifics = tk.Listbox(right, selectmode=tk.MULTIPLE, width=26, exportselection=False)
        sp_vsb = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.lb_specifics.yview)
        self.lb_specifics.configure(yscrollcommand=sp_vsb.set)
        self.lb_specifics.grid(row=0, column=0, sticky=tk.NSEW)
        sp_vsb.grid(row=0, column=1, sticky=tk.NS)

        add_fr = ttk.Frame(right)
        add_fr.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
        self.var_new_spec = tk.StringVar()
        ttk.Entry(add_fr, textvariable=self.var_new_spec, width=18).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(add_fr, text="Add", command=self._add_specific).pack(side=tk.LEFT)

        ttk.Button(right, text="Remove Selected", command=self._remove_specific).grid(
            row=2, column=0, sticky=tk.W, pady=(4, 0)
        )

        self._spec_state        = self.db.load_spec_state()
        self._spec_current_type = None

        self.lb_act_sel.bind("<<ListboxSelect>>", self._on_spec_type_select)
        if self.lb_act_sel.size() > 0:
            self.lb_act_sel.selection_set(0)
            self._on_spec_type_select()

    def _on_spec_type_select(self, event=None):
        sel = self.lb_act_sel.curselection()
        if not sel:
            return
        new_type = self.lb_act_sel.get(sel[0])
        if self._spec_current_type in self._spec_state:
            items = self._spec_state[self._spec_current_type]["items"]
            self._spec_state[self._spec_current_type]["selected"] = {
                items[i][0] for i in self.lb_specifics.curselection()
            }
        self._spec_current_type = new_type
        self._refresh_spec_listbox()

    def _refresh_spec_listbox(self):
        self.lb_specifics.delete(0, tk.END)
        if self._spec_current_type not in self._spec_state:
            return
        state = self._spec_state[self._spec_current_type]
        for name, is_custom in state["items"]:
            self.lb_specifics.insert(tk.END, f"{name} *" if is_custom else name)
        for i, (name, _) in enumerate(state["items"]):
            if name in state["selected"]:
                self.lb_specifics.selection_set(i)

    def _add_specific(self):
        name = self.var_new_spec.get().strip()
        if not name or not self._spec_current_type:
            return
        state    = self._spec_state[self._spec_current_type]
        existing = {item[0] for item in state["items"]}
        if name in existing:
            messagebox.showwarning("Duplicate", f'"{name}" already exists.')
            return
        state["items"].append((name, True))
        state["selected"].add(name)
        self._refresh_spec_listbox()
        self.var_new_spec.set("")

    def _remove_specific(self):
        sel = self.lb_specifics.curselection()
        if not sel or not self._spec_current_type:
            return
        state = self._spec_state[self._spec_current_type]
        for i in reversed(sel):
            name, _ = state["items"][i]
            state["items"].pop(i)
            state["selected"].discard(name)
        self._refresh_spec_listbox()

    def _save_specific(self):
        if self._spec_current_type in self._spec_state:
            items = self._spec_state[self._spec_current_type]["items"]
            self._spec_state[self._spec_current_type]["selected"] = {
                items[i][0] for i in self.lb_specifics.curselection()
            }
        self.db.save_specific_prefs(self._spec_state)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

def _preload_matplotlib():
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure  # noqa: F401
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk  # noqa: F401
    from matplotlib.ticker import FuncFormatter  # noqa: F401


class LanguageLoggerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        threading.Thread(target=_preload_matplotlib, daemon=True).start()

        self.title("Language Learning Logger")
        self.geometry("920x620")
        self.minsize(740, 520)

        db = Database(DB_PATH)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_log      = LogTab(self.notebook, db)
        self.tab_timer    = TimerTab(self.notebook, self.tab_log)
        self.tab_history  = HistoryTab(self.notebook, db)
        self.tab_stats     = StatsTab(self.notebook, db)
        self.tab_cumul     = CumulativeTab(self.notebook, db)
        self.tab_learntime = LearningTimeTab(self.notebook, db)
        self.tab_settings  = SettingsTab(self.notebook, db, on_prefs_changed=self._on_prefs_changed)

        self.notebook.add(self.tab_log,       text="  Log Session  ")
        self.notebook.add(self.tab_history,   text="  History  ")
        self.notebook.add(self.tab_stats,     text="  Stats  ")
        self.notebook.add(self.tab_cumul,     text="  Cumulative  ")
        self.notebook.add(self.tab_learntime, text="  Learning Time  ")
        self.notebook.add(self.tab_settings,  text="  Settings  ")
        self.notebook.add(self.tab_timer,     text="  Timer  ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)
        self.bind("<Control-s>", self._on_ctrl_s)

    def _on_ctrl_s(self, event=None):
        selected = self.notebook.select()
        if selected == str(self.tab_log):
            self.tab_log.save_session()
        elif selected == str(self.tab_settings):
            self.tab_settings._save_all()

    def _on_prefs_changed(self):
        self.tab_log.refresh_prefs()
        self.tab_stats.refresh_prefs()
        self.tab_cumul.refresh_prefs()

    def _on_tab_change(self, event):
        selected = self.notebook.select()
        if selected == str(self.tab_history):
            self.tab_history.refresh()
        elif selected == str(self.tab_stats):
            self.tab_stats.refresh()
        elif selected == str(self.tab_cumul):
            self.tab_cumul.refresh()
        elif selected == str(self.tab_learntime):
            self.tab_learntime.refresh()


def _cli_list_templates():
    db = Database(DB_PATH)
    rows = db.get_templates()
    if not rows:
        print("No templates saved yet.")
        return
    for tid, tname in rows:
        row = db.get_template(tid)
        lang, act, spec, dur, notes = row
        lang_display = _lang_display(lang) if lang else "(no language)"
        detail = f"{lang_display} | {act}"
        if spec:
            detail += f" / {spec}"
        detail += f" | {dur} min"
        print(f"{tname}: {detail}")


def _cli_log():
    """Log a session from CLI args and exit, no GUI."""
    try:
        datetime.strptime(_ARGS.date, "%Y-%m-%d")
    except ValueError:
        sys.exit(f"Error: --date must be YYYY-MM-DD, got {_ARGS.date!r}")

    db = Database(DB_PATH)
    row = db.get_template_by_name(_ARGS.template)
    if row is None:
        names = [r[1] for r in db.get_templates()]
        if names:
            sys.exit(f"Error: template {_ARGS.template!r} not found. Available: {', '.join(names)}")
        else:
            sys.exit(f"Error: template {_ARGS.template!r} not found. No templates saved yet.")

    language, activity_type, specific, duration, notes = row
    if _ARGS.duration is not None:
        if _ARGS.duration < 1:
            sys.exit("Error: --duration must be a positive integer")
        duration = _ARGS.duration

    db.insert_session(language, activity_type, specific, duration, _ARGS.date, notes)
    lang_display = _lang_display(language) if language else "(no language)"
    print(f"Logged: {lang_display} | {activity_type}"
          + (f" / {specific}" if specific else "")
          + f" | {duration} min | {_ARGS.date}")


if __name__ == "__main__":
    if _ARGS.list_templates:
        _cli_list_templates()
    elif _ARGS.template:
        _cli_log()
    else:
        app = LanguageLoggerApp()
        app.mainloop()
