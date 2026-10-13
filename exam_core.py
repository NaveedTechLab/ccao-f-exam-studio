"""Persistent exam engine. All deadlines and grading are enforced server-side."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import random
import re
import secrets
import sqlite3
import time

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("EXAM_DB_PATH", ROOT / "data" / "exam.db"))
DURATION = 100 * 60
QUESTIONS = json.loads((ROOT / "data" / "questions.json").read_text(encoding="utf-8"))
BY_ID = {q["id"]: q for q in QUESTIONS}


def validate_bank():
    assert len(QUESTIONS) == len(BY_ID) == 60
    assert [sum(q["id"].startswith(f"{d}.") for q in QUESTIONS) for d in range(1, 8)] == [8, 13, 7, 10, 7, 9, 6]
    for q in QUESTIONS:
        assert q["select"] == len(q["answer"])
        assert set(q["answer"]) <= set(q["options"])
        assert len(q["options"]) == (4 if q["select"] == 1 else 5)
        assert q["question"] and q["explanation"]
        assert all(q["options"].values())


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    try:
        with c:
            yield c
    finally:
        c.close()


def init_db():
    validate_bank()
    with connect() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY, name TEXT NOT NULL);
        """)
        # Preserve existing leaderboard identities while removing legacy password hashes.
        columns = {row["name"] for row in c.execute("PRAGMA table_info(users)")}
        if "password_hash" in columns:
            c.executescript("""
            CREATE TABLE users_username_only (
                username TEXT PRIMARY KEY, name TEXT NOT NULL);
            INSERT INTO users_username_only(username, name)
                SELECT username, name FROM users;
            DROP TABLE users;
            ALTER TABLE users_username_only RENAME TO users;
            """)
        c.executescript("""
        CREATE TABLE IF NOT EXISTS attempts (
            id TEXT PRIMARY KEY, username TEXT NOT NULL,
            started REAL NOT NULL, deadline REAL NOT NULL,
            order_json TEXT NOT NULL, answers_json TEXT NOT NULL DEFAULT '{}',
            flags_json TEXT NOT NULL DEFAULT '[]', finished REAL, score INTEGER,
            elapsed INTEGER, reason TEXT);
        CREATE UNIQUE INDEX IF NOT EXISTS one_active_attempt
        ON attempts(username) WHERE finished IS NULL;
        """)


def login(username):
    display_name = " ".join(username.split())
    username = display_name.lower()
    if not re.fullmatch(r"[a-z0-9_]{3,24}", username):
        raise ValueError("Username must be 3-24 letters, numbers or underscores.")
    with connect() as c:
        row = c.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
        if row:
            return row["username"]
        try:
            c.execute("INSERT INTO users(username, name) VALUES (?, ?)", (username, display_name))
        except sqlite3.IntegrityError:
            # Another session may have created the same username at the same time.
            row = c.execute("SELECT username FROM users WHERE username=?", (username,)).fetchone()
            if row:
                return row["username"]
            raise
    return username


def grade(answers):
    return sum(set(answers.get(q["id"], [])) == set(q["answer"]) for q in QUESTIONS)


def finish_row(c, row, now, reason):
    if row["finished"] is not None:
        return
    end = min(now, row["deadline"])
    c.execute("UPDATE attempts SET finished=?, score=?, elapsed=?, reason=? WHERE id=? AND finished IS NULL",
              (end, grade(json.loads(row["answers_json"])), max(0, int(end-row["started"])),
               "Time expired" if now >= row["deadline"] else reason, row["id"]))


def expire_attempts():
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        now = time.time()
        for row in c.execute("SELECT * FROM attempts WHERE finished IS NULL AND deadline<=?", (now,)).fetchall():
            finish_row(c, row, now, "Time expired")


def start_exam(username):
    expire_attempts()
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        if not c.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
            raise ValueError("Please sign in first.")
        active = c.execute("SELECT id FROM attempts WHERE username=? AND finished IS NULL", (username,)).fetchone()
        if active:
            return active["id"]
        aid, now = secrets.token_hex(16), time.time()
        order = list(BY_ID)
        random.SystemRandom().shuffle(order)
        c.execute("INSERT INTO attempts(id,username,started,deadline,order_json) VALUES(?,?,?,?,?)",
                  (aid, username, now, now+DURATION, json.dumps(order)))
        return aid


def attempt(aid, username):
    expire_attempts()
    with connect() as c:
        row = c.execute("SELECT * FROM attempts WHERE id=? AND username=?", (aid, username)).fetchone()
    if row is None:
        raise ValueError("Attempt not found.")
    return dict(row)


def active_attempt(username):
    expire_attempts()
    with connect() as c:
        row = c.execute("SELECT id FROM attempts WHERE username=? AND finished IS NULL", (username,)).fetchone()
    return row["id"] if row else None


def save_answer(aid, username, qid, answers):
    q = BY_ID[qid]
    if len(set(answers)) != len(answers) or not set(answers) <= set(q["options"]) or len(answers) > q["select"]:
        raise ValueError("Invalid answer selection.")
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM attempts WHERE id=? AND username=?", (aid, username)).fetchone()
        if row is None or row["finished"] is not None:
            return False
        now = time.time()
        if now >= row["deadline"]:
            finish_row(c, row, now, "Time expired")
            return False
        stored = json.loads(row["answers_json"])
        stored[qid] = answers
        c.execute("UPDATE attempts SET answers_json=? WHERE id=?", (json.dumps(stored), aid))
    return True


def flag_question(aid, username, qid, flagged):
    if qid not in BY_ID:
        raise ValueError("Unknown question.")
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM attempts WHERE id=? AND username=?", (aid, username)).fetchone()
        if row is None or row["finished"] is not None:
            return
        if time.time() >= row["deadline"]:
            finish_row(c, row, time.time(), "Time expired")
            return
        flags = set(json.loads(row["flags_json"]))
        flags.add(qid) if flagged else flags.discard(qid)
        c.execute("UPDATE attempts SET flags_json=? WHERE id=?", (json.dumps(sorted(flags)), aid))


def submit(aid, username):
    with connect() as c:
        c.execute("BEGIN IMMEDIATE")
        row = c.execute("SELECT * FROM attempts WHERE id=? AND username=?", (aid, username)).fetchone()
        if row:
            finish_row(c, row, time.time(), "Submitted")


def history(username):
    expire_attempts()
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM attempts WHERE username=? AND finished IS NOT NULL ORDER BY finished DESC", (username,))]


def leaderboard():
    expire_attempts()
    with connect() as c:
        return [dict(r) for r in c.execute("""
        WITH ranked AS (
            SELECT a.*, u.name, ROW_NUMBER() OVER (
                PARTITION BY a.username ORDER BY score DESC, elapsed ASC, finished ASC, id ASC
            ) AS position
            FROM attempts a JOIN users u ON a.username=u.username WHERE finished IS NOT NULL
        ) SELECT username, name, score, elapsed, finished FROM ranked WHERE position=1
        ORDER BY score DESC, elapsed ASC, finished ASC, username ASC LIMIT 10
        """)]
