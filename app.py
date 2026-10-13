import json
import math
import time
from datetime import datetime
from pathlib import Path

import streamlit as st
import exam_core as engine

st.set_page_config(page_title="CCAO-F | Exam Studio", page_icon="🎓", layout="wide")
engine.init_db()
st.markdown("""<style>
.stApp {background:#f5f7fb;}
.block-container {max-width:1180px;padding-top:2rem;padding-bottom:3rem;}
[data-testid="stSidebar"] {background:#101d35;}
[data-testid="stSidebar"] * {color:#e6edf8;}
[data-testid="stSidebar"] button {background:#243550;border:1px solid #526078;}
h1,h2,h3 {letter-spacing:-.035em;}
.hero {background:linear-gradient(120deg,#142442,#264b74);padding:36px;border-radius:22px;color:white;margin:12px 0 24px;}
.hero h1 {color:white;font-size:2.6rem;margin:8px 0;}
.hero p {color:#d5e3f5;max-width:680px;font-size:1.06rem;}
.eyebrow {font-size:.76rem;letter-spacing:.16em;font-weight:700;color:#81dfd0;}
[data-testid="stMetric"] {background:white;border:1px solid #e1e7f0;padding:16px;border-radius:14px;}
[data-testid="stVerticalBlockBorderWrapper"] {background:white;border-radius:16px;}
.stButton>button {border-radius:10px;min-height:42px;}
[data-testid="stProgressBar"]>div>div {background:#13a692;}
</style>""", unsafe_allow_html=True)


def seconds_label(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def fresh_view():
    for k in list(st.session_state):
        if k.startswith(("exam_", "flag_", "practice_")) or k in ("aid", "idx", "result", "confirm_submit"):
            del st.session_state[k]


def sign_out():
    fresh_view()
    st.session_state.pop("user", None)
    st.rerun()


def show_leaderboard():
    st.subheader("Top 10 learners")
    st.caption("Best exam per account · highest score first · fastest time breaks a tie. Practice mode is excluded.")
    rows = engine.leaderboard()
    if not rows:
        st.info("The podium is waiting. Complete an exam to set the first score.")
        return
    data = [{"Rank": i+1, "Name": r["name"], "Username": r["username"], "Score": f'{r["score"]}/60',
             "Accuracy": f'{r["score"]/60:.0%}', "Time": seconds_label(r["elapsed"])} for i,r in enumerate(rows)]
    st.dataframe(data, hide_index=True, use_container_width=True)


def auth():
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.markdown('''<div class="hero"><div class="eyebrow">YOUR NEXT STEP IN AI</div>
        <h1>Practice with purpose.<br>Walk in prepared.</h1>
        <p>Your focused study space for Claude Certified Associate – Foundations.
        Learn from explanations, take a timed mock exam, and track your progress.</p></div>''', unsafe_allow_html=True)
        a,b,c = st.columns(3)
        a.metric("Questions", "60")
        b.metric("Time limit", "100 min")
        c.metric("Domains", "7")
        st.caption("Practice content by Matthew Purcell. This is an independent study tool, not an official certification exam.")
    with right:
        with st.container(border=True):
            tabs = st.tabs(["Sign in", "Create account"])
            with tabs[0]:
                with st.form("login"):
                    username = st.text_input("Username", max_chars=24)
                    password = st.text_input("Password", type="password", max_chars=128)
                    if st.form_submit_button("Continue to my study space", type="primary", use_container_width=True):
                        try:
                            st.session_state.user = engine.login(username, password)
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
            with tabs[1]:
                st.caption("Your display name and username appear on the leaderboard after an exam.")
                with st.form("register"):
                    name = st.text_input("Display name", max_chars=40)
                    username = st.text_input("Choose a username", max_chars=24)
                    password = st.text_input("Choose a password", type="password", max_chars=128)
                    confirm = st.text_input("Repeat password", type="password", max_chars=128)
                    if st.form_submit_button("Create my account", type="primary", use_container_width=True):
                        try:
                            if password != confirm:
                                raise ValueError("Passwords do not match.")
                            st.session_state.user = engine.register(username, name, password)
                            st.rerun()
                        except ValueError as e:
                            st.error(str(e))
    show_leaderboard()


def result_view(row):
    st.subheader("Your exam report")
    answers = json.loads(row["answers_json"])
    done = sum(bool(v) for v in answers.values())
    a,b,c,d = st.columns(4)
    a.metric("Score", f'{row["score"]} / 60')
    b.metric("Accuracy", f'{row["score"]/60:.1%}')
    c.metric("Time used", seconds_label(row["elapsed"]))
    d.metric("Unanswered", 60-done)
    st.caption(f'{row["reason"]} · One point per fully correct answer. No negative marks or partial credit.')
    if row["score"] >= 45:
        st.success("You reached the 75% practice target. Review weaker domains before your next attempt.")
    else:
        st.info("Use the explanations below to focus your next study session. Practice target: 75%.")
    st.caption("75% is a study target from the source material, not an official pass prediction.")
    domains = []
    for domain in dict.fromkeys(q["domain"] for q in engine.QUESTIONS):
        qs = [q for q in engine.QUESTIONS if q["domain"] == domain]
        correct = sum(set(answers.get(q["id"], [])) == set(q["answer"]) for q in qs)
        domains.append({"Domain": domain, "Correct": correct, "Questions": len(qs), "Accuracy (%)": round(correct/len(qs)*100, 1)})
    st.dataframe(domains, hide_index=True, use_container_width=True)
    st.download_button("Download my result", json.dumps({"username": row["username"], "score": row["score"], "total": 60,
                       "elapsed_seconds": row["elapsed"], "domains": domains, "answers": answers}, indent=2),
                       file_name="ccao-f-result.json", mime="application/json")
    only_missed = st.checkbox("Show only incorrect and unanswered questions", value=True)
    for qid in json.loads(row["order_json"]):
        q = engine.BY_ID[qid]
        selected = answers.get(qid, [])
        correct = set(selected) == set(q["answer"])
        if only_missed and correct:
            continue
        with st.expander(f'{"✓" if correct else "○"} {qid} · {q["question"][:100]}'):
            st.write(q["question"])
            for letter, text in q["options"].items():
                st.write(f'{letter}. {text}')
            st.write("Your answer: " + (", ".join(selected) or "Unanswered"))
            st.success("Correct answer: " + ", ".join(q["answer"]))
            st.write(q["explanation"])


def answer_changed(aid, qid, key, multiple):
    value = st.session_state[key]
    engine.save_answer(aid, st.session_state.user, qid, list(value) if multiple else ([value] if value else []))


def multiple_answers_changed(aid, qid, keys):
    selected = [letter for letter, key in keys.items() if st.session_state.get(key, False)]
    engine.save_answer(aid, st.session_state.user, qid, selected)


def flag_changed(aid, qid, key):
    engine.flag_question(aid, st.session_state.user, qid, st.session_state[key])


def change_question(index):
    st.session_state.idx = index
    st.session_state.confirm_submit = False


def exam_view(aid):
    row = engine.attempt(aid, st.session_state.user)
    if row["finished"] is not None:
        result_view(row)
        if st.button("Back to dashboard", type="primary"):
            fresh_view()
            st.rerun()
        return
    st.subheader("Mock exam")
    st.caption("Your answers save automatically. Refreshing or signing out does not reset the deadline. Sign in again to resume.")

    @st.fragment(run_every="1s")
    def timer():
        remaining = max(0, math.ceil(row["deadline"] - time.time()))
        st.metric("Time remaining", seconds_label(remaining))
        if remaining <= 0:
            engine.submit(aid, st.session_state.user)
            st.rerun()
        if remaining <= 300:
            st.warning("Final 5 minutes. Check unanswered questions and submit when ready.")
    timer()
    order = json.loads(row["order_json"])
    answers = json.loads(row["answers_json"])
    flags = set(json.loads(row["flags_json"]))
    idx = min(st.session_state.get("idx", 0), 59)
    qid = order[idx]
    q = engine.BY_ID[qid]
    answered = sum(len(answers.get(i, [])) == engine.BY_ID[i]["select"] for i in order)
    st.progress(answered/60, text=f"{answered} / 60 fully answered · {len(flags)} flagged for review")
    main, navigation = st.columns([2.6, 1], gap="large")
    with main:
        with st.container(border=True):
            st.caption(f'QUESTION {idx+1} OF 60 · {q["domain"]} · Source {qid}')
            st.subheader(q["question"])
            st.caption(f'Select exactly {q["select"]} answer(s).')
            key = f"exam_{aid}_{qid}"
            stored = answers.get(qid, [])
            if q["select"] > 1:
                checkbox_keys = {letter: f"exam_{aid}_{qid}_{letter}" for letter in q["options"]}
                for letter, checkbox_key in checkbox_keys.items():
                    if checkbox_key not in st.session_state:
                        st.session_state[checkbox_key] = letter in stored
                selected_now = [letter for letter, checkbox_key in checkbox_keys.items()
                                if st.session_state.get(checkbox_key, False)]
                for letter, option_text in q["options"].items():
                    checkbox_key = checkbox_keys[letter]
                    st.checkbox(
                        f"{letter}. {option_text}",
                        key=checkbox_key,
                        disabled=(len(selected_now) >= q["select"] and letter not in selected_now),
                        on_change=multiple_answers_changed,
                        args=(aid, qid, checkbox_keys),
                    )
            else:
                if key not in st.session_state:
                    st.session_state[key] = stored[0] if stored else None
                fmt = lambda letter: f'{letter}. {q["options"][letter]}'
                st.radio("Your answer", list(q["options"]), index=None, format_func=fmt, key=key,
                         on_change=answer_changed, args=(aid, qid, key, False))
                if st.button("Clear answer", key=f"clear_{qid}"):
                    engine.save_answer(aid, st.session_state.user, qid, [])
                    # A new widget key is unnecessary: clear on next run before rendering.
                    st.session_state.clear_widget = key
                    st.rerun()
            flag_key = f"flag_{aid}_{qid}"
            if flag_key not in st.session_state:
                st.session_state[flag_key] = qid in flags
            st.checkbox("Flag for review", key=flag_key, on_change=flag_changed, args=(aid, qid, flag_key))
        prev, nex = st.columns(2)
        prev.button("← Previous", disabled=idx==0, on_click=change_question, args=(idx-1,), use_container_width=True)
        nex.button("Next →", disabled=idx==59, on_click=change_question, args=(idx+1,), use_container_width=True)
    with navigation:
        st.markdown("**Question navigator**")
        st.caption("✓ Answered · ⚑ Flagged · · Incomplete")
        for start in range(0,60,5):
            cols = st.columns(5)
            for offset, col in enumerate(cols):
                n = start+offset
                i = order[n]
                marker = "⚑" if i in flags else ("✓" if len(answers.get(i, [])) == engine.BY_ID[i]["select"] else "·")
                col.button(f"{n+1}{marker}", key=f"jump_{n}", type="primary" if n==idx else "secondary",
                           on_click=change_question, args=(n,), use_container_width=True)
        if st.button("Finish exam", type="primary", use_container_width=True):
            st.session_state.confirm_submit = True
        if st.session_state.get("confirm_submit"):
            st.warning(f"{60-answered} questions incomplete. Submit your current answers?")
            if st.button("Submit now", use_container_width=True):
                engine.submit(aid, st.session_state.user)
                st.rerun()
            if st.button("Keep working", use_container_width=True):
                st.session_state.confirm_submit = False
                st.rerun()


def practice_view():
    st.title("Make every answer count.")
    st.write("Study one domain at a time, with immediate feedback and the author's reasoning.")
    domain = st.selectbox("Study domain", ["All domains"] + list(dict.fromkeys(q["domain"] for q in engine.QUESTIONS)))
    pool = [q for q in engine.QUESTIONS if domain == "All domains" or q["domain"] == domain]
    qid = st.selectbox("Question", [q["id"] for q in pool], format_func=lambda i: f'{i} · {engine.BY_ID[i]["question"][:85]}')
    q = engine.BY_ID[qid]
    with st.container(border=True):
        st.caption(q["domain"])
        st.subheader(q["question"])
        st.caption(f'Select exactly {q["select"]} answer(s). No timer. No leaderboard score.')
        fmt = lambda a: f'{a}. {q["options"][a]}'
        if q["select"] == 1:
            value = st.radio("Your answer", list(q["options"]), index=None, format_func=fmt, key=f"practice_{qid}")
            selected = [value] if value else []
        else:
            checkbox_keys = {letter: f"practice_{qid}_{letter}" for letter in q["options"]}
            for checkbox_key in checkbox_keys.values():
                if checkbox_key not in st.session_state:
                    st.session_state[checkbox_key] = False
            selected = [letter for letter, checkbox_key in checkbox_keys.items()
                        if st.session_state.get(checkbox_key, False)]
            for letter, option_text in q["options"].items():
                st.checkbox(
                    f"{letter}. {option_text}",
                    key=checkbox_keys[letter],
                    disabled=(len(selected) >= q["select"] and letter not in selected),
                )
            selected = [letter for letter, checkbox_key in checkbox_keys.items()
                        if st.session_state.get(checkbox_key, False)]
        if st.button("Check answer", type="primary"):
            if len(selected) != q["select"]:
                st.warning(f'Select {q["select"]} answer(s) first.')
            else:
                if set(selected) == set(q["answer"]):
                    st.success("Correct. Keep going!")
                else:
                    st.error("Not quite. Review the explanation and try the next question.")
                st.write("**Correct answer: " + ", ".join(q["answer"]) + "**")
                st.write(q["explanation"])


def dashboard():
    st.markdown('''<div class="hero"><div class="eyebrow">CCAO-F / EXAM STUDIO</div>
    <h1>A little practice.<br>A lot more confidence.</h1>
    <p>60 source questions. Seven domains. One focused place to prepare.</p></div>''', unsafe_allow_html=True)
    history = engine.history(st.session_state.user)
    a,b,c,d = st.columns(4)
    a.metric("Exam length", "100 min")
    b.metric("Question bank", "60")
    c.metric("Completed exams", len(history))
    d.metric("Personal best", f'{max(r["score"] for r in history)}/60' if history else "—")
    st.write("")
    left,right = st.columns([1.3, 1])
    with left, st.container(border=True):
        st.subheader("Ready for a full mock exam?")
        st.write("All 60 questions in a shuffled order, with a 100-minute countdown. Answers are revealed after submission.")
        st.write("Each question is worth 1 point. Multiple-response questions require every correct choice; no partial credit or negative marking.")
        st.caption("The PDF suggests 120 minutes; this platform uses your requested 100 minutes.")
        if st.button("Start 100-minute exam →", type="primary", use_container_width=True):
            st.session_state.aid = engine.start_exam(st.session_state.user)
            st.session_state.idx = 0
            st.rerun()
    with right, st.container(border=True):
        st.subheader("Your study map")
        for domain in dict.fromkeys(q["domain"] for q in engine.QUESTIONS):
            count = sum(q["domain"]==domain for q in engine.QUESTIONS)
            st.write(f"**{count:02d}** · {domain}")
    show_leaderboard()


if "clear_widget" in st.session_state:
    st.session_state[st.session_state.pop("clear_widget")] = None

if "user" not in st.session_state:
    auth()
else:
    with st.sidebar:
        st.markdown("## 🎓 Exam Studio")
        st.caption("CCAO-F FOUNDATIONS")
        st.write("Signed in as")
        st.text(st.session_state.user)
        st.divider()
    active = engine.active_attempt(st.session_state.user)
    if active:
        st.session_state.aid = active
    if st.session_state.get("aid"):
        with st.sidebar:
            st.info("Your exam workspace")
            if st.button("Sign out"):
                sign_out()
        exam_view(st.session_state.aid)
    else:
        with st.sidebar:
            page = st.radio("Workspace", ["Dashboard", "Practice", "Leaderboard", "My results"])
            st.divider()
            if st.button("Sign out"):
                sign_out()
            st.caption("Study target: 75% or better in each domain.")
        if page == "Dashboard":
            dashboard()
        elif page == "Practice":
            practice_view()
        elif page == "Leaderboard":
            st.title("The top 10")
            show_leaderboard()
        else:
            st.title("My results")
            rows = engine.history(st.session_state.user)
            if not rows:
                st.info("Complete your first mock exam to see your progress here.")
            else:
                choice = st.selectbox("Exam attempt", range(len(rows)), format_func=lambda i: f'{datetime.fromtimestamp(rows[i]["finished"]):%d %b %Y, %H:%M} · {rows[i]["score"]}/60')
                result_view(rows[choice])

st.divider()
st.caption("Source: Matthew Purcell · CCAO-F Practice Questions · Independent practice material; not actual exam questions or an official Anthropic exam.")
