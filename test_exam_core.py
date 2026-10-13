import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import exam_core as e


class ExamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original = e.DB_PATH
        e.DB_PATH = Path(self.temp.name) / "test.db"
        e.init_db()
        e.login("learner")

    def tearDown(self):
        e.DB_PATH = self.original
        self.temp.cleanup()

    def test_bank_matches_source_blueprint(self):
        e.validate_bank()
        self.assertEqual(e.grade({q["id"]: q["answer"] for q in e.QUESTIONS}), 60)
        self.assertEqual(e.grade({}), 0)

    def test_multi_select_requires_exact_set(self):
        q = next(q for q in e.QUESTIONS if q["select"] == 2)
        self.assertEqual(e.grade({q["id"]: q["answer"][:1]}), 0)
        self.assertEqual(e.grade({q["id"]: q["answer"]}), 1)
        self.assertEqual(e.grade({q["id"]: list(q["options"])}), 0)

    def test_username_only_identity(self):
        self.assertEqual(e.login("LEARNER"), "learner")
        self.assertEqual(e.login("learner"), "learner")
        with self.assertRaises(ValueError):
            e.login("ab")
        with e.connect() as c:
            columns = {row["name"] for row in c.execute("PRAGMA table_info(users)")}
        self.assertEqual(columns, {"username", "name"})

    def test_resume_and_saved_answers(self):
        with patch("exam_core.time.time", return_value=1000):
            aid = e.start_exam("learner")
            self.assertEqual(e.start_exam("learner"), aid)
            self.assertTrue(e.save_answer(aid, "learner", "1.1", ["B"]))
            e.flag_question(aid, "learner", "1.1", True)
            row = e.attempt(aid, "learner")
            self.assertEqual(row["deadline"], 7000)
            self.assertEqual(len(set(json.loads(row["order_json"]))), 60)
            self.assertEqual(json.loads(row["answers_json"])["1.1"], ["B"])
            self.assertIn("1.1", json.loads(row["flags_json"]))
            self.assertEqual(e.active_attempt("learner"), aid)

    def test_late_answer_rejected_and_auto_submit(self):
        with patch("exam_core.time.time", return_value=1000):
            aid = e.start_exam("learner")
            e.save_answer(aid, "learner", "1.1", ["B"])
        with patch("exam_core.time.time", return_value=7000):
            self.assertFalse(e.save_answer(aid, "learner", "1.2", ["D"]))
            row = e.attempt(aid, "learner")
            self.assertEqual(row["score"], 1)
            self.assertEqual(row["elapsed"], 6000)
            self.assertEqual(row["reason"], "Time expired")

    def test_expired_disconnected_exam_on_leaderboard(self):
        with patch("exam_core.time.time", return_value=1000):
            e.start_exam("learner")
        with patch("exam_core.time.time", return_value=9000):
            board = e.leaderboard()
            self.assertEqual(board[0]["elapsed"], 6000)
            self.assertIsNone(e.active_attempt("learner"))

    def test_submission_is_idempotent_and_authorized(self):
        e.login("other")
        aid = e.start_exam("learner")
        self.assertFalse(e.save_answer(aid, "other", "1.1", ["B"]))
        e.submit(aid, "other")
        self.assertIsNone(e.attempt(aid, "learner")["finished"])
        e.save_answer(aid, "learner", "1.1", ["B"])
        e.submit(aid, "learner")
        first = e.attempt(aid, "learner")
        e.submit(aid, "learner")
        self.assertFalse(e.save_answer(aid, "learner", "1.1", ["A"]))
        self.assertEqual(first, e.attempt(aid, "learner"))

    def test_best_score_and_time_and_top_ten_unique_users(self):
        for i in range(12):
            username = f"user_{i}"
            e.login(username)
            with patch("exam_core.time.time", return_value=1000):
                aid = e.start_exam(username)
                for q in e.QUESTIONS[:i]:
                    e.save_answer(aid, username, q["id"], q["answer"])
            with patch("exam_core.time.time", return_value=1100+i):
                e.submit(aid, username)
        # A weaker repeat must not replace the personal best.
        aid = e.start_exam("user_11")
        e.submit(aid, "user_11")
        board = e.leaderboard()
        self.assertEqual(len(board), 10)
        self.assertEqual(len({r["username"] for r in board}), 10)
        self.assertEqual(board[0]["username"], "user_11")
        self.assertEqual(board[0]["score"], 11)
        # Same score, faster completion ranks first.
        with patch("exam_core.time.time", return_value=10000):
            aid = e.start_exam("learner")
            for q in e.QUESTIONS[:11]:
                e.save_answer(aid, "learner", q["id"], q["answer"])
        with patch("exam_core.time.time", return_value=10020):
            e.submit(aid, "learner")
        self.assertEqual(e.leaderboard()[0]["username"], "learner")


if __name__ == "__main__":
    unittest.main()
