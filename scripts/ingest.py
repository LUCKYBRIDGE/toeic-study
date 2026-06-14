#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

try:
    from pypdf import PdfReader
except Exception as exc:  # pragma: no cover - local dependency check
    print(f"pypdf is required: {exc}", file=sys.stderr)
    sys.exit(1)

ROOT = Path(__file__).resolve().parents[1]
MATERIALS_DIR = ROOT / "materials"
OUTPUT_DIR = ROOT / "private-data" / "generated"
OUTPUT_FILE = OUTPUT_DIR / "study-items.json"
MANIFEST_FILE = OUTPUT_DIR / "materials-manifest.json"

HANGUL_RE = re.compile(r"[가-힣]")
EN_RE = re.compile(r"[A-Za-z]")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'/-]*(?:\s+[A-Za-z][A-Za-z'/-]*){0,4}")

NOISE_ENGLISH = {
    "ETS",
    "TOEIC",
    "YBM",
    "PART",
    "UNIT",
    "LC",
    "RC",
    "TEST",
    "NO TEST MATERIAL ON THIS PAGE",
    "READING TEST",
    "LISTENING TEST",
}

COMMON_CONTEXTS = [
    "The company will {term} the new policy next month.",
    "Employees should {term} the document before the meeting.",
    "The manager asked the team to review the {term} carefully.",
    "Customers can check the {term} on the company Web site.",
    "The department sent a notice about the {term} yesterday.",
    "Applicants must submit the {term} by Friday.",
]

CATEGORY_RULES = [
    ("schedule", ("deadline", "delay", "postpone", "reschedule", "advance", "expire", "reservation", "period")),
    ("business", ("policy", "agreement", "contract", "account", "department", "company", "manager", "staff")),
    ("document", ("document", "attachment", "form", "copy", "publish", "notice", "report")),
    ("workplace", ("equipment", "facility", "warehouse", "office", "safety", "goggles", "floor")),
    ("travel", ("transportation", "reservation", "region", "stay", "rent")),
    ("action-verb", ("implement", "require", "renew", "amend", "reduce", "expand", "merge", "donate", "produce")),
]


def stable_id(*parts: str) -> str:
    raw = "\n".join(parts).encode("utf-8", "ignore")
    return hashlib.sha1(raw).hexdigest()[:16]


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def extract_pdf_text(path: Path) -> tuple[str, int, str | None]:
    try:
        reader = PdfReader(str(path))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages), len(reader.pages), None
    except Exception as exc:
        return "", 0, str(exc)


def extract_docx_text(path: Path) -> tuple[str, int, str | None]:
    try:
        with ZipFile(path) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", "ignore")
        text = re.sub(r"<[^>]+>", " ", xml)
        return normalize_space(text), 1, None
    except Exception as exc:
        return "", 0, str(exc)


def split_sentences(text: str) -> list[str]:
    compact = normalize_space(text)
    pieces = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", compact)
    sentences = []
    for piece in pieces:
        value = normalize_space(piece)
        if 35 <= len(value) <= 240 and EN_RE.search(value):
            if "Unauthorized copying" in value:
                continue
            sentences.append(value)
    return sentences


def clean_term(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"^[0-9]+\s*", "", value)
    value = value.strip(" -_/.,:;()[]")
    return value


def clean_meaning(value: str) -> str:
    value = normalize_space(value)
    value = re.sub(r"[_]{2,}.*$", "", value)
    value = value.strip(" -_/.,:;()[]")
    return value


def is_good_term(term: str) -> bool:
    if not term or len(term) < 2 or len(term) > 48:
        return False
    if term.upper() in NOISE_ENGLISH:
        return False
    if not EN_RE.search(term) or HANGUL_RE.search(term):
        return False
    if re.search(r"\d", term):
        return False
    words = term.split()
    if len(words) > 5:
        return False
    return all(len(w.strip("'-/")) > 1 for w in words)


def is_good_meaning(meaning: str) -> bool:
    if not meaning or len(meaning) < 2 or len(meaning) > 80:
        return False
    return bool(HANGUL_RE.search(meaning))


def extract_pairs_from_line(line: str) -> list[tuple[str, str]]:
    line = normalize_space(line)
    if not line or "저작권" in line or "허락 없이" in line:
        return []
    matches = list(re.finditer(r"([A-Za-z][A-Za-z'/-]*(?:\s+[A-Za-z][A-Za-z'/-]*){0,4})\s+([가-힣][가-힣A-Za-z0-9\s~/·,\[\]()'-]{1,80})", line))
    pairs: list[tuple[str, str]] = []
    for match in matches:
        term = clean_term(match.group(1))
        meaning = clean_meaning(match.group(2))
        meaning = re.split(r"\s{2,}| [A-Za-z][A-Za-z'/-]{2,}\s+", meaning)[0]
        if is_good_term(term) and is_good_meaning(meaning):
            pairs.append((term, meaning))
    return pairs


def source_label(path: Path) -> str:
    rel = path.relative_to(ROOT)
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "materials":
        return f"{parts[1]} / {path.name}"
    return path.name


def classify(term: str, meaning: str, source: str) -> list[str]:
    haystack = f"{term} {meaning} {source}".lower()
    tags = set()
    for tag, words in CATEGORY_RULES:
        if any(word in haystack for word in words):
            tags.add(tag)
    if "voca" in source.lower() or "단어" in source:
        tags.add("vocabulary")
    if "rc" in source.lower():
        tags.add("rc")
    if "lc" in source.lower():
        tags.add("lc")
    if "part 5" in source.lower() or "part5" in source.lower():
        tags.add("part5")
    if not tags:
        tags.add("general")
    return sorted(tags)


def fallback_sentence(term: str, tags: list[str]) -> str:
    if "schedule" in tags:
        return f"The team discussed the {term} during the planning meeting."
    if "document" in tags:
        return f"Please check the {term} before sending the file to the client."
    if "workplace" in tags:
        return f"The supervisor inspected the {term} before the office opened."
    if "travel" in tags:
        return f"The traveler confirmed the {term} before leaving for the airport."
    if "action-verb" in tags:
        return f"The company will {term} the new policy next month."
    template = COMMON_CONTEXTS[int(stable_id(term), 16) % len(COMMON_CONTEXTS)]
    return template.format(term=term)


def find_context(term: str, sentences: list[str]) -> str | None:
    pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
    for sentence in sentences:
        if pattern.search(sentence) and not HANGUL_RE.search(sentence):
            return sentence
    return None


def build_choices(items: list[dict]) -> None:
    meanings = []
    seen = set()
    for item in items:
        meaning = item["answer"]
        if meaning not in seen:
            meanings.append(meaning)
            seen.add(meaning)
    for item in items:
        pool = [m for m in meanings if m != item["answer"]]
        pool.sort(key=lambda value: stable_id(item["id"], value))
        choices = pool[:3] + [item["answer"]]
        choices.sort(key=lambda value: stable_id(value, item["id"]))
        item["choices"] = choices
        item["answerIndex"] = choices.index(item["answer"])


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [
            path
            for path in MATERIALS_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in {".pdf", ".docx"}
        ]
    )
    pair_map: dict[tuple[str, str], dict] = {}
    all_sentences: list[str] = []
    manifest = []

    for path in files:
        if path.suffix.lower() == ".pdf":
            text, pages, error = extract_pdf_text(path)
        else:
            text, pages, error = extract_docx_text(path)
        rel = str(path.relative_to(ROOT))
        entry = {
            "path": rel,
            "kind": path.suffix.lower().lstrip("."),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
            "pages": pages,
            "status": "error" if error else "ok",
            "error": error,
        }
        manifest.append(entry)
        if error:
            continue

        source = source_label(path)
        sentences = split_sentences(text)
        all_sentences.extend(sentences)
        for line in text.splitlines():
            for term, meaning in extract_pairs_from_line(line):
                key = (term.lower(), meaning)
                if key not in pair_map:
                    tags = classify(term, meaning, source)
                    pair_map[key] = {
                        "id": stable_id(term.lower(), meaning, source),
                        "term": term,
                        "answer": meaning,
                        "tags": tags,
                        "source": source,
                        "sourcePath": rel,
                        "mode": "meaning-in-context",
                    }

    items = []
    for item in pair_map.values():
        context = find_context(item["term"], all_sentences) or fallback_sentence(item["term"], item["tags"])
        item["sentence"] = context
        item["blankSentence"] = re.sub(
            rf"\b{re.escape(item['term'])}\b",
            "_____",
            context,
            count=1,
            flags=re.IGNORECASE,
        )
        item["prompt"] = f"문맥상 {item['term']}의 뜻은?"
        items.append(item)

    items.sort(key=lambda item: (item["source"], item["term"].lower(), item["answer"]))
    build_choices(items)

    stats = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceFileCount": len(files),
        "itemCount": len(items),
        "tagCounts": dict(Counter(tag for item in items for tag in item["tags"]).most_common()),
    }
    OUTPUT_FILE.write_text(
        json.dumps({"version": 1, "stats": stats, "items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    MANIFEST_FILE.write_text(
        json.dumps({"version": 1, "generatedAt": stats["generatedAt"], "files": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {len(items)} study items to {OUTPUT_FILE.relative_to(ROOT)}")
    print(f"Wrote manifest for {len(files)} files to {MANIFEST_FILE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
