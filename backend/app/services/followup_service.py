"""
Follow-up Question Generation (Phase 3 — local LLM)
────────────────────────────────────────────────────
Uses the patient's OWN interview answers as context to generate 1–4 short,
patient-friendly follow-up questions in English / Hindi / Gujarati, powered
by the free local model (Ollama / LM Studio via LocalLLMClient).

Safety contract (enforced here, independent of the model):
  * Output is VALIDATED: JSON array, length bounds, single-line, native
    script check, and a blocklist regex that rejects dosages / medication
    instructions / diagnoses / any wording that could downplay symptoms.
  * The LLM only ever ADDS questions. Red-flag escalation is computed by
    the deterministic RedFlagEngine in the router and can never be
    suppressed by model output.
  * Any timeout, transport error, unparseable or fully-invalid output
    degrades to predefined, clinically-reviewed ontology questions
    (QUESTION_TREES / COMMON_QUESTIONS) — the safe fallback.
"""

import re
import json
import logging
from typing import Any, Dict, List, Optional

from backend.app.clinical.ontology import QUESTION_TREES, COMMON_QUESTIONS
from backend.app.services.local_llm import LocalLLMClient

logger = logging.getLogger(__name__)

MAX_QUESTIONS = 4
MIN_LEN = 8
MAX_LEN = 220

# ── Safety validation patterns (reject, never rewrite) ───────────────────
_FORBIDDEN_PATTERNS = [
    re.compile(r"\b\d+\s?(mg|ml|gm|g)\b", re.IGNORECASE),          # dosages
    re.compile(r"\b(take|consume|swallow)\s+\w*\s*(tablet|pill|capsule|medicine|paracetamol|dolo|crocin)\w*\b", re.IGNORECASE),
    re.compile(r"\b(ignore|disregard)\b.*\b(pain|symptom|warning|danger|bleed)", re.IGNORECASE),
    re.compile(r"(don'?t|do not|no need).{0,18}worry", re.IGNORECASE),
    re.compile(r"\b(not serious|nothing wrong|perfectly fine|harmless)\b", re.IGNORECASE),
    re.compile(r"\b(diagnos\w*|prognos\w*)\b", re.IGNORECASE),
    re.compile(r"\b(you (probably|likely) have|you are suffering|it is cancer|you are dying)\b", re.IGNORECASE),
    re.compile(r"\b(prescrib\w*|inject\w*)\b", re.IGNORECASE),
]

# Native-script requirements per language (fallback-safe: rejected output
# simply yields guideline questions, never a crash).
_SCRIPT_RANGES = {
    "hi": re.compile(r"[\u0900-\u097F]"),  # Devanagari
    "gu": re.compile(r"[\u0A80-\u0AFF]"),  # Gujarati
}

# Deterministic complaint → ontology question-tree mapping. Multilingual
# keywords written as unicode escapes for script-safety of this source file:
#  EN, romanized Hindi, Devanagari (hi), Gujarati (gu).
_TREE_KEYWORDS: Dict[str, List[str]] = {
    "CHEST_PAIN": [
        "chest", "seene", "heart",
        "\u0938\u0940\u0928\u093e", "\u091b\u093e\u0924\u0940", "\u0926\u093f\u0932",  # सीना छाती दिल
        "\u0938\u0940\u0928\u0947",                                              # सीने (oblique form; Phase 5 eval gap)
        "\u0a9b\u0abe\u0aa4\u0ac0",                                              # છાતી
    ],
    "ASTHMA_RESPIRATORY": [
        "breath", "cough", "asthma", "ashthama",
        "\u0936\u094d\u0935\u093e\u0938", "\u0916\u093e\u0902\u0938\u0940",             # श्वास खांसी
        "\u0938\u093e\u0902\u0938",                                              # सांस (Phase 5 eval gap: "सांस लेने में तकलीफ")
        "\u0ab6\u0acd\u0ab5\u0abe\u0ab8", "\u0ab8\u0ac1\u0a82\u0a9d\u0abe\u0ab8",       # શ્વાસ/sho
    ],
    "FEVER_INFECTION": [
        "fever", "bukhar", "temperature",
        "\u092c\u0941\u0916\u093e\u0930", "\u091c\u094d\u0935\u0930",                   # बुखार ज्वर
        "\u0aa4\u0abe\u0ab5",                                                   # તાવ
    ],
    "DIABETES": [
        "diabet", "sugar", "madhumeh", "numb",
        "\u092e\u0927\u0941\u092e\u0947\u0939", "\u0936\u0941\u0917\u0930",             # मधुमेह शुगर
        "\u0aae\u0aa7\u0ac1\u0aae\u0ac7\u0ab9",                                     # મધુમેહ (fixed: was Devanagari \u0941 matra, never matched Gujarati)
    ],
    "ABDOMINAL_PAIN": [
        "stomach", "abdomen", "pet", "udhar", "tummy",
        "\u092a\u0947\u091f",                                                   # पेट
        "\u0a89\u0aa6\u0ab0", "\u0aaa\u0ac7\u0a9f",                               # ઉદર પેટ
    ],
}

LANGUAGE_NAMES = {
    "en": "English (Latin script)",
    "hi": "Hindi in Devanagari script (\u0939\u093f\u0928\u094d\u0926\u0940)",
    "gu": "Gujarati in Gujarati script (\u0a97\u0ac1\u0a9c\u0ab0\u0abe\u0aa4\u0ac0)",
}

SYSTEM_PROMPT = (
    "You are a clinical intake assistant at a hospital OPD kiosk in India. "
    "Your ONLY job is to ask short, warm, patient-friendly follow-up questions "
    "that help the patient describe their history better. "
    "STRICT RULES: never diagnose, never mention medicines or doses, never say a "
    "symptom is minor or can be ignored, never give advice — only questions. "
    "Respond ONLY with a JSON array of question strings. No other text."
)


def _keyword_tree(complaint_text: str) -> str:
    low = (complaint_text or "").lower()
    for tree, words in _TREE_KEYWORDS.items():
        if any(w in low for w in words):
            return tree
    return "GENERAL_OPD"


def localize(q, language: str) -> str:
    """Ontology question → display text; honest English when no translation."""
    text = q.translations.get(language)
    return text if text else q.question_en


def guideline_questions(
    complaint_text: str,
    answered_sections: List[str],
    language: str,
    count: int,
) -> List[Dict[str, str]]:
    """
    Predefined, clinically-reviewed fallback questions from the ontology:
    complaint-specific tree first (skipping already-answered sections),
    then general common questions.
    """
    answered = {s.upper() for s in answered_sections if s}
    tree = QUESTION_TREES.get(_keyword_tree(complaint_text), QUESTION_TREES["GENERAL_OPD"])
    picked: List[Dict[str, str]] = []
    seen_text = set()

    for q in list(tree) + list(COMMON_QUESTIONS):
        if len(picked) >= count:
            break
        if q.section.upper() in answered:
            continue
        text = localize(q, language)
        key = text.lower().strip()
        if key in seen_text:
            continue
        seen_text.add(key)
        picked.append({"text": text, "section": q.section, "provenance": "guideline"})
    return picked


def parse_json_array(raw: str) -> Optional[List[Any]]:
    """Tolerant extraction of a JSON string array from model output."""
    if not raw:
        return None
    candidates = [raw.strip()]
    m = re.search(r"\[[\s\S]*\]", raw)
    if m:
        candidates.insert(0, m.group(0))
    for cand in candidates:
        try:
            data = json.loads(cand)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and isinstance(data.get("questions"), list):
                return data["questions"]
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _has_native_script(text: str, language: str) -> bool:
    if language not in _SCRIPT_RANGES:
        return True  # English: just require no Indic leakage
    pattern = _SCRIPT_RANGES[language]
    native = len(pattern.findall(text))
    return native / max(1, len(text)) >= 0.3


def validate_question(text: Any, language: str) -> Optional[str]:
    """Return the cleaned question, or None if it fails any safety rule."""
    if not isinstance(text, str):
        # some models emit {"question": "..."} objects
        if isinstance(text, dict):
            text = next(iter(text.values()), None)
        if not isinstance(text, str):
            return None
    cleaned = " ".join(text.split()).strip()
    if not (MIN_LEN <= len(cleaned) <= MAX_LEN):
        return None
    if "?" not in cleaned:
        return None
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(cleaned):
            logger.warning(f"Rejected unsafe LLM question: {cleaned[:60]!r}")
            return None
    if language in _SCRIPT_RANGES:
        if not _has_native_script(cleaned, language):
            return None
    else:  # English must not drift into Indic scripts
        if _SCRIPT_RANGES["hi"].search(cleaned) or _SCRIPT_RANGES["gu"].search(cleaned):
            return None
    return cleaned


def _build_user_prompt(
    statements: List[Dict[str, str]], language: str, count: int
) -> str:
    lang_name = LANGUAGE_NAMES.get(language, LANGUAGE_NAMES["en"])
    context = [
        {"asked": s.get("question_text", ""), "patient_answer": (s.get("answer_text") or "")[:300]}
        for s in statements if (s.get("answer_text") or "").strip()
    ]
    return (
        f"Write exactly {count} short follow-up questions for the next interview step, "
        f"in {lang_name}. Each question max 160 characters, ending with '?'. "
        f"Base them only on what the patient said; do not repeat what was already answered.\n\n"
        f"Patient interview so far (JSON):\n{json.dumps(context, ensure_ascii=False, indent=1)}\n\n"
        f"Return ONLY a JSON array of {count} question strings."
    )


async def generate_followups(
    statements: List[Dict[str, str]],
    language: str = "en",
    max_questions: int = 3,
    answered_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Main entry: local-LLM questions first, guideline fallback for anything
    missing/unsafe. Never raises — worst case returns guideline questions.
    """
    language = (language or "en").strip().lower()
    if language not in LANGUAGE_NAMES:
        language = "en"
    count = max(1, min(int(max_questions or 3), MAX_QUESTIONS))

    complaint_text = " ".join(
        (s.get("answer_text") or "") for s in statements[:2]
    )
    fallback_pool = guideline_questions(
        complaint_text, answered_sections or [], language, count + 2
    )

    questions: List[Dict[str, str]] = []
    source = "rule_fallback"

    try:
        client = LocalLLMClient()
        raw = await client.chat(
            messages=[{"role": "user", "content": _build_user_prompt(statements, language, count)}],
            system=SYSTEM_PROMPT,
            temperature=0.3,
            max_tokens=350,
            json_mode=True,
        )
        if raw:
            parsed = parse_json_array(raw)
            if parsed:
                for item in parsed:
                    if len(questions) >= count:
                        break
                    valid = validate_question(item, language)
                    if valid:
                        questions.append({"text": valid, "section": "FOLLOW_UP", "provenance": "local_ai"})
                if questions:
                    source = "local_llm"
    except Exception as exc:  # defensive: generation must never break intake
        logger.error(f"Follow-up generation error: {exc}")

    # Top up with predefined guideline questions (deduplicated)
    seen = {q["text"].lower() for q in questions}
    for fb in fallback_pool:
        if len(questions) >= count:
            break
        if fb["text"].lower() in seen:
            continue
        questions.append(fb)
        source = "hybrid" if source == "local_llm" else source

    return {
        "questions": questions[:count],
        "source": source if questions else "rule_fallback",
        "language": language,
        "engine": "local_ollama_or_openai_compat" if source != "rule_fallback" else "ontology_question_trees",
    }
