#!/usr/bin/env python

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import sqlite3
import csv
import os
import sys
import threading
from collections import defaultdict
from datetime import date, timedelta, datetime

DB_PATH = (
    sys.argv[1]
    if len(sys.argv) > 1
    else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.db")
)

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


def _prepare_chart_data(rows, start_date, end_date, grouping):
    """Shared computation for Stats and Cumulative charts. Returns None when rows is empty."""
    if not rows:
        return None
    all_acts  = sorted(set(act for _, act, _ in rows))
    color_map = {act: _CHART_COLORS[i % len(_CHART_COLORS)] for i, act in enumerate(all_acts)}
    data_dates = [datetime.strptime(r[0], "%Y-%m-%d").date() for r in rows]
    eff_start  = start_date or min(data_dates)
    eff_end    = end_date   or max(data_dates)
    periods    = _all_periods(eff_start, eff_end, grouping)
    p_keys     = [p[0] for p in periods]
    p_labels   = [p[1] for p in periods]
    by_act_period = defaultdict(lambda: defaultdict(float))
    for d_str, act, dur in rows:
        by_act_period[act][_period_key(d_str, grouping)] += dur / 60
    return all_acts, color_map, p_keys, p_labels, by_act_period


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

class Database:
    def __init__(self, path: str):
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
        if lang_code:
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
            values=["All"] + self.db.pref_languages(), width=_lang_w, state="readonly",
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
        self.cb_lang["values"] = ["All"] + self.db.pref_languages()

    @property
    def lang_code(self):
        v = self.var_lang.get()
        return None if v == "All" else _extract_lang_code(v)

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

        lbl("Date (YYYY-MM-DD):", 4)
        self.var_date = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(frame, textvariable=self.var_date, width=14).grid(row=4, column=1, sticky=tk.W)

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

    def refresh_prefs(self):
        self.cb_language["values"]     = self.db.pref_languages()
        self.cb_activity_type["values"] = self.db.pref_activity_types()
        act = self.var_activity_type.get()
        if act:
            self.cb_specific["values"] = self.db.pref_specifics(act)

    def save_session(self):
        lang_display  = self.var_language.get().strip()
        language      = _extract_lang_code(lang_display) if lang_display else None
        activity_type = self.var_activity_type.get().strip()
        specific      = self.var_specific.get().strip() or None
        notes         = self.txt_notes.get("1.0", tk.END).strip() or None

        try:
            duration = int(self.var_duration.get())
            if duration < 1:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Validation Error", "Duration must be a positive integer.")
            return

        date_str = self.var_date.get().strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Validation Error", "Date must be in YYYY-MM-DD format.")
            return

        if not activity_type:
            messagebox.showerror("Validation Error", "Activity Type is required.")
            return

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
        if lang:
            lang_name = LANGUAGES.get(lang, "")
            self.var_language.set(f"{lang_name} ({lang})" if lang_name else lang)
        else:
            self.var_language.set("")
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
        lang_opts  = ["All"] + [
            (f"{LANGUAGES[c]} ({c})" if c in LANGUAGES else c) for c in lang_codes
        ]
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
            lang_disp = (f"{LANGUAGES[lang]} ({lang})" if lang in LANGUAGES else lang) if lang else ""
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
                lang_disp = (f"{LANGUAGES[lang]} ({lang})" if lang in LANGUAGES else lang) if lang else ""
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

        lang_display = ""
        if lang_code:
            name = LANGUAGES.get(lang_code, "")
            lang_display = f"{name} ({lang_code})" if name else lang_code

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
        language      = _extract_lang_code(lang_display) if lang_display else None
        activity_type = var_act.get().strip()
        specific      = var_spec.get().strip() or None
        notes         = txt_notes.get("1.0", tk.END).strip() or None

        if not activity_type:
            messagebox.showerror("Validation Error", "Activity Type is required.", parent=dlg)
            return
        try:
            duration = int(float(var_dur.get()))
            if duration < 1:
                raise ValueError
        except (ValueError, tk.TclError):
            messagebox.showerror("Validation Error", "Duration must be a positive integer.", parent=dlg)
            return
        try:
            datetime.strptime(var_date.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Validation Error", "Date must be in YYYY-MM-DD format.", parent=dlg)
            return

        self.db.update_session(
            db_id, language, activity_type, specific, duration, var_date.get().strip(), notes
        )
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
        import matplotlib
        matplotlib.use("TkAgg")
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        frame = self._chart_parent
        self.fig = Figure(figsize=(8, 4), dpi=96)
        self.fig.subplots_adjust(left=0.08, right=0.95, bottom=0.15, top=0.88, wspace=0.4)
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.get_tk_widget().grid(row=1, column=0, sticky=tk.NSEW)
        toolbar_frame = ttk.Frame(frame)
        toolbar_frame.grid(row=2, column=0, sticky=tk.EW)
        NavigationToolbar2Tk(self.canvas, toolbar_frame)

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
        prepared = _prepare_chart_data(rows, start_date, end_date, grouping)

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
        import matplotlib
        matplotlib.use("TkAgg")
        from matplotlib.figure import Figure
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        frame = self._chart_parent
        self.fig = Figure(figsize=(8, 4), dpi=96)
        self.fig.subplots_adjust(left=0.1, right=0.97, bottom=0.15, top=0.88)
        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.get_tk_widget().grid(row=2, column=0, sticky=tk.NSEW)
        toolbar_frame = ttk.Frame(frame)
        toolbar_frame.grid(row=3, column=0, sticky=tk.EW)
        NavigationToolbar2Tk(self.canvas, toolbar_frame)

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
        prepared = _prepare_chart_data(rows, start_date, end_date, grouping)

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
# Tab 5 — Settings
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

    def _apply_theme(self, event=None):
        ttk.Style().theme_use(self.var_theme.get())

    def _save_all(self):
        self._save_lang()
        self._save_activity()
        self._save_specific()
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
        self.title("Language Learning Logger")
        self.geometry("920x620")
        self.minsize(740, 520)

        db = Database(DB_PATH)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_log      = LogTab(self.notebook, db)
        self.tab_history  = HistoryTab(self.notebook, db)
        self.tab_stats    = StatsTab(self.notebook, db)
        self.tab_cumul    = CumulativeTab(self.notebook, db)
        self.tab_settings = SettingsTab(self.notebook, db, on_prefs_changed=self._on_prefs_changed)

        self.notebook.add(self.tab_log,      text="  Log Session  ")
        self.notebook.add(self.tab_history,  text="  History  ")
        self.notebook.add(self.tab_stats,    text="  Stats  ")
        self.notebook.add(self.tab_cumul,    text="  Cumulative  ")
        self.notebook.add(self.tab_settings, text="  Settings  ")

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)
        self.bind("<Control-s>", self._on_ctrl_s)

        threading.Thread(target=_preload_matplotlib, daemon=True).start()

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


if __name__ == "__main__":
    app = LanguageLoggerApp()
    app.mainloop()
