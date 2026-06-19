#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "private-data" / "generated"
RAW_FILE = GENERATED_DIR / "study-items.json"
APPROVED_FILE = GENERATED_DIR / "study-items.approved.json"
LEXICON_FILE = GENERATED_DIR / "study-items.lexicon-approved.json"
REVIEW_FILE = GENERATED_DIR / "study-items.review.json"
REJECTED_FILE = GENERATED_DIR / "study-items.rejected.json"
REPORT_FILE = GENERATED_DIR / "quality-report.md"

HANGUL_RE = re.compile(r"[가-힣]")
EN_RE = re.compile(r"[A-Za-z]")
TERM_RE = re.compile(r"^[A-Za-z][A-Za-z'/-]*(?:\s+[A-Za-z][A-Za-z'/-]*){0,4}$")
BAD_KOREAN_FRAGMENTS = ("젂", "슸", "핚", "릱", "읶", "읷", "젃", "묷", "공슸")
BAD_SOURCE_WORDS = ("answers", "answer", "translation", "번역", "정답", "해설", "문제지", "test.pdf")
GOOD_SOURCE_WORDS = ("voca", "단어장", "어휘", "필수표현")
SOURCE_PRIORITY = {
    "voca": 3,
    "단어장": 3,
    "어휘": 3,
    "필수표현": 2,
}

STOP_TERMS = {
    "ets",
    "toeic",
    "ybm",
    "part",
    "unit",
    "test",
    "reading test",
    "listening test",
    "no test material",
}

GENERIC_DISTRACTORS = [
    "연기하다",
    "검토하다",
    "제출하다",
    "확인하다",
    "시행하다",
    "공지",
    "마감일",
    "시설",
    "계약",
    "고객",
    "직원",
    "할인",
    "배송",
]

VERB_OBJECTS = [
    ("conduct", "a survey", "설문 조사를"),
    ("implement", "a policy", "정책을"),
    ("submit", "a report", "보고서를"),
    ("postpone", "the meeting", "회의를"),
    ("reschedule", "the appointment", "약속 일정을"),
    ("renew", "the contract", "계약을"),
    ("review", "the document", "문서를"),
    ("confirm", "the reservation", "예약을"),
    ("attach", "the file", "파일을"),
    ("affix", "a label", "라벨을"),
    ("reimburse", "the employee", "직원에게 비용을"),
    ("expand", "the service", "서비스를"),
    ("reduce", "the cost", "비용을"),
    ("merge", "the departments", "부서를"),
]


def load_items() -> list[dict]:
    raw = json.loads(RAW_FILE.read_text(encoding="utf-8"))
    return raw.get("items", [])


def clean_meaning(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"\s+\d{1,3}$", "", value)
    value = re.sub(r"\s+(in|on|at|by|for|to|from|with|as|be|of|and|or)$", "", value, flags=re.I)
    return value.strip(" ,;/")


def source_score(source: str) -> int:
    lowered = source.lower()
    if any(word in lowered for word in BAD_SOURCE_WORDS):
        return -2
    score = 0
    for word, value in SOURCE_PRIORITY.items():
        if word in lowered:
            score = max(score, value)
    return score


def quality_reasons(item: dict) -> list[str]:
    reasons: list[str] = []
    term = item.get("term", "").strip()
    answer = item.get("answer", "").strip()
    source = item.get("source", "")
    cleaned_answer = clean_meaning(answer)

    if not TERM_RE.match(term):
        reasons.append("term-format")
    if term.lower() in STOP_TERMS or any(stop in term.lower() for stop in STOP_TERMS):
        reasons.append("term-is-metadata")
    if re.search(r"[A-Z]{4,}", term) and term.isupper():
        reasons.append("term-is-acronym")
    if not HANGUL_RE.search(cleaned_answer):
        reasons.append("meaning-no-korean")
    if EN_RE.search(cleaned_answer):
        reasons.append("meaning-has-english-fragment")
    if re.search(r"\d", cleaned_answer):
        reasons.append("meaning-has-page-number")
    if any(fragment in cleaned_answer for fragment in BAD_KOREAN_FRAGMENTS):
        reasons.append("meaning-has-broken-korean")
    if len(cleaned_answer) > 36:
        reasons.append("meaning-too-long")
    if source_score(source) < 1:
        reasons.append("source-not-vocab")

    return reasons


def infer_usage(term: str, meaning: str) -> str:
    lower = term.lower()
    if " " in lower:
        if lower.startswith(("in ", "at ", "on ", "by ", "for ", "with ", "without ", "due to", "owing to")):
            return "adverbial-phrase"
        if lower.startswith(("be ", "become ", "remain ")):
            return "verb-phrase"
        if "하다" in meaning:
            return "verb-phrase"
        return "noun-phrase"
    if "하다" in meaning or meaning.endswith("되다"):
        return "verb"
    if meaning.endswith(("한", "있는", "없는", "적인", "된")):
        return "adjective"
    if lower.endswith("ly") or meaning.endswith(("게", "히")):
        return "adverb"
    return "noun"


def particle(value: str) -> str:
    if not value:
        return "을"
    code = ord(value[-1])
    if 0xAC00 <= code <= 0xD7A3:
        return "을" if (code - 0xAC00) % 28 else "를"
    return "을"


def verb_object(term: str) -> tuple[str, str]:
    lower = term.lower()
    for key, obj, ko in VERB_OBJECTS:
        if lower == key:
            return obj, ko
    return "the request", "요청을"


def build_learning_item(item: dict, cleaned_answer: str) -> dict:
    term = item["term"].strip()
    usage = infer_usage(term, cleaned_answer)
    tags = sorted(set(item.get("tags") or ["vocabulary"]) | {"approved"})

    if usage == "verb":
        obj, ko_obj = verb_object(term)
        sentence = f"The manager will {term} {obj} before Friday."
        sentence_ko = f"관리자는 금요일 전까지 {ko_obj} {cleaned_answer}."
        grammar_focus = "verb"
        grammar_note = "동사 어휘는 주어 뒤에서 동작을 나타내며, 뒤에 목적어가 오는지 함께 확인합니다."
    elif usage == "adjective":
        sentence = f"The report includes {term} information about the new service."
        sentence_ko = f"그 보고서에는 새 서비스에 대한 {cleaned_answer} 정보가 포함되어 있다."
        grammar_focus = "adjective"
        grammar_note = "형용사는 명사 앞이나 be동사 뒤에서 명사의 상태와 성질을 설명합니다."
    elif usage == "adverb":
        sentence = f"The supervisor explained the procedure {term} during the meeting."
        sentence_ko = f"관리자는 회의 중 절차를 {cleaned_answer} 설명했다."
        grammar_focus = "adverb"
        grammar_note = "부사는 동사, 형용사, 문장 전체를 꾸미며 동작의 방식이나 정도를 나타냅니다."
    elif usage == "adverbial-phrase":
        sentence = f"Employees must register {term} to attend the training session."
        sentence_ko = f"직원들은 교육에 참석하려면 {cleaned_answer} 등록해야 한다."
        grammar_focus = "phrase"
        grammar_note = "전치사구나 부사구는 문장에서 시간, 조건, 방식 같은 배경 정보를 더합니다."
    elif usage == "verb-phrase":
        phrase = term[3:] if term.lower().startswith("be ") else term
        sentence = f"Employees should be {phrase} when assisting customers."
        sentence_ko = f"직원들은 고객을 도울 때 {cleaned_answer} 상태여야 한다."
        grammar_focus = "verb-phrase"
        grammar_note = "be 동사와 함께 쓰이는 표현은 뒤의 형용사나 구 전체를 하나의 의미 단위로 봅니다."
    elif usage == "noun-phrase":
        sentence = f"The manager discussed the {term} during the planning meeting."
        sentence_ko = f"관리자는 계획 회의에서 {cleaned_answer}{particle(cleaned_answer)} 논의했다."
        grammar_focus = "noun-phrase"
        grammar_note = "명사구는 문장에서 주어, 목적어, 보어 역할을 할 수 있습니다."
    else:
        sentence = f"The manager checked the {term} before the meeting."
        sentence_ko = f"관리자는 회의 전에 {cleaned_answer}{particle(cleaned_answer)} 확인했다."
        grammar_focus = "noun"
        grammar_note = "명사는 사람, 사물, 개념을 나타내며 관사나 형용사와 함께 자주 쓰입니다."

    choices = build_choices(cleaned_answer)
    return {
        **item,
        "answer": cleaned_answer,
        "termKey": normalize_term_key(term),
        "contextId": f"ctx-{hashlib.sha1(sentence.encode('utf-8')).hexdigest()[:12]}",
        "choices": choices,
        "answerIndex": choices.index(cleaned_answer),
        "usage": usage,
        "quality": "lexicon-approved",
        "sentence": sentence,
        "sentenceKo": sentence_ko,
        "blankSentence": sentence.replace(term, "_____", 1),
        "grammarFocus": grammar_focus,
        "grammarNote": grammar_note,
        "tags": tags,
        "prompt": f"문맥상 {term}의 뜻은?",
    }


def normalize_term_key(term: str) -> str:
    return re.sub(r"\s+", " ", term.strip().lower())


def build_choices(answer: str) -> list[str]:
    choices = [answer]
    for candidate in GENERIC_DISTRACTORS:
        if candidate != answer and candidate not in choices:
            choices.append(candidate)
        if len(choices) == 4:
            break
    choices.sort()
    return choices


def dedupe(items: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    result = []
    for item in sorted(items, key=lambda value: (-source_score(value.get("source", "")), value["term"].lower())):
        key = (item["term"].lower(), item["answer"])
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return sorted(result, key=lambda value: value["term"].lower())


def write_dataset(path: Path, items: list[dict], extra: dict | None = None) -> None:
    stats = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "itemCount": len(items),
        "tagCounts": dict(Counter(tag for item in items for tag in item.get("tags", [])).most_common()),
    }
    if extra:
        stats.update(extra)
    path.write_text(json.dumps({"version": 1, "stats": stats, "items": items}, ensure_ascii=False, indent=2), encoding="utf-8")


def approved_item_count() -> int:
    if not APPROVED_FILE.exists():
        return 0
    try:
        data = json.loads(APPROVED_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    return len(data.get("items", []))


def main() -> int:
    raw_items = load_items()
    lexicon_approved = []
    review = []
    rejected = []
    reason_counts: Counter[str] = Counter()

    for item in raw_items:
        reasons = quality_reasons(item)
        reason_counts.update(reasons)
        cleaned_answer = clean_meaning(item.get("answer", ""))
        if not reasons:
            lexicon_approved.append(build_learning_item(item, cleaned_answer))
        elif source_score(item.get("source", "")) >= 1 and not any(reason.startswith("meaning-has-broken") for reason in reasons):
            review.append({**item, "quality": "review", "qualityReasons": reasons, "cleanedAnswer": cleaned_answer})
        else:
            rejected.append({**item, "quality": "rejected", "qualityReasons": reasons, "cleanedAnswer": cleaned_answer})

    lexicon_approved = dedupe(lexicon_approved)
    review = review[:1000]
    rejected = rejected[:1000]
    preserved_approved_count = approved_item_count()

    # `study-items.approved.json` is curated by source-specific builders. Keep this
    # broad validator from overwriting approved study data with provisional output.
    write_dataset(LEXICON_FILE, lexicon_approved, {"rawItemCount": len(raw_items), "reviewCount": len(review), "rejectedSampleCount": len(rejected)})
    write_dataset(REVIEW_FILE, review, {"rawItemCount": len(raw_items)})
    write_dataset(REJECTED_FILE, rejected, {"rawItemCount": len(raw_items)})

    report_lines = [
        "# TOEIC Study Data Quality Report",
        "",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Raw items: {len(raw_items)}",
        f"- Study-approved items preserved: {preserved_approved_count}",
        f"- Lexicon-approved items: {len(lexicon_approved)}",
        f"- Review sample items: {len(review)}",
        f"- Rejected sample items: {len(rejected)}",
        "",
        "## Rejection / Review Reasons",
        "",
    ]
    for reason, count in reason_counts.most_common():
        report_lines.append(f"- {reason}: {count}")
    report_lines.extend(["", "## Lexicon-Approved Source Counts", ""])
    for source, count in Counter(item["source"] for item in lexicon_approved).most_common():
        report_lines.append(f"- {count}: {source}")
    REPORT_FILE.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"Study-approved preserved: {preserved_approved_count}")
    print(f"Lexicon-approved {len(lexicon_approved)} of {len(raw_items)} raw items")
    print(f"Wrote {LEXICON_FILE.relative_to(ROOT)}")
    print(f"Wrote {REPORT_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
