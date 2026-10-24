"""
MediKiosk — Phase 5: Multilingual Retrieval Evaluation harness.

Question: does multilingual SEMANTIC retrieval measurably improve
follow-up question relevance / patient-history context over the current
deterministic keyword-routing baseline (followup_service.guideline_questions)?

Methodology (pre-registered, reproducible):
  * Corpus = the 22 predefined clinically-reviewed ontology questions
    (QUESTION_TREES + COMMON_QUESTIONS), indexed in English + Hindi
    (the only texts that exist — the corpus has no Gujarati translations).
  * Evaluation set = SYNTHETIC patient-voice queries in English, Hindi and
    Gujarati (plus romanized Hindi). Never real patient data.
  * Three ranking methods are compared on identical gold labels:
      1. "keyword"  — the production baseline: _keyword_tree() routing,
                      then tree order + COMMON_QUESTIONS.
      2. "lexical"  — TF-IDF (word + char_wb n-grams) cosine retrieval.
      3. "e5"       — intfloat/multilingual-e5-small embeddings using the
                      documented "query: " / "passage: " prefixes (CPU only).
  * Metrics: top-1 tree accuracy, gold-question hit@3 / recall@3, MRR@5,
      per-language native-script correctness of the returned question text,
      mean latency per query, and process RSS (memory) per method.
  * Evidence gate (decided BEFORE measuring): retrieval is integrated into
    the service only if it improves top-1 tree accuracy or hit@3 by
    >= +10 percentage points ABSOLUTE on this set, with mean retrieval
    latency < 300 ms/query (warm, excl. model load). Otherwise the simpler
    baseline stays and the evidence is documented.

Run from the repository root:
    python -X utf8 -m backend.evaluation.multilingual_retrieval_eval [--methods keyword,lexical] [--json out.json]

This module NEVER mutates application behaviour; it only reads the ontology.
"""

import argparse
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

# Repo root must be importable when executed as a plain script.
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.app.clinical.ontology import QUESTION_TREES, COMMON_QUESTIONS
from backend.app.services.followup_service import _keyword_tree  # baseline logic, read-only

# ── Synthetic evaluation set (no real patient data) ───────────────────────
# gold_tree  = complaint domain the query belongs to (GENERAL_OPD = out of scope)
# gold_questions = clinically relevant ontology question ids (any of them counts
#                  as a hit; the FULL set measures recall).
EVAL_SET: List[Dict[str, Any]] = [
    # ── English ──────────────────────────────────────────────────────────
    {"id": "en01", "lang": "en", "query": "I have had continuous chest pain since this morning",
     "gold_tree": "CHEST_PAIN", "gold_questions": ["cp_socrates_site", "cp_socrates_onset"]},
    {"id": "en02", "lang": "en", "query": "My blood sugar is very high and I feel thirsty all the time",
     "gold_tree": "DIABETES", "gold_questions": ["dm_duration", "dm_hba1c", "dm_medications"]},
    {"id": "en03", "lang": "en", "query": "Shortness of breath at night with a wheezing sound",
     "gold_tree": "ASTHMA_RESPIRATORY", "gold_questions": ["resp_symptoms", "resp_triggers"]},
    {"id": "en04", "lang": "en", "query": "Burning sensation in my stomach after meals and nausea",
     "gold_tree": "ABDOMINAL_PAIN", "gold_questions": ["abdo_site", "abdo_associated"]},
    {"id": "en05", "lang": "en", "query": "High fever for the last three days with body ache",
     "gold_tree": "FEVER_INFECTION", "gold_questions": ["fever_duration", "fever_pattern"]},
    {"id": "en06", "lang": "en", "query": "Numbness and tingling in both my feet",
     "gold_tree": "DIABETES", "gold_questions": ["dm_complications"]},
    {"id": "en07", "lang": "en", "query": "I came for a general health checkup, no specific problem",
     "gold_tree": "GENERAL_OPD", "gold_questions": ["gen_chief_complaint"]},
    {"id": "en08", "lang": "en", "query": "I forgot my appointment date, where do I report?",
     "gold_tree": "GENERAL_OPD", "gold_questions": ["gen_chief_complaint"]},
    # ── Hindi (Devanagari) ───────────────────────────────────────────────
    {"id": "hi01", "lang": "hi", "query": "मुझे सीने में दर्द है और बाएँ हाथ में फैल रहा है",
     "gold_tree": "CHEST_PAIN", "gold_questions": ["cp_socrates_site", "cp_socrates_radiation"]},
    {"id": "hi02", "lang": "hi", "query": "रात को सांस लेने में तकलीफ होती है",
     # NOTE: 'सांस'/'तकलीफ' are NOT in the baseline keyword list (only श्वास/खांसी) —
     # a genuine lexical gap the evaluation is designed to expose.
     "gold_tree": "ASTHMA_RESPIRATORY", "gold_questions": ["resp_symptoms", "resp_triggers"]},
    {"id": "hi03", "lang": "hi", "query": "पेट में जलन और मरोड़ हो रही है",
     "gold_tree": "ABDOMINAL_PAIN", "gold_questions": ["abdo_site", "abdo_associated"]},
    {"id": "hi04", "lang": "hi", "query": "तीन दिन से तेज़ बुखार है",
     "gold_tree": "FEVER_INFECTION", "gold_questions": ["fever_duration", "fever_pattern"]},
    {"id": "hi05", "lang": "hi", "query": "खून में शुगर बढ़ गई है, कितनी दिनों से दवा लूँ",
     "gold_tree": "DIABETES", "gold_questions": ["dm_duration", "dm_medications", "dm_hba1c"]},
    {"id": "hi06", "lang": "hi", "query": "चलने फिरने पर सांस फूलती है",
     # Another baseline keyword gap ('सांस फूलती' absent from _TREE_KEYWORDS).
     "gold_tree": "ASTHMA_RESPIRATORY", "gold_questions": ["resp_symptoms"]},
    {"id": "hi07", "lang": "hi", "query": "केवल सामान्य जाँच के लिए आया हूँ",
     "gold_tree": "GENERAL_OPD", "gold_questions": ["gen_chief_complaint"]},
    # ── Gujarati (Gujarati script) — corpus has NO Gujarati question text ─
    {"id": "gu01", "lang": "gu", "query": "મને છાતીમાં દુખાવો થાય છે",
     "gold_tree": "CHEST_PAIN", "gold_questions": ["cp_socrates_site", "cp_socrates_onset"]},
    {"id": "gu02", "lang": "gu", "query": "શ્વાસ લેવામાં તકલીફ પડે છે",
     "gold_tree": "ASTHMA_RESPIRATORY", "gold_questions": ["resp_symptoms", "resp_triggers"]},
    {"id": "gu03", "lang": "gu", "query": "પેટમાં દુખાવો અને ઉબકા આવે છે",
     "gold_tree": "ABDOMINAL_PAIN", "gold_questions": ["abdo_site", "abdo_associated"]},
    {"id": "gu04", "lang": "gu", "query": "ત્રણ દિવસથી તાવ છે",
     # 'તાવ' IS in the baseline Gujarati keyword list.
     "gold_tree": "FEVER_INFECTION", "gold_questions": ["fever_duration", "fever_pattern"]},
    {"id": "gu05", "lang": "gu", "query": "મધુમેહની દવા ચાલુ છે, હાલની રિપોર્ટ ક્યાં આપવી",
     "gold_tree": "DIABETES", "gold_questions": ["dm_medications", "dm_hba1c"]},
    {"id": "gu06", "lang": "gu", "query": "સામાન્ય checkup માટે આવ્યો છું",
     "gold_tree": "GENERAL_OPD", "gold_questions": ["gen_chief_complaint"]},
    # ── Romanized Hindi (Hinglish) ───────────────────────────────────────
    {"id": "ro01", "lang": "hi", "query": "seene mein bhari pan aur dard hai",
     "gold_tree": "CHEST_PAIN", "gold_questions": ["cp_socrates_site", "cp_socrates_character"]},
    {"id": "ro02", "lang": "hi", "query": "pet mein gas aur jalan rehti hai",
     "gold_tree": "ABDOMINAL_PAIN", "gold_questions": ["abdo_site", "abdo_associated"]},
]

# Script detectors for language-correctness scoring.
_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_GUJARATI = re.compile(r"[\u0A80-\u0AFF]")


# ── Corpus ────────────────────────────────────────────────────────────────

def build_corpus() -> List[Dict[str, str]]:
    """All ontology questions as retrieval passages (id/tree + en & hi text)."""
    corpus: List[Dict[str, str]] = []
    ordered = []
    for tree, questions in QUESTION_TREES.items():
        for q in questions:
            ordered.append((tree, q))
    for q in COMMON_QUESTIONS:
        ordered.append(("COMMON", q))
    seen = set()
    for tree, q in ordered:
        if q.id in seen:
            continue
        seen.add(q.id)
        corpus.append({
            "id": q.id,
            "tree": tree,
            "section": q.section,
            "en": q.question_en,
            "hi": q.translations.get("hi", ""),
        })
    return corpus


def question_text(corpus_by_id: Dict[str, Dict[str, str]], qid: str, lang: str) -> str:
    """Localized display text of a question the way the service would return it."""
    rec = corpus_by_id.get(qid) or {}
    text = rec.get(lang, "") or ""
    return text if text else rec.get("en", "")


# ── Method 1: production keyword baseline ─────────────────────────────────

def rank_keyword(query: str, corpus: List[Dict[str, str]]) -> List[str]:
    """Mirror followup_service.guideline_questions ordering (no scores)."""
    tree = _keyword_tree(query)
    ids: List[str] = []
    for rec in corpus:
        if rec["tree"] == tree:
            ids.append(rec["id"])
    for rec in corpus:
        if rec["tree"] == "COMMON" and rec["id"] not in ids:
            ids.append(rec["id"])
    # Anything unanswered elsewhere simply never surfaces; order remaining by id
    # so every method returns a full-length ranking for fair @k cutoffs.
    for rec in corpus:
        if rec["id"] not in ids:
            ids.append(rec["id"])
    return ids


# ── Method 2: lexical TF-IDF retrieval ────────────────────────────────────

class LexicalRetriever:
    def __init__(self, corpus: List[Dict[str, str]]):
        from sklearn.feature_extraction.text import TfidfVectorizer
        # Each question contributes two passages (en + hi where present); max
        # similarity across a question's passages becomes the question score.
        self._passages = []
        for rec in corpus:
            if rec["en"]:
                self._passages.append((rec["id"], rec["en"]))
            if rec["hi"]:
                self._passages.append((rec["id"], rec["hi"]))
        texts = [p[1] for p in self._passages]
        self._vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)
        self._matrix = self._vec.fit_transform(texts)
        # Word-level model for space-separated scripts boosts English/Hindi tokens.
        self._vec_w = TfidfVectorizer(analyzer="word", ngram_range=(1, 1), sublinear_tf=True)
        self._matrix_w = self._vec_w.fit_transform(texts)

    def rank(self, query: str) -> List[str]:
        import numpy as np
        qc = self._vec.transform([query])
        cw = (self._matrix @ qc.T).toarray().ravel()
        qw = (self._matrix_w @ self._vec_w.transform([query]).T).toarray().ravel()
        scores = 0.6 * cw + 0.4 * qw
        best: Dict[str, float] = {}
        for (qid, _), s in zip(self._passages, scores):
            if s > best.get(qid, -1):
                best[qid] = s
        return sorted(best, key=lambda q: -best[q])


# ── Method 3: intfloat/multilingual-e5-small semantic retrieval ───────────

class E5Retriever:
    """Documented e5 usage: prepend 'query: ' to queries and 'passage: ' to
    passages; CPU device (this machine's CUDA kernels are known-broken)."""

    MODEL_NAME = "intfloat/multilingual-e5-small"

    def __init__(self, corpus: List[Dict[str, str]]):
        os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
        from sentence_transformers import SentenceTransformer
        t0 = time.perf_counter()
        self.model = SentenceTransformer(self.MODEL_NAME, device="cpu")
        self.load_seconds = time.perf_counter() - t0
        passages = []
        for rec in corpus:
            if rec["en"]:
                passages.append((rec["id"], "passage: " + rec["en"]))
            if rec["hi"]:
                passages.append((rec["id"], "passage: " + rec["hi"]))
        self._ids = [p[0] for p in passages]
        self._emb = self.model.encode([p[1] for p in passages], convert_to_numpy=True,
                                      normalize_embeddings=True)

    def rank(self, query: str) -> List[str]:
        qv = self.model.encode(["query: " + query], convert_to_numpy=True,
                               normalize_embeddings=True)
        sims = (self._emb @ qv.T).ravel()
        best: Dict[str, float] = {}
        for qid, s in zip(self._ids, sims):
            if s > best.get(qid, -2):
                best[qid] = float(s)
        return sorted(best, key=lambda q: -best[q])


# ── Scoring ───────────────────────────────────────────────────────────────

def script_fraction(text: str, lang: str) -> float:
    if not text:
        return 0.0
    if lang == "hi":
        return len(_DEVANAGARI.findall(text)) / max(1, len(text))
    if lang == "gu":
        return len(_GUJARATI.findall(text)) / max(1, len(text))
    # English: correctness = no Indic leakage
    return 0.0 if (_DEVANAGARI.search(text) or _GUJARATI.search(text)) else 1.0


def evaluate(rank_fn, corpus: List[Dict[str, str]], k: int = 3) -> Dict[str, Any]:
    corpus_by_id = {c["id"]: c for c in corpus}
    tree_of = {c["id"]: c["tree"] for c in corpus}
    per_lang: Dict[str, Dict[str, List[float]]] = {}
    lat: List[float] = []

    for case in EVAL_SET:
        t0 = time.perf_counter()
        ranking = rank_fn(case["query"])
        lat.append(time.perf_counter() - t0)
        top_k = ranking[:k]
        gold = set(case["gold_questions"])
        hit = 1.0 if gold & set(top_k) else 0.0
        recall = len(gold & set(top_k)) / max(1, len(gold))
        top1_tree_ok = 1.0 if tree_of.get(ranking[0], "") == case["gold_tree"] else 0.0
        rr = 0.0
        for pos, qid in enumerate(ranking[:5], 1):
            if qid in gold:
                rr = 1.0 / pos
                break
        # Language correctness: does the top-1 question, localized for the
        # query language, actually render in that language's script?
        loc = question_text(corpus_by_id, ranking[0], case["lang"])
        sc = 1.0 if script_fraction(loc, case["lang"]) >= (0.3 if case["lang"] in ("hi", "gu") else 1.0) else 0.0

        d = per_lang.setdefault(case["lang"], {"hit": [], "recall": [], "top1": [], "mrr": [], "script": []})
        d["hit"].append(hit); d["recall"].append(recall); d["top1"].append(top1_tree_ok)
        d["mrr"].append(rr); d["script"].append(sc)

    def agg(vals: List[float]) -> float:
        return round(100.0 * sum(vals) / max(1, len(vals)), 1)

    overall = {lang: {m: agg(v[m]) for m in v} for lang, v in per_lang.items()}
    all_lists = {m: [x for v in per_lang.values() for x in v[m]] for m in ("hit", "recall", "top1", "mrr", "script")}
    return {
        "overall": {m: agg(v) for m, v in all_lists.items()},
        "per_language": overall,
        "latency_ms_mean": round(1000.0 * sum(lat) / max(1, len(lat)), 2),
        "n_queries": len(EVAL_SET),
    }


# ── Memory measurement (dependency-free) ──────────────────────────────────

def rss_mb() -> Optional[float]:
    try:  # POSIX
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        pass
    try:  # Windows: psapi via ctypes (no psutil dependency)
        import ctypes
        import ctypes.wintypes as wt

        class PMC(ctypes.Structure):
            _fields_ = [("Cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
        pmc = PMC()
        pmc.Cb = ctypes.sizeof(pmc)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
        psapi.GetProcessMemoryInfo.restype = wt.BOOL
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(pmc), pmc.Cb):
            return pmc.WorkingSetSize / (1024.0 * 1024.0)
    except Exception:
        pass
    return None


def model_disk_mb(model_name: str = "intfloat/multilingual-e5-small") -> Optional[float]:
    """Size of the local HF cache snapshot (evidence for download/disk needs)."""
    try:
        slug = "models--" + model_name.replace("/", "--")
        snap_root = os.path.join(os.path.expanduser("~"), ".cache", "huggingface", "hub", slug, "snapshots")
        if not os.path.isdir(snap_root):
            return None
        total = 0
        for base, _dirs, files in os.walk(snap_root):
            for fn in files:
                p = os.path.join(base, fn)
                try:
                    total += os.path.getsize(os.path.realpath(p))
                except OSError:
                    pass
        return round(total / (1024.0 * 1024.0), 1)
    except Exception:
        return None


# ── Runner ────────────────────────────────────────────────────────────────

def run(methods: List[str]) -> Dict[str, Any]:
    corpus = build_corpus()
    results: Dict[str, Any] = {"n_corpus": len(corpus), "n_queries": len(EVAL_SET), "methods": {}}

    if "keyword" in methods:
        results["methods"]["keyword"] = evaluate(
            lambda q, _c=corpus: rank_keyword(q, _c), corpus)
    if "lexical" in methods:
        lr = LexicalRetriever(corpus)
        results["methods"]["lexical"] = evaluate(lambda q: lr.rank(q), corpus)
    if "e5" in methods:
        before = rss_mb()
        try:
            er = E5Retriever(corpus)
        except Exception as exc:  # model missing / deps unavailable → record honestly
            results["methods"]["e5"] = {"error": f"{type(exc).__name__}: {exc}"}
            return results
        _ = er.rank("warm up")  # discard one-time first-encode cost; measured latency is warm latency
        after = rss_mb()
        res = evaluate(lambda q: er.rank(q), corpus)
        res["model_load_seconds"] = round(er.load_seconds, 2)
        res["rss_mb_before_model"] = round(before, 1) if before else None
        res["rss_mb_after_model"] = round(after, 1) if after else None
        res["model_delta_mb"] = (round(after - before, 1) if (before and after) else None)
        res["model_disk_mb"] = model_disk_mb()
        results["methods"]["e5"] = res
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--methods", default="keyword,lexical,e5")
    parser.add_argument("--json", dest="json_out", default=None)
    args = parser.parse_args()

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    out = run(methods)
    text = json.dumps(out, ensure_ascii=False, indent=2)
    # Console-safe output (Windows cp1252 cannot print Indic chars).
    try:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    except Exception:
        print(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
