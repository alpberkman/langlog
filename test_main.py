#!/usr/bin/env python
"""Regression tests for main.py.

Focuses on pure logic (date/formatting helpers, reference data, the Database
layer, and the generic Treeview-sort helper) plus an end-to-end CLI smoke
test, rather than driving the full Tkinter UI. Run with:

    python -m unittest test_main.py -v
"""

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

# main.py parses sys.argv at import time (argparse); swap it out so the test
# runner's own argv doesn't get fed into main's parser.
_ORIG_ARGV = sys.argv[:]
sys.argv = ["main.py"]
import main
sys.argv = _ORIG_ARGV


def _make_test_db():
    tmpdir = tempfile.mkdtemp()
    db = main.Database(os.path.join(tmpdir, "test.db"))
    return db, tmpdir


def _frozen_today(fixed_date):
    """datetime.date is immutable in C, so `today` can't be patched directly;
    swap main's `date` name for a subclass whose today() is pinned instead."""
    class _FixedDate(date):
        @classmethod
        def today(cls):
            return fixed_date
    return patch("main.date", _FixedDate)


class TestFmtTime(unittest.TestCase):
    def test_minutes_only(self):
        self.assertEqual(main._fmt_time(5), "00:05")

    def test_hours_and_minutes(self):
        self.assertEqual(main._fmt_time(90), "01:30")

    def test_rolls_over_into_days(self):
        self.assertEqual(main._fmt_time(1500), "01:01:00")  # 1440 + 60

    def test_rounds_fractional_minutes(self):
        self.assertEqual(main._fmt_time(59.6), "01:00")


class TestMonthsAgo(unittest.TestCase):
    def test_simple_month_subtraction(self):
        with _frozen_today(date(2026, 7, 26)):
            self.assertEqual(main._months_ago(1), date(2026, 6, 26))

    def test_wraps_year_boundary(self):
        with _frozen_today(date(2026, 1, 15)):
            self.assertEqual(main._months_ago(2), date(2025, 11, 15))

    def test_clamps_to_last_day_of_shorter_month(self):
        with _frozen_today(date(2026, 3, 31)):
            self.assertEqual(main._months_ago(1), date(2026, 2, 28))


class TestPeriodHelpers(unittest.TestCase):
    def test_period_key_day(self):
        self.assertEqual(main._period_key("2026-07-26", "Day"), "2026-07-26")

    def test_period_key_week_starts_monday(self):
        d = date(2026, 7, 26)
        expected = (d - timedelta(days=d.weekday())).isoformat()
        self.assertEqual(main._period_key("2026-07-26", "Week"), expected)

    def test_period_key_month(self):
        self.assertEqual(main._period_key("2026-07-26", "Month"), "2026-07")

    def test_all_periods_day_range(self):
        periods = main._all_periods(date(2026, 7, 1), date(2026, 7, 3), "Day")
        self.assertEqual([p[0] for p in periods], ["2026-07-01", "2026-07-02", "2026-07-03"])

    def test_all_periods_month_range_crosses_year(self):
        periods = main._all_periods(date(2025, 12, 1), date(2026, 1, 1), "Month")
        self.assertEqual([p[0] for p in periods], ["2025-12", "2026-01"])


class TestLanguageDisplayHelpers(unittest.TestCase):
    def test_extract_code_from_display(self):
        self.assertEqual(main._extract_lang_code("Japanese (ja)"), "ja")

    def test_extract_code_passthrough_plain_code(self):
        self.assertEqual(main._extract_lang_code("ja"), "ja")

    def test_extract_code_uses_final_parenthesis_group(self):
        self.assertEqual(main._extract_lang_code("Some (Extra) Name (xx)"), "xx")

    def test_lang_display_known_code(self):
        self.assertEqual(main._lang_display("ja"), "Japanese (ja)")

    def test_lang_display_empty(self):
        self.assertEqual(main._lang_display(""), "")
        self.assertEqual(main._lang_display(None), "")

    def test_lang_display_unknown_code_falls_back_to_code(self):
        self.assertEqual(main._lang_display("xx-unknown"), "xx-unknown")


class TestContrastingFg(unittest.TestCase):
    def test_light_background_gets_black_text(self):
        self.assertEqual(main._contrasting_fg("#ffffff"), "#000000")

    def test_dark_background_gets_white_text(self):
        self.assertEqual(main._contrasting_fg("#000000"), "#ffffff")


class TestPrepareChartData(unittest.TestCase):
    def test_empty_rows_returns_none(self):
        self.assertIsNone(main._prepare_chart_data([], None, None, "Day"))

    def test_aggregates_minutes_to_hours_by_period(self):
        rows = [
            ("2026-07-01", "Reading", 30),
            ("2026-07-01", "Reading", 30),
            ("2026-07-02", "Listening", 60),
        ]
        data = main._prepare_chart_data(rows, date(2026, 7, 1), date(2026, 7, 2), "Day")
        self.assertEqual(set(data.all_acts), {"Reading", "Listening"})
        self.assertEqual(data.by_act_period["Reading"]["2026-07-01"], 1.0)
        self.assertEqual(data.by_act_period["Listening"]["2026-07-02"], 1.0)

    def test_uses_data_range_when_no_explicit_bounds(self):
        rows = [("2026-07-05", "Reading", 30)]
        data = main._prepare_chart_data(rows, None, None, "Day")
        self.assertEqual(data.p_keys, ["2026-07-05"])

    def test_user_colors_override_default_palette(self):
        rows = [("2026-07-01", "Reading", 30)]
        data = main._prepare_chart_data(rows, None, None, "Day", user_colors={"Reading": "#123456"})
        self.assertEqual(data.color_map["Reading"], "#123456")


class TestSummaryLine(unittest.TestCase):
    def test_computes_sessions_total_avg_and_top_activity(self):
        rows = [
            ("2026-07-01", "Reading", 30),
            ("2026-07-02", "Reading", 30),
            ("2026-07-03", "Listening", 15),
        ]
        line = main._summary_line(rows, ["2026-07-01", "2026-07-02", "2026-07-03"], "Day")
        self.assertIn("Sessions: 3", line)
        self.assertIn("Total: 01:15", line)
        self.assertIn("Avg session: 00:25", line)
        self.assertIn("Avg per Day: 00:25", line)
        self.assertIn("Top activity: Reading", line)


class TestProjectLevels(unittest.TestCase):
    def test_hours_needed_scales_with_word_count_ratio(self):
        # C1 is the anchor level: hours_needed == the category's FSI hour estimate exactly.
        results = main._project_levels(
            total_minutes=60, first_date_str="2026-01-01", last_date_str="2026-01-01",
            fsi_category="III", today=date(2026, 1, 1),
        )
        levels = {r.level: r for r in results}
        self.assertAlmostEqual(levels["C1"].hours_needed, 1100)
        self.assertAlmostEqual(levels["A1"].hours_needed, 1100 * 500 / 8000)
        self.assertAlmostEqual(levels["C2"].hours_needed, 1100 * 16000 / 8000)

    def test_days_remaining_and_target_date_match_historical_pace(self):
        # One 60-minute session logged on a single day -> pace of 1 hour/day.
        results = main._project_levels(
            total_minutes=60, first_date_str="2026-01-01", last_date_str="2026-01-01",
            fsi_category="II", today=date(2026, 1, 1),
        )
        c1 = next(r for r in results if r.level == "C1")
        self.assertAlmostEqual(c1.hours_needed, 900)  # category II's hours_est
        self.assertEqual(c1.days_remaining, 899)       # 899 hours left at 1 hour/day
        self.assertEqual(c1.target_date, date(2026, 1, 1) + timedelta(days=899))

    def test_already_reached_levels_have_no_days_remaining(self):
        results = main._project_levels(
            total_minutes=100 * 60, first_date_str="2026-01-01", last_date_str="2026-01-11",
            fsi_category="I", today=date(2026, 1, 11),
        )
        levels = {r.level: r for r in results}
        self.assertIsNone(levels["A1"].days_remaining)
        self.assertIsNone(levels["A1"].target_date)
        self.assertIsNotNone(levels["C2"].days_remaining)
        self.assertIsNotNone(levels["C2"].target_date)


class TestIncrementalLevels(unittest.TestCase):
    def test_first_level_added_equals_its_own_total(self):
        # A1's "previous level" is zero, so words/hours added == the level's own totals.
        results = main._incremental_levels("III")
        a1 = next(r for r in results if r.level == "A1")
        self.assertEqual(a1.words_added, 500)
        self.assertAlmostEqual(a1.hours_added, 1100 * 500 / 8000)

    def test_deltas_sum_back_to_cumulative_totals(self):
        category = "II"
        incremental = main._incremental_levels(category)
        cumulative = main._project_levels(
            total_minutes=60, first_date_str="2026-01-01", last_date_str="2026-01-01", fsi_category=category
        )
        running_words, running_hours = 0, 0.0
        for inc, cum in zip(incremental, cumulative):
            running_words += inc.words_added
            running_hours += inc.hours_added
            self.assertEqual(running_words, cum.words)
            self.assertAlmostEqual(running_hours, cum.hours_needed)

    def test_higher_category_needs_more_incremental_hours(self):
        easy = {r.level: r for r in main._incremental_levels("I")}
        hard = {r.level: r for r in main._incremental_levels("IV")}
        for level in ("A1", "B1", "C1"):
            self.assertGreater(hard[level].hours_added, easy[level].hours_added)

    def test_custom_word_counts_table_uses_cefr_c1_anchor(self):
        # JLPT's N1 (10,000 words) should scale off the *same* CEFR-C1 (8,000
        # words) anchor as CEFR itself, not off JLPT's own top level.
        jlpt_name, jlpt_levels = main.NATIVE_LEVEL_SYSTEMS["ja"]
        results = main._incremental_levels("IV", word_counts=jlpt_levels)
        n1 = next(r for r in results if r.level == "N1")
        cumulative_hours = sum(r.hours_added for r in results)
        self.assertAlmostEqual(cumulative_hours, 2200 * 10000 / 8000)
        self.assertEqual(n1.words_added, 10000 - 6000)  # N1 - N2


class TestFormatDaysInUnit(unittest.TestCase):
    def test_day_unit_returns_plain_integer_string(self):
        self.assertEqual(main._format_days_in_unit(42, 1), "42")

    def test_week_unit_divides_and_rounds_to_one_decimal(self):
        self.assertEqual(main._format_days_in_unit(42, 7), "6.0")
        self.assertEqual(main._format_days_in_unit(10, 7), "1.4")

    def test_month_unit_divides_and_rounds_to_one_decimal(self):
        self.assertEqual(main._format_days_in_unit(90, 30), "3.0")


class TestValidateSessionFields(unittest.TestCase):
    def setUp(self):
        self.db, self.tmpdir = _make_test_db()

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_valid_fields(self):
        with patch("main.messagebox.showerror") as mock_err:
            result = main._validate_session_fields("Japanese (ja)", "Reading", "30", "2026-07-01", self.db)
        mock_err.assert_not_called()
        self.assertEqual(result, ("ja", 30))

    def test_empty_language_allowed(self):
        with patch("main.messagebox.showerror") as mock_err:
            result = main._validate_session_fields("", "Reading", "30", "2026-07-01", self.db)
        mock_err.assert_not_called()
        self.assertEqual(result, (None, 30))

    def test_language_not_in_prefs_rejected(self):
        with patch("main.messagebox.showerror") as mock_err:
            result = main._validate_session_fields(
                "Not A Real Language (zz)", "Reading", "30", "2026-07-01", self.db
            )
        self.assertIsNone(result)
        mock_err.assert_called_once()

    def test_missing_activity_type_rejected(self):
        with patch("main.messagebox.showerror") as mock_err:
            result = main._validate_session_fields("", "", "30", "2026-07-01", self.db)
        self.assertIsNone(result)
        mock_err.assert_called_once()

    def test_non_positive_duration_rejected(self):
        with patch("main.messagebox.showerror"):
            result = main._validate_session_fields("", "Reading", "0", "2026-07-01", self.db)
        self.assertIsNone(result)

    def test_non_numeric_duration_rejected(self):
        with patch("main.messagebox.showerror"):
            result = main._validate_session_fields("", "Reading", "abc", "2026-07-01", self.db)
        self.assertIsNone(result)

    def test_bad_date_rejected(self):
        with patch("main.messagebox.showerror"):
            result = main._validate_session_fields("", "Reading", "30", "07/01/2026", self.db)
        self.assertIsNone(result)


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.db, self.tmpdir = _make_test_db()

    def tearDown(self):
        self.db.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_schema_created(self):
        tables = {r[0] for r in self.db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {"sessions", "templates", "pref_languages", "pref_activity_types",
                    "pref_specific_activities", "pref_activity_colors"}
        self.assertTrue(expected <= tables)

    def test_fresh_db_has_no_languages_enabled_but_falls_back_to_all(self):
        self.assertEqual(self.db.enabled_lang_codes(), set())
        self.assertEqual(self.db.pref_languages(), main.LANGUAGE_OPTIONS)

    def test_activity_types_all_enabled_by_default(self):
        self.assertEqual(set(self.db.pref_activity_types()), set(main.ACTIVITIES))

    def test_insert_and_get_session(self):
        self.db.insert_session("ja", "Reading", "Book", 30, "2026-07-01", "notes")
        rows = self.db.get_sessions()
        self.assertEqual(len(rows), 1)
        _, d, lang, act, spec, dur, notes = rows[0]
        self.assertEqual((d, lang, act, spec, dur, notes),
                          ("2026-07-01", "ja", "Reading", "Book", 30, "notes"))

    def test_update_session(self):
        self.db.insert_session("ja", "Reading", "Book", 30, "2026-07-01", None)
        session_id = self.db.get_sessions()[0][0]
        self.db.update_session(session_id, "ko", "Listening", "Podcast", 45, "2026-07-02", "updated")
        row = self.db.get_session(session_id)
        self.assertEqual(row, ("ko", "Listening", "Podcast", 45, "2026-07-02", "updated"))

    def test_delete_session(self):
        self.db.insert_session("ja", "Reading", "Book", 30, "2026-07-01", None)
        session_id = self.db.get_sessions()[0][0]
        self.db.delete_session(session_id)
        self.assertEqual(self.db.get_sessions(), [])

    def test_get_sessions_filters_by_language_and_date_range(self):
        self.db.insert_session("ja", "Reading", None, 30, "2026-07-01", None)
        self.db.insert_session("ko", "Reading", None, 30, "2026-07-05", None)
        self.db.insert_session(None, "Reading", None, 30, "2026-07-10", None)

        self.assertEqual(len(self.db.get_sessions(lang_code="ja")), 1)
        self.assertEqual(len(self.db.get_sessions(lang_code="")), 1)  # "" == no-language rows
        self.assertEqual(len(self.db.get_sessions(start="2026-07-02", end="2026-07-06")), 1)

    def test_distinct_languages_excludes_null(self):
        self.db.insert_session("ja", "Reading", None, 30, "2026-07-01", None)
        self.db.insert_session(None, "Reading", None, 30, "2026-07-02", None)
        self.assertEqual(self.db.distinct_languages(), ["ja"])

    def test_language_time_stats_none_when_no_sessions(self):
        self.assertIsNone(self.db.language_time_stats("ja"))

    def test_language_time_stats_aggregates_across_sessions(self):
        self.db.insert_session("ja", "Reading", None, 30, "2026-07-01", None)
        self.db.insert_session("ja", "Listening", None, 45, "2026-07-05", None)
        self.db.insert_session("ko", "Reading", None, 10, "2026-07-01", None)
        stats = self.db.language_time_stats("ja")
        self.assertEqual(stats, (75, "2026-07-01", "2026-07-05", 2))

    def test_template_round_trip_and_duplicate_name_rejected(self):
        self.db.insert_template("anki-15", "ja", "Vocabulary", "Flashcards (Anki)", 15, None)
        self.assertEqual([t[1] for t in self.db.get_templates()], ["anki-15"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.insert_template("anki-15", "ko", "Vocabulary", None, 20, None)

    def test_save_and_read_lang_prefs(self):
        self.db.save_lang_prefs({"ja", "ko"})
        self.assertEqual(self.db.enabled_lang_codes(), {"ja", "ko"})

    def test_save_activity_colors_replaces_rather_than_accumulates(self):
        self.db.save_activity_colors({"Reading": "#111111"})
        self.assertEqual(self.db.get_activity_colors(), {"Reading": "#111111"})
        self.db.save_activity_colors({"Listening": "#222222"})
        self.assertEqual(self.db.get_activity_colors(), {"Listening": "#222222"})


class TestReferenceDataConsistency(unittest.TestCase):
    """Guards against typos in the hand-maintained FSI/CEFR/HSK/JLPT/TOPIK
    reference tables used by the Learning Time and Vocabulary tabs."""

    def test_language_difficulty_categories_are_all_known(self):
        for code, (category, _estimated) in main.LANGUAGE_DIFFICULTY.items():
            self.assertIn(category, main.FSI_CATEGORIES, f"{code} has unknown category {category!r}")

    def test_language_difficulty_codes_are_all_real_languages(self):
        self.assertTrue(set(main.LANGUAGE_DIFFICULTY) <= set(main.LANGUAGES))

    def test_native_level_systems_codes_are_all_real_languages(self):
        self.assertTrue(set(main.NATIVE_LEVEL_SYSTEMS) <= set(main.LANGUAGES))

    def test_cefr_word_counts_strictly_increasing(self):
        counts = [words for _level, words in main.CEFR_WORD_COUNTS]
        self.assertEqual(counts, sorted(counts))
        self.assertEqual(len(counts), len(set(counts)))

    def test_native_level_systems_word_counts_strictly_increasing(self):
        for code, (_system, levels) in main.NATIVE_LEVEL_SYSTEMS.items():
            counts = [words for _level, words in levels]
            self.assertEqual(counts, sorted(counts), f"{code} levels not increasing")


@unittest.skipUnless(os.environ.get("DISPLAY"), "no DISPLAY available for Tkinter widget tests")
class TestSortTreeview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = main.tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def _make_tree(self, rows):
        tree = main.ttk.Treeview(self.root, columns=("name", "hours"), show="headings")
        for name, hours in rows:
            tree.insert("", main.tk.END, values=(name, hours))
        return tree

    def test_sorts_ascending_then_toggles_to_descending(self):
        tree = self._make_tree([("b", "20"), ("a", "10"), ("c", "5")])
        state = {"column": None, "reverse": False}

        main._sort_treeview(tree, "name", state)
        self.assertEqual([tree.set(i, "name") for i in tree.get_children()], ["a", "b", "c"])

        main._sort_treeview(tree, "name", state)
        self.assertEqual([tree.set(i, "name") for i in tree.get_children()], ["c", "b", "a"])

    def test_numeric_column_sorts_by_value_not_text(self):
        tree = self._make_tree([("b", "20"), ("a", "9"), ("c", "100")])
        state = {"column": None, "reverse": False}
        main._sort_treeview(tree, "hours", state, numeric_columns=("hours",))
        # a text sort would give "100", "20", "9" - numeric sort must not
        self.assertEqual([tree.set(i, "hours") for i in tree.get_children()], ["9", "20", "100"])

    def test_numeric_column_parses_first_number_in_range(self):
        tree = self._make_tree([("a", "600-750"), ("b", "900"), ("c", "1100")])
        state = {"column": None, "reverse": False}
        main._sort_treeview(tree, "hours", state, numeric_columns=("hours",))
        self.assertEqual(
            [tree.set(i, "hours") for i in tree.get_children()], ["600-750", "900", "1100"]
        )

    def test_explicit_reverse_overrides_toggle_state(self):
        tree = self._make_tree([("b", "1"), ("a", "2")])
        state = {"column": "name", "reverse": False}
        main._sort_treeview(tree, "name", state, reverse=True)
        self.assertTrue(state["reverse"])
        self.assertEqual([tree.set(i, "name") for i in tree.get_children()], ["b", "a"])


@unittest.skipUnless(os.environ.get("DISPLAY"), "no DISPLAY available for Tkinter widget tests")
class TestProjectionTabPaceSlider(unittest.TestCase):
    """The Projection tab's Day/Week/Month slider re-scales the displayed
    pace figure and, on both sub-tabs, re-expresses the remaining/needed
    duration in the chosen unit (e.g. weeks instead of days)."""

    @classmethod
    def setUpClass(cls):
        cls.root = main.tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.db, self.tmpdir = _make_test_db()
        # A single 60-minute session on one day -> an unambiguous 60 min/day pace.
        # Japanese is FSI category IV (hours_est=2200), so A1 needs 137.5 hours.
        self.db.insert_session("ja", "Reading", None, 60, "2026-01-01", None)
        self.tab = main.ProjectionTab(self.root, self.db)
        self.tab.var_lang.set("Japanese (ja)")
        self.tab._populate()

    def tearDown(self):
        self.tab.destroy()
        self.db.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _first_row(self, tree, column):
        return tree.set(tree.get_children()[0], column)

    def test_default_unit_is_day(self):
        self.assertEqual(self.tab.tree.heading("pace")["text"], "Your Avg/Day")
        self.assertEqual(self.tab.tree.heading("days_remaining")["text"], "Days Remaining")
        self.assertEqual(self._first_row(self.tab.tree, "pace"), main._fmt_time(60))
        self.assertEqual(self._first_row(self.tab.tree, "days_remaining"), "137")

    def test_week_scales_pace_and_days_remaining(self):
        self.tab.var_unit_idx.set(1)
        self.tab._on_unit_change()
        self.assertEqual(self.tab.tree.heading("pace")["text"], "Your Avg/Week")
        self.assertEqual(self.tab.tree.heading("days_remaining")["text"], "Weeks Remaining")
        self.assertEqual(self._first_row(self.tab.tree, "pace"), main._fmt_time(60 * 7))
        self.assertEqual(self._first_row(self.tab.tree, "days_remaining"), "19.6")

    def test_month_scales_pace_and_days_remaining(self):
        self.tab.var_unit_idx.set(2)
        self.tab._on_unit_change()
        self.assertEqual(self.tab.tree.heading("pace")["text"], "Your Avg/Month")
        self.assertEqual(self.tab.tree.heading("days_remaining")["text"], "Months Remaining")
        self.assertEqual(self._first_row(self.tab.tree, "pace"), main._fmt_time(60 * 30))
        self.assertEqual(self._first_row(self.tab.tree, "days_remaining"), "4.6")

    def test_year_scales_pace_and_days_remaining(self):
        self.tab.var_unit_idx.set(3)
        self.tab._on_unit_change()
        self.assertEqual(self.tab.tree.heading("pace")["text"], "Your Avg/Year")
        self.assertEqual(self.tab.tree.heading("days_remaining")["text"], "Years Remaining")
        self.assertEqual(self._first_row(self.tab.tree, "pace"), main._fmt_time(60 * 365))
        self.assertEqual(self._first_row(self.tab.tree, "days_remaining"), "0.4")

    def test_target_date_unaffected_by_unit(self):
        target_at_day = self._first_row(self.tab.tree, "target_date")
        self.tab.var_unit_idx.set(1)
        self.tab._on_unit_change()
        self.assertEqual(self._first_row(self.tab.tree, "target_date"), target_at_day)

    def test_incremental_tab_default_unit_is_day(self):
        tree = self.tab.tree_incremental
        self.assertEqual(tree.heading("pace2")["text"], "Your Avg/Day")
        self.assertEqual(tree.heading("days_needed")["text"], "Days Needed")
        self.assertEqual(self._first_row(tree, "words_added"), "+500")
        self.assertEqual(self._first_row(tree, "hours_added"), "+138")
        self.assertEqual(self._first_row(tree, "days_needed"), "138")

    def test_incremental_tab_scales_with_unit(self):
        self.tab.var_unit_idx.set(1)
        self.tab._on_unit_change()
        tree = self.tab.tree_incremental
        self.assertEqual(tree.heading("pace2")["text"], "Your Avg/Week")
        self.assertEqual(tree.heading("days_needed")["text"], "Weeks Needed")
        self.assertEqual(self._first_row(tree, "days_needed"), "19.7")


@unittest.skipUnless(os.environ.get("DISPLAY"), "no DISPLAY available for Tkinter widget tests")
class TestProjectionTabNativeSystems(unittest.TestCase):
    """Languages with their own scale (HSK/JLPT/TOPIK) should show those
    levels alongside CEFR in both Projection sub-tabs; languages without one
    should only show CEFR."""

    @classmethod
    def setUpClass(cls):
        cls.root = main.tk.Tk()
        cls.root.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.root.destroy()

    def setUp(self):
        self.db, self.tmpdir = _make_test_db()

    def tearDown(self):
        self.tab.destroy()
        self.db.conn.close()
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _systems_shown(self, lang_display):
        self.tab = main.ProjectionTab(self.root, self.db)
        self.tab.var_lang.set(lang_display)
        self.tab._populate()
        to_level     = {self.tab.tree.set(i, "system") for i in self.tab.tree.get_children()}
        incremental  = {self.tab.tree_incremental.set(i, "system") for i in self.tab.tree_incremental.get_children()}
        return to_level, incremental

    def test_japanese_shows_cefr_and_jlpt(self):
        self.db.insert_session("ja", "Reading", None, 60, "2026-01-01", None)
        to_level, incremental = self._systems_shown("Japanese (ja)")
        self.assertEqual(to_level, {"CEFR", "JLPT"})
        self.assertEqual(incremental, {"CEFR", "JLPT"})

    def test_spanish_shows_only_cefr(self):
        self.db.insert_session("es", "Reading", None, 60, "2026-01-01", None)
        to_level, incremental = self._systems_shown("Spanish (es)")
        self.assertEqual(to_level, {"CEFR"})
        self.assertEqual(incremental, {"CEFR"})

    def test_jlpt_rows_use_jlpt_level_labels_and_word_counts(self):
        self.db.insert_session("ja", "Reading", None, 60, "2026-01-01", None)
        self._systems_shown("Japanese (ja)")
        jlpt_words = {
            self.tab.tree.set(i, "level"): self.tab.tree.set(i, "words")
            for i in self.tab.tree.get_children()
            if self.tab.tree.set(i, "system") == "JLPT"
        }
        self.assertEqual(jlpt_words["N5"], "~800")
        self.assertEqual(jlpt_words["N1"], "~10,000")


class TestCliSmoke(unittest.TestCase):
    """End-to-end tests that actually invoke `python main.py` as a subprocess,
    matching the documented CLI usage (--list-templates / --template)."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "cli_test.db")
        self.main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, *args):
        return subprocess.run(
            [sys.executable, self.main_py, "-f", self.db_path, *args],
            capture_output=True, text=True, timeout=15,
        )

    def test_list_templates_empty(self):
        result = self._run("--list-templates")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No templates saved yet.", result.stdout)

    def test_log_unknown_template_fails_with_message(self):
        result = self._run("--template", "does-not-exist")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stdout + result.stderr)

    def test_log_template_end_to_end(self):
        db = main.Database(self.db_path)
        db.insert_template("anki-15", "ja", "Vocabulary", "Flashcards (Anki)", 15, None)
        db.conn.close()

        result = self._run("--template", "anki-15", "--date", "2026-07-01")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Logged:", result.stdout)

        db2 = main.Database(self.db_path)
        rows = db2.get_sessions()
        db2.conn.close()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][5], 15)  # duration_minutes


if __name__ == "__main__":
    unittest.main()
