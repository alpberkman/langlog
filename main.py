import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
import os
from datetime import date, timedelta, datetime
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions.db")

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


def _extract_lang_code(display_value: str) -> str:
    if display_value.endswith(")") and "(" in display_value:
        return display_value.rsplit("(", 1)[-1].rstrip(")")
    return display_value.strip()


class LanguageLoggerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Language Learning Logger")
        self.geometry("920x620")
        self.minsize(740, 520)
        self._init_db()
        self._build_ui()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self):
        self.conn = sqlite3.connect(DB_PATH)
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
        """)
        self.conn.commit()
        self._seed_prefs()

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
            rows = [
                (act, spec, 1, 0)
                for act, specs in ACTIVITIES.items()
                for spec in specs
            ]
            self.conn.executemany(
                "INSERT OR IGNORE INTO pref_specific_activities VALUES (?, ?, ?, ?)",
                rows,
            )
        self.conn.commit()

    # -- preference readers --

    def _pref_languages(self):
        """Display strings for enabled languages; falls back to all if none enabled."""
        enabled = {r[0] for r in self.conn.execute(
            "SELECT code FROM pref_languages WHERE enabled=1"
        )}
        if not enabled:
            return LANGUAGE_OPTIONS
        return [o for o in LANGUAGE_OPTIONS if _extract_lang_code(o) in enabled]

    def _pref_activity_types(self):
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM pref_activity_types WHERE enabled=1"
        )]

    def _pref_specifics(self, activity_type: str):
        return [r[0] for r in self.conn.execute(
            "SELECT name FROM pref_specific_activities "
            "WHERE activity_type=? AND enabled=1 ORDER BY is_custom, name",
            (activity_type,),
        )]

    # ------------------------------------------------------------------
    # UI skeleton
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_log      = ttk.Frame(self.notebook)
        self.tab_history  = ttk.Frame(self.notebook)
        self.tab_stats    = ttk.Frame(self.notebook)
        self.tab_settings = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_log,      text="  Log Session  ")
        self.notebook.add(self.tab_history,  text="  History  ")
        self.notebook.add(self.tab_stats,    text="  Stats  ")
        self.notebook.add(self.tab_settings, text="  Settings  ")

        self._build_log_tab()
        self._build_history_tab()
        self._build_stats_tab()
        self._build_settings_tab()

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        tab = self.notebook.index(self.notebook.select())
        if tab == 1:
            self.load_history()
        elif tab == 2:
            self.refresh_stats()

    # ------------------------------------------------------------------
    # Tab 1 — Log Session
    # ------------------------------------------------------------------

    def _build_log_tab(self):
        frame = ttk.Frame(self.tab_log, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        def lbl(text, r):
            ttk.Label(frame, text=text).grid(row=r, column=0, sticky=tk.W, pady=6, padx=(0, 12))

        lbl("Language:", 0)
        self.var_language = tk.StringVar()
        self.cb_language = ttk.Combobox(frame, textvariable=self.var_language, width=30)
        self.cb_language["values"] = self._pref_languages()
        self.cb_language.grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(frame, text="e.g. Japanese (ja)", foreground="gray").grid(
            row=0, column=2, sticky=tk.W, padx=(6, 0)
        )

        lbl("Activity Type:", 1)
        self.var_activity_type = tk.StringVar()
        self.cb_activity_type = ttk.Combobox(
            frame, textvariable=self.var_activity_type,
            values=self._pref_activity_types(), state="readonly", width=30,
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

        ttk.Button(frame, text="Save Session", command=self.save_session).grid(
            row=6, column=1, sticky=tk.W, pady=(12, 0)
        )

    def _on_activity_type_change(self, event=None):
        activity = self.var_activity_type.get()
        specifics = self._pref_specifics(activity)
        self.cb_specific["values"] = specifics
        self.var_specific.set(specifics[0] if specifics else "")

    def _refresh_log_form(self):
        self.cb_language["values"] = self._pref_languages()
        self.cb_activity_type["values"] = self._pref_activity_types()
        act = self.var_activity_type.get()
        if act:
            specs = self._pref_specifics(act)
            self.cb_specific["values"] = specs

    def save_session(self):
        lang_display = self.var_language.get().strip()
        language     = _extract_lang_code(lang_display) if lang_display else None
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

        self.conn.execute(
            "INSERT INTO sessions "
            "(language, activity_type, specific_activity, duration_minutes, date, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (language, activity_type, specific, duration, date_str, notes),
        )
        self.conn.commit()

        self.var_activity_type.set("")
        self.var_specific.set("")
        self.cb_specific["values"] = []
        self.var_duration.set(30)
        self.txt_notes.delete("1.0", tk.END)

    # ------------------------------------------------------------------
    # Tab 2 — History
    # ------------------------------------------------------------------

    def _build_history_tab(self):
        frame = ttk.Frame(self.tab_history, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        columns = ("date", "language", "activity", "specific", "duration", "notes")
        self.tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")

        col_cfg = [
            ("date",     "Date",              100),
            ("language", "Language",          90),
            ("activity", "Activity Type",     120),
            ("specific", "Specific Activity", 140),
            ("duration", "Duration (min)",    110),
            ("notes",    "Notes",             200),
        ]
        for col_id, heading, width in col_cfg:
            self.tree.heading(col_id, text=heading,
                              command=lambda c=col_id: self._sort_tree(c))
            self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL,   command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)

        ttk.Button(frame, text="Delete Selected", command=self.delete_session).grid(
            row=2, column=0, sticky=tk.W, pady=(8, 0)
        )

        self._tree_id_map   = {}
        self._sort_column   = "date"
        self._sort_reverse  = True

    def load_history(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._tree_id_map.clear()

        cur = self.conn.execute(
            "SELECT id, date, language, activity_type, specific_activity, duration_minutes, notes "
            "FROM sessions ORDER BY date DESC"
        )
        for row in cur.fetchall():
            db_id, date_val, lang, act, spec, dur, notes = row
            iid = self.tree.insert(
                "", tk.END,
                values=(date_val, lang or "", act, spec or "", dur, notes or ""),
            )
            self._tree_id_map[iid] = db_id

    def delete_session(self):
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
        self.conn.execute("DELETE FROM sessions WHERE id=?", (db_id,))
        self.conn.commit()
        self.tree.delete(iid)
        del self._tree_id_map[iid]

    def _sort_tree(self, column):
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

    # ------------------------------------------------------------------
    # Tab 3 — Stats
    # ------------------------------------------------------------------

    def _build_stats_tab(self):
        frame = ttk.Frame(self.tab_stats, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        self.fig = Figure(figsize=(8, 4), dpi=96)
        self.fig.subplots_adjust(left=0.08, right=0.95, bottom=0.15, top=0.88, wspace=0.35)

        self.canvas = FigureCanvasTkAgg(self.fig, master=frame)
        self.canvas.get_tk_widget().grid(row=0, column=0, sticky=tk.NSEW)

        toolbar_frame = ttk.Frame(frame)
        toolbar_frame.grid(row=1, column=0, sticky=tk.EW)
        NavigationToolbar2Tk(self.canvas, toolbar_frame)

        ttk.Button(frame, text="Refresh", command=self.refresh_stats).grid(
            row=2, column=0, sticky=tk.W, pady=(4, 0)
        )

    def refresh_stats(self):
        self.fig.clear()
        rows = self.conn.execute(
            "SELECT date, activity_type, duration_minutes FROM sessions"
        ).fetchall()

        ax_bar = self.fig.add_subplot(1, 2, 1)
        ax_pie = self.fig.add_subplot(1, 2, 2)

        if not rows:
            for ax in (ax_bar, ax_pie):
                ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                        transform=ax.transAxes, fontsize=12, color="gray")
                ax.set_axis_off()
            self.canvas.draw()
            return

        today = date.today()
        weeks, week_hours = [], []
        for i in range(7, -1, -1):
            week_start = today - timedelta(days=today.weekday() + 7 * i)
            week_end   = week_start + timedelta(days=6)
            label      = week_start.strftime("%b %d")
            total_min  = sum(
                dur for d, _, dur in rows
                if week_start.isoformat() <= d <= week_end.isoformat()
            )
            weeks.append(label)
            week_hours.append(round(total_min / 60, 2))

        bars = ax_bar.bar(range(len(weeks)), week_hours, color="#4a90d9")
        ax_bar.set_xticks(range(len(weeks)))
        ax_bar.set_xticklabels(weeks, rotation=40, ha="right", fontsize=7)
        ax_bar.set_ylabel("Hours")
        ax_bar.set_title("Hours per Week (last 8 weeks)")
        for bar, val in zip(bars, week_hours):
            if val > 0:
                ax_bar.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=7,
                )

        from collections import defaultdict
        by_activity = defaultdict(int)
        for _, act, dur in rows:
            by_activity[act] += dur
        labels = list(by_activity.keys())
        sizes  = [by_activity[l] for l in labels]
        ax_pie.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140)
        ax_pie.set_title("Time by Activity Type")

        self.canvas.draw()

    # ------------------------------------------------------------------
    # Tab 4 — Settings
    # ------------------------------------------------------------------

    def _save_all_prefs(self):
        self._save_lang_prefs()
        self._save_activity_prefs()
        self._save_specific_prefs()
        messagebox.showinfo("Saved", "Settings saved.")

    def _build_settings_tab(self):
        ttk.Button(self.tab_settings, text="Save Settings", command=self._save_all_prefs).pack(
            side=tk.BOTTOM, anchor=tk.W, padx=12, pady=(4, 8)
        )
        sub = ttk.Notebook(self.tab_settings)
        sub.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 0))

        st_lang = ttk.Frame(sub)
        st_act  = ttk.Frame(sub)
        st_spec = ttk.Frame(sub)

        sub.add(st_lang, text="  Languages  ")
        sub.add(st_act,  text="  Activity Types  ")
        sub.add(st_spec, text="  Specific Activities  ")

        self._build_lang_settings(st_lang)
        self._build_activity_settings(st_act)
        self._build_specific_settings(st_spec)

    # -- Languages sub-tab --

    def _build_lang_settings(self, parent):
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

        self.lb_languages = tk.Listbox(
            lb_frame, selectmode=tk.MULTIPLE, width=36, exportselection=False
        )
        vsb = ttk.Scrollbar(lb_frame, orient=tk.VERTICAL, command=self.lb_languages.yview)
        self.lb_languages.configure(yscrollcommand=vsb.set)
        self.lb_languages.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)

        enabled_codes = {r[0] for r in self.conn.execute(
            "SELECT code FROM pref_languages WHERE enabled=1"
        )}
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

    def _save_lang_prefs(self):
        selected = {_extract_lang_code(LANGUAGE_OPTIONS[i])
                    for i in self.lb_languages.curselection()}
        self.conn.executemany(
            "INSERT OR REPLACE INTO pref_languages (code, enabled) VALUES (?, ?)",
            [(code, 1 if code in selected else 0) for code in LANGUAGES],
        )
        self.conn.commit()
        self._refresh_log_form()

    # -- Activity Types sub-tab --

    def _build_activity_settings(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(
            frame,
            text="Choose which activity types appear in the Log Session form.",
            foreground="gray",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 10))

        enabled = {r[0] for r in self.conn.execute(
            "SELECT name FROM pref_activity_types WHERE enabled=1"
        )}
        self._act_vars = {}
        for i, name in enumerate(ACTIVITIES):
            var = tk.BooleanVar(value=name in enabled)
            self._act_vars[name] = var
            ttk.Checkbutton(frame, text=name, variable=var).grid(
                row=i + 1, column=0, sticky=tk.W, pady=3
            )

    def _save_activity_prefs(self):
        self.conn.executemany(
            "INSERT OR REPLACE INTO pref_activity_types (name, enabled) VALUES (?, ?)",
            [(name, 1 if var.get() else 0) for name, var in self._act_vars.items()],
        )
        self.conn.commit()
        self._refresh_log_form()

    # -- Specific Activities sub-tab --

    def _build_specific_settings(self, parent):
        frame = ttk.Frame(parent, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="Select which specific activities appear. Add custom ones with the entry below.",
            foreground="gray",
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        # Left: activity type selector
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

        # Right: specific activities for selected type
        right = ttk.LabelFrame(frame, text="Specific Activities  (selected = enabled)", padding=6)
        right.grid(row=1, column=1, sticky=tk.NSEW)
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.lb_specifics = tk.Listbox(
            right, selectmode=tk.MULTIPLE, width=26, exportselection=False
        )
        sp_vsb = ttk.Scrollbar(right, orient=tk.VERTICAL, command=self.lb_specifics.yview)
        self.lb_specifics.configure(yscrollcommand=sp_vsb.set)
        self.lb_specifics.grid(row=0, column=0, sticky=tk.NSEW)
        sp_vsb.grid(row=0, column=1, sticky=tk.NS)

        add_fr = ttk.Frame(right)
        add_fr.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(6, 0))
        self.var_new_spec = tk.StringVar()
        ttk.Entry(add_fr, textvariable=self.var_new_spec, width=18).pack(
            side=tk.LEFT, padx=(0, 4)
        )
        ttk.Button(add_fr, text="Add", command=self._add_specific).pack(side=tk.LEFT)

        ttk.Button(right, text="Remove Selected", command=self._remove_specific).grid(
            row=2, column=0, sticky=tk.W, pady=(4, 0)
        )

        # In-memory state: {activity_type: {"items": [(name, is_custom)], "selected": set}}
        self._spec_state        = {}
        self._spec_current_type = None
        self._load_spec_state()

        self.lb_act_sel.bind("<<ListboxSelect>>", self._on_spec_type_select)
        if self.lb_act_sel.size() > 0:
            self.lb_act_sel.selection_set(0)
            self._on_spec_type_select()

    def _load_spec_state(self):
        for act_type in ACTIVITIES:
            rows = self.conn.execute(
                "SELECT name, is_custom, enabled FROM pref_specific_activities "
                "WHERE activity_type=? ORDER BY is_custom, name",
                (act_type,),
            ).fetchall()
            self._spec_state[act_type] = {
                "items":    [(r[0], bool(r[1])) for r in rows],
                "selected": {r[0] for r in rows if r[2]},
            }

    def _on_spec_type_select(self, event=None):
        sel = self.lb_act_sel.curselection()
        if not sel:
            return
        new_type = self.lb_act_sel.get(sel[0])
        # Persist current right-panel selection before switching
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

    def _save_specific_prefs(self):
        # Flush the currently visible right-panel selections into state
        if self._spec_current_type in self._spec_state:
            items = self._spec_state[self._spec_current_type]["items"]
            self._spec_state[self._spec_current_type]["selected"] = {
                items[i][0] for i in self.lb_specifics.curselection()
            }

        for act_type, state in self._spec_state.items():
            existing_in_db = {r[0] for r in self.conn.execute(
                "SELECT name FROM pref_specific_activities WHERE activity_type=?",
                (act_type,),
            )}
            current_names = {item[0] for item in state["items"]}

            # Remove items deleted from the list
            for name in existing_in_db - current_names:
                self.conn.execute(
                    "DELETE FROM pref_specific_activities WHERE activity_type=? AND name=?",
                    (act_type, name),
                )

            # Upsert remaining
            for name, is_custom in state["items"]:
                enabled = 1 if name in state["selected"] else 0
                self.conn.execute(
                    "INSERT OR REPLACE INTO pref_specific_activities "
                    "(activity_type, name, enabled, is_custom) VALUES (?, ?, ?, ?)",
                    (act_type, name, enabled, 1 if is_custom else 0),
                )

        self.conn.commit()
        self._refresh_log_form()


if __name__ == "__main__":
    app = LanguageLoggerApp()
    app.mainloop()
