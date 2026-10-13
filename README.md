# CCAO-F Exam Studio

A Streamlit preparation platform built from **Matthew Purcell - CCAO-F exam.pdf**.

## Start on Windows

Double-click **START_EXAM.bat** in this folder, then open http://localhost:8501.
Python must be installed. The first launch installs Streamlit and needs internet access.

Or run in PowerShell:

```powershell
cd 'E:\exam prep\ccao-f-exam-studio'
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

Create an account, then use Dashboard, Practice, Leaderboard, or My results.
The interface and questions are in English, matching the source document.

## Included

- All 60 source questions, correct answers and original explanations, across seven domains.
- Single-answer and select-two questions.
- Full mock exam: all 60 questions shuffled; a fixed **100-minute** deadline.
- Live countdown and automatic submission when time expires in an active browser session.
- Autosaved answers, previous/next controls, question navigator and review flags.
- Resume an unfinished attempt after signing back in; closing the browser does not pause time.
- Untimed domain practice with immediate explanations; practice does not affect rankings.
- Score, incorrect-answer review, domain breakdown and downloadable JSON report.
- Top 10 distinct accounts by their best exam: score descending, elapsed time ascending, then earliest finish.
- Persistent SQLite leaderboard/results; username-only identity, with no password fields.

The PDF suggests 120 minutes. The platform deliberately uses the requested 100 minutes.
Scoring is one point per fully correct question, no partial credit, no negative marks.
The source's 75% study target is not an official passing-score claim.

## Persistence and timer behavior

Data is stored in data/exam.db next to the app. Keep that file to retain accounts and results.
An active attempt is associated with the entered username. Since usernames are not verified, another visitor can enter that same username and access its records.
After refresh, sign in again to resume. The original deadline remains in force.
If the browser or server is closed at expiry, the attempt is finalized on the next app/database interaction,
using its original deadline and the last saved answers. Late answers are rejected by the backend.

This is a local or small-group study app. Everyone must use the same running server to share a leaderboard. Username-only sign-in does not verify identity; leaderboard names and records can be impersonated.
Separate installations maintain separate databases. For hosted use, keep SQLite on a persistent disk
(EXAM_DB_PATH can set its location); ephemeral hosting will not preserve results across resets.
Public high-stakes examination features such as proctoring, identity verification, password recovery and
login rate limiting are not part of this study platform.

## Source and extraction

Questions remain attributed to Matthew Purcell. The source describes them as independent practice
questions, not actual exam questions. No question answers were generated or invented.
The application reads data/questions.json; it does not need PDF libraries at runtime.
Source fingerprint and import metadata are in data/source.json.

To reimport the PDF, install pypdf and run:

```powershell
.\.venv\Scripts\python.exe -m pip install pypdf
.\.venv\Scripts\python.exe import_pdf.py
```

## Validation

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_exam_core
```

Eight backend tests cover the bank blueprint, exact-match grading, password authentication,
resume/save behavior, deadline rejection, disconnected expiry, account ownership, submission idempotency,
and unique top-10 rankings with score/time tie-breaking.

During implementation, backend tests and Python compilation passed. Streamlit installation was blocked
by this execution environment's network restriction (WinError 10013). Consequently the live Streamlit UI
has not been launched or visually verified here. START_EXAM.bat installs the missing dependency when run
in a normal terminal with internet access.

Timer implementation follows the official fragment API:
https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment
