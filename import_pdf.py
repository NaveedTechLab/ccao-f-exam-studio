"""Rebuild questions.json from the supplied PDF. Requires pypdf."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent
parser = argparse.ArgumentParser()
parser.add_argument("pdf", nargs="?", default=str(ROOT / "Matthew Purcell - CCAO-F exam.pdf"))
args = parser.parse_args()
source = Path(args.pdf)
reader = PdfReader(source)
text = " ".join(" ".join(p.extract_text().split()) for p in reader.pages)
text = re.sub(r"CCAO-F Practice Questions · Matthew Purcell · linkedin\.com/in/purcellmatthew \d+", "", text)
domains = re.findall(r"Domain [1-7]: (.*?) \(\d+%\)", text)
assert len(domains) == 7, "Expected seven domains"
for domain in domains:
    text = re.sub(r"Domain [1-7]: " + re.escape(domain) + r"(?: \(\d+%\))?", "", text)
questions_text, answers_text = text.split("Answer Key & Rationales", 1)
headers = list(re.finditer(r"Question (\d+\.\d+) · Multiple (choice|response) · select (ONE|TWO|THREE) ", questions_text))
keys = list(re.finditer(r"(\d+\.\d+) — Correct: ([A-E](?:, [A-E])*) ", answers_text))
assert len(headers) == len(keys) == 60, "Expected 60 questions and answer keys"
answers = {}
for i, match in enumerate(keys):
    end = keys[i+1].start() if i+1 < len(keys) else len(answers_text)
    rationale = answers_text[match.end():end].split("How did you go?")[0].strip()
    answers[match[1]] = (match[2].split(", "), rationale)
bank = []
for i, match in enumerate(headers):
    end = headers[i+1].start() if i+1 < len(headers) else len(questions_text)
    body = questions_text[match.end():end].strip()
    options = list(re.finditer(r"(?:^| )([A-E])\. ", body))
    choice_map = {o[1]: body[o.end():options[j+1].start() if j+1 < len(options) else len(body)].strip()
                  for j, o in enumerate(options)}
    correct, rationale = answers[match[1]]
    count = {"ONE":1,"TWO":2,"THREE":3}[match[3]]
    assert count == len(correct) and set(correct) <= set(choice_map)
    assert len(choice_map) == (4 if count == 1 else 5)
    bank.append(dict(id=match[1], domain=domains[int(match[1].split(".")[0])-1], select=count,
                     question=body[:options[0].start()].strip(), options=choice_map, answer=correct, explanation=rationale))
assert len({q["id"] for q in bank}) == 60
out = ROOT / "data"
out.mkdir(exist_ok=True)
(out / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
(out / "source.json").write_text(json.dumps({"filename": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "author": "Matthew Purcell", "pages": len(reader.pages), "questions": len(bank), "source_suggested_minutes":120,
    "app_minutes":100, "note":"Independent practice material. Questions and rationales extracted; whitespace normalized."}, indent=2), encoding="utf-8")
print(f"Imported {len(bank)} questions across {len(domains)} domains.")
