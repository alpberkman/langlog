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

# ISO 639-1 code → language name (common subset)
LANGUAGES = {
    "af": "Afrikaans", "sq": "Albanian", "ar": "Arabic", "hy": "Armenian",
    "az": "Azerbaijani", "eu": "Basque", "be": "Belarusian", "bn": "Bengali",
    "bs": "Bosnian", "bg": "Bulgarian", "ca": "Catalan", "zh": "Chinese",
    "hr": "Croatian", "cs": "Czech", "da": "Danish", "nl": "Dutch",
    "en": "English", "et": "Estonian", "fi": "Finnish", "fr": "French",
    "gl": "Galician", "ka": "Georgian", "de": "German", "el": "Greek",
    "gu": "Gujarati", "ht": "Haitian Creole", "he": "Hebrew", "hi": "Hindi",
    "hu": "Hungarian", "is": "Icelandic", "id": "Indonesian", "ga": "Irish",
    "it": "Italian", "ja": "Japanese", "kn": "Kannada", "kk": "Kazakh",
    "ko": "Korean", "ku": "Kurdish", "lv": "Latvian", "lt": "Lithuanian",
    "mk": "Macedonian", "ms": "Malay", "ml": "Malayalam", "mt": "Maltese",
    "mr": "Marathi", "mn": "Mongolian", "ne": "Nepali", "no": "Norwegian",
    "fa": "Persian", "pl": "Polish", "pt": "Portuguese", "pa": "Punjabi",
    "ro": "Romanian", "ru": "Russian", "sr": "Serbian", "sk": "Slovak",
    "sl": "Slovenian", "es": "Spanish", "sw": "Swahili", "sv": "Swedish",
    "tl": "Tagalog", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu", "uz": "Uzbek",
    "vi": "Vietnamese", "cy": "Welsh", "yi": "Yiddish",
}
# Display values for the combobox: "Japanese (ja)", sorted by name
LANGUAGE_OPTIONS = sorted(
    [f"{name} ({code})" for code, name in LANGUAGES.items()],
    key=lambda s: s.lower(),
)


def _extract_lang_code(display_value: str) -> str:
    """Return the ISO code from 'Japanese (ja)', or the raw value if typed manually."""
    if display_value.endswith(")") and "(" in display_value:
        return display_value.rsplit("(", 1)[-1].rstrip(")")
    return display_value.strip()


ACTIVITIES = {
    "Listening":  ["Podcast", "Audiobook", "Music", "Radio", "TV/Video", "Movie", "Other"],
    "Reading":    ["Book", "Article", "News", "Manga/Comic", "Subtitles", "Other"],
    "Speaking":   ["Conversation", "Language Exchange", "Tutor/Class", "Shadowing", "Monologue", "Other"],
    "Writing":    ["Journal", "Translation", "Chat/Messaging", "Grammar Exercises", "Other"],
    "Vocabulary": ["Flashcards (Anki)", "App (Duolingo etc.)", "Word List", "Dictionary Study", "Other"],
    "Grammar":    ["Textbook", "Exercises", "Online Course", "Other"],
    "Watching":   ["Movie", "TV Series", "YouTube", "Other"],
}


class LanguageLoggerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Language Learning Logger")
        self.geometry("860x580")
        self.minsize(700, 480)
        self._init_db()
        self._build_ui()

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    def _init_db(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                language          TEXT,
                activity_type     TEXT    NOT NULL,
                specific_activity TEXT,
                duration_minutes  INTEGER NOT NULL,
                date              TEXT    NOT NULL,
                notes             TEXT
            )
        """)
        self.conn.commit()

    def _known_languages(self):
        """Return display strings for languages already used, merged with full list."""
        cur = self.conn.execute(
            "SELECT DISTINCT language FROM sessions WHERE language IS NOT NULL ORDER BY language"
        )
        used_codes = {r[0] for r in cur.fetchall()}
        # Put used languages at the top, then the rest of the full list
        used = [o for o in LANGUAGE_OPTIONS if _extract_lang_code(o) in used_codes]
        rest = [o for o in LANGUAGE_OPTIONS if _extract_lang_code(o) not in used_codes]
        return used + rest

    # ------------------------------------------------------------------
    # UI skeleton
    # ------------------------------------------------------------------

    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.tab_log = ttk.Frame(self.notebook)
        self.tab_history = ttk.Frame(self.notebook)
        self.tab_stats = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_log,     text="  Log Session  ")
        self.notebook.add(self.tab_history, text="  History  ")
        self.notebook.add(self.tab_stats,   text="  Stats  ")

        self._build_log_tab()
        self._build_history_tab()
        self._build_stats_tab()

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

        def row(label_text, r):
            ttk.Label(frame, text=label_text).grid(row=r, column=0, sticky=tk.W, pady=6, padx=(0, 12))

        # Language (ISO 639-1)
        row("Language:", 0)
        self.var_language = tk.StringVar()
        self.cb_language = ttk.Combobox(frame, textvariable=self.var_language, width=30)
        self.cb_language["values"] = self._known_languages()
        self.cb_language.grid(row=0, column=1, sticky=tk.EW)
        ttk.Label(frame, text="e.g. Japanese (ja)", foreground="gray").grid(
            row=0, column=2, sticky=tk.W, padx=(6, 0)
        )

        # Activity Type
        row("Activity Type:", 1)
        self.var_activity_type = tk.StringVar()
        self.cb_activity_type = ttk.Combobox(
            frame, textvariable=self.var_activity_type,
            values=list(ACTIVITIES.keys()), state="readonly", width=30
        )
        self.cb_activity_type.grid(row=1, column=1, sticky=tk.EW)
        self.cb_activity_type.bind("<<ComboboxSelected>>", self._on_activity_type_change)

        # Specific Activity
        row("Specific Activity:", 2)
        self.var_specific = tk.StringVar()
        self.cb_specific = ttk.Combobox(frame, textvariable=self.var_specific, width=30)
        self.cb_specific.grid(row=2, column=1, sticky=tk.EW)

        # Duration
        row("Duration (minutes):", 3)
        self.var_duration = tk.IntVar(value=30)
        ttk.Spinbox(
            frame, from_=1, to=600, increment=5,
            textvariable=self.var_duration, width=10
        ).grid(row=3, column=1, sticky=tk.W)

        # Date
        row("Date (YYYY-MM-DD):", 4)
        self.var_date = tk.StringVar(value=date.today().isoformat())
        ttk.Entry(frame, textvariable=self.var_date, width=14).grid(row=4, column=1, sticky=tk.W)

        # Notes
        row("Notes:", 5)
        self.txt_notes = tk.Text(frame, height=4, width=40, wrap=tk.WORD)
        self.txt_notes.grid(row=5, column=1, sticky=tk.EW, pady=(0, 4))
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.txt_notes.yview)
        self.txt_notes.configure(yscrollcommand=scrollbar.set)
        scrollbar.grid(row=5, column=2, sticky=tk.NS)

        # Save button
        ttk.Button(frame, text="Save Session", command=self.save_session).grid(
            row=6, column=1, sticky=tk.W, pady=(12, 0)
        )

    def _on_activity_type_change(self, event=None):
        activity = self.var_activity_type.get()
        specifics = ACTIVITIES.get(activity, [])
        self.cb_specific["values"] = specifics
        self.var_specific.set(specifics[0] if specifics else "")

    def save_session(self):
        lang_display = self.var_language.get().strip()
        language = _extract_lang_code(lang_display) if lang_display else None
        activity_type = self.var_activity_type.get().strip()
        specific = self.var_specific.get().strip() or None
        notes = self.txt_notes.get("1.0", tk.END).strip() or None

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
            "INSERT INTO sessions (language, activity_type, specific_activity, duration_minutes, date, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (language, activity_type, specific, duration, date_str, notes)
        )
        self.conn.commit()

        # Refresh language dropdown so newly used codes bubble to the top
        self.cb_language["values"] = self._known_languages()

        # Clear form (keep language and date)
        self.var_activity_type.set("")
        self.var_specific.set("")
        self.cb_specific["values"] = []
        self.var_duration.set(30)
        self.txt_notes.delete("1.0", tk.END)

        desc = specific or activity_type
        messagebox.showinfo("Saved", f"Session logged: {duration} min — {desc}.")

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
            ("language", "Language",          100),
            ("activity", "Activity Type",     120),
            ("specific", "Specific Activity", 140),
            ("duration", "Duration (min)",    110),
            ("notes",    "Notes",             200),
        ]
        for col_id, heading, width in col_cfg:
            self.tree.heading(col_id, text=heading,
                              command=lambda c=col_id: self._sort_tree(c))
            self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)

        ttk.Button(frame, text="Delete Selected", command=self.delete_session).grid(
            row=2, column=0, sticky=tk.W, pady=(8, 0)
        )

        # Map treeview item iid → DB row id
        self._tree_id_map = {}
        self._sort_column = "date"
        self._sort_reverse = True

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
            iid = self.tree.insert("", tk.END, values=(date_val, lang, act, spec, dur, notes or ""))
            self._tree_id_map[iid] = db_id

    def delete_session(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Nothing selected", "Select a session to delete.")
            return
        iid = selected[0]
        db_id = self._tree_id_map.get(iid)
        if db_id is None:
            return
        if not messagebox.askyesno("Confirm Delete", "Delete this session?"):
            return
        self.conn.execute("DELETE FROM sessions WHERE id = ?", (db_id,))
        self.conn.commit()
        self.tree.delete(iid)
        del self._tree_id_map[iid]

    def _sort_tree(self, column):
        col_index = {"date": 0, "language": 1, "activity": 2, "specific": 3, "duration": 4, "notes": 5}
        idx = col_index[column]
        reverse = (column == self._sort_column) and not self._sort_reverse
        self._sort_column = column
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

        cur = self.conn.execute(
            "SELECT date, activity_type, duration_minutes FROM sessions"
        )
        rows = cur.fetchall()

        ax_bar = self.fig.add_subplot(1, 2, 1)
        ax_pie = self.fig.add_subplot(1, 2, 2)

        if not rows:
            for ax in (ax_bar, ax_pie):
                ax.text(0.5, 0.5, "No data yet", ha="center", va="center",
                        transform=ax.transAxes, fontsize=12, color="gray")
                ax.set_axis_off()
            self.canvas.draw()
            return

        # Bar chart — hours per week (last 8 weeks)
        today = date.today()
        weeks = []
        week_hours = []
        for i in range(7, -1, -1):
            week_start = today - timedelta(days=today.weekday() + 7 * i)
            week_end = week_start + timedelta(days=6)
            label = week_start.strftime("%b %d")
            total_min = sum(
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
                ax_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                            f"{val:.1f}", ha="center", va="bottom", fontsize=7)

        # Pie chart — time by activity type
        from collections import defaultdict
        by_activity = defaultdict(int)
        for _, act, dur in rows:
            by_activity[act] += dur
        labels = list(by_activity.keys())
        sizes = [by_activity[l] for l in labels]
        ax_pie.pie(sizes, labels=labels, autopct="%1.1f%%", startangle=140)
        ax_pie.set_title("Time by Activity Type")

        self.canvas.draw()


if __name__ == "__main__":
    app = LanguageLoggerApp()
    app.mainloop()
