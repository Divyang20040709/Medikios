"""
Phase 5 — Multilingual retrieval EVALUATION tests.

These tests guard the evaluation evidence and the resulting decisions:
  * The synthetic en/hi/gu evaluation set stays valid against the ontology.
  * The keyword baseline (production routing) matches the harness ordering.
  * The pre-registered evidence gate result is codified: on a 22-question
    curated corpus, neither TF-IDF lexical retrieval nor e5 semantic
    retrieval beat the fixed keyword baseline → NO retrieval was integrated.
  * Keyword-data fixes found by the evaluation stay fixed (Hindi oblique
    forms, the wrong-matra Gujarati bug, diabetes numbness keyword).
  * Red-flag escalation is untouched and the guideline fallback still
    serves correctly-localized questions end-to-end.

The e5 model itself is NOT exercised here (8 s load, +1.4 GB RSS) — it is
measured on demand via `python -m backend.evaluation.multilingual_retrieval_eval`.
"""

import json
import os

import pytest

from backend.app.clinical.ontology import QUESTION_TREES, COMMON_QUESTIONS
from backend.app.clinical.red_flags import RedFlagEngine
from backend.app.services.followup_service import (
    _keyword_tree, _TREE_KEYWORDS, guideline_questions, generate_followups,
)
from backend.evaluation.multilingual_retrieval_eval import (
    EVAL_SET, build_corpus, rank_keyword, question_text, LexicalRetriever,
    run as run_eval,
)

RESULTS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "evaluation", "phase5_results.json")


# ── evaluation set integrity ──────────────────────────────────────────────

class TestEvalSetIntegrity:
    def test_gold_ids_exist_in_corpus(self):
        ids = {c["id"] for c in build_corpus()}
        for case in EVAL_SET:
            for qid in case["gold_questions"]:
                assert qid in ids, f"{case['id']} references unknown question {qid}"

    def test_gold_trees_exist(self):
        trees = set(QUESTION_TREES.keys()) | {"COMMON"}
        for case in EVAL_SET:
            assert case["gold_tree"] in trees

    def test_covers_three_languages_and_romanized(self):
        langs = {c["lang"] for c in EVAL_SET}
        assert {"en", "hi", "gu"} <= langs
        scripts = {c["id"][:2] for c in EVAL_SET}
        assert "ro" in scripts  # romanized Hindi (Hinglish) cases present

    def test_queries_are_synthetic_not_patient_data(self):
        # Evaluation set must stay hand-written: no MRNs, phones, or real ids.
        blob = json.dumps(EVAL_SET)
        for forbidden in ("MRN", "abha", "phone", "patient_id"):
            assert forbidden.lower() not in blob.lower()


# ── harness fidelity to production routing ────────────────────────────────

class TestBaselineFidelity:
    @pytest.mark.parametrize("qid", ["hi02", "en02", "gu04", "ro02"])
    def test_harness_matches_guideline_questions_order(self, qid):
        case = next(c for c in EVAL_SET if c["id"] == qid)
        corpus = build_corpus()
        corpus_by_id = {c["id"]: c for c in corpus}
        prod = [g["text"] for g in
                guideline_questions(case["query"], [], case["lang"], 5)]
        harness = [question_text(corpus_by_id, i, case["lang"])
                   for i in rank_keyword(case["query"], corpus)][:5]
        assert prod == harness[:len(prod)]


# ── keyword-data fixes proven by the evaluation (evidence, not guesses) ───

class TestEvalDiscoveredRoutingFixes:
    def test_hindi_oblique_chest_word_routes_to_chest(self):
        # 'सीने' (oblique of 'सीना') was missed by the exact-match list.
        assert _keyword_tree("मुझे सीने में दर्द है") == "CHEST_PAIN"

    def test_hindi_saans_word_routes_to_respiratory(self):
        assert _keyword_tree("रात को सांस लेने में तकलीफ होती है") == "ASTHMA_RESPIRATORY"

    def test_gujarati_madhumeh_matches_after_matra_fix(self):
        # Production list used Devanagari U+0941 inside a Gujarati word, so
        # correctly-spelled Gujarati 'મધુમેહ' never matched. Evaluation exposed it.
        assert "મધુમેહ" in _TREE_KEYWORDS["DIABETES"]
        assert _keyword_tree("મધુમેહની દવા ચાલુ છે") == "DIABETES"

    def test_diabetes_neuropathy_english_keyword(self):
        assert _keyword_tree("Numbness and tingling in both my feet") == "DIABETES"

    def test_no_keyword_regression_for_existing_words(self):
        assert _keyword_tree("bukhar aur khaansi") == "FEVER_INFECTION"
        assert _keyword_tree("stomach pain since morning") == "ABDOMINAL_PAIN"
        assert _keyword_tree(" totally unrelated text ") == "GENERAL_OPD"


# ── the pre-registered evidence gate, codified from the saved run ─────────

@pytest.mark.skipif(not os.path.exists(RESULTS_PATH),
                    reason="run `python -m backend.evaluation.multilingual_retrieval_eval` first")
class TestEvidenceGate:
    def test_gate_artifact_has_all_methods(self):
        data = json.load(open(RESULTS_PATH, encoding="utf-8"))
        assert {"keyword", "lexical", "e5"} <= set(data["methods"])

    def test_lexical_retrieval_did_not_justify_adoption(self):
        data = json.load(open(RESULTS_PATH, encoding="utf-8"))
        assert data["methods"]["lexical"]["overall"]["top1"] < data["methods"]["keyword"]["overall"]["top1"]

    def test_e5_did_not_justify_adoption(self):
        # Gate: >= +10pp top-1 or hit@3 over baseline. Measured: top-1 fell
        # (73.9 vs 100.0) and hit@3 fell (82.6 vs 95.7) after the keyword
        # fixes, while costing +1.4 GB RSS, 470 MB disk and 8 s load.
        data = json.load(open(RESULTS_PATH, encoding="utf-8"))
        kw, e5 = data["methods"]["keyword"], data["methods"]["e5"]
        assert e5["overall"]["top1"] <= kw["overall"]["top1"]
        assert e5["overall"]["hit"] <= kw["overall"]["hit"]

    def test_retrieval_not_integrated_into_service(self):
        # Phase 5 decision guard: followup_service must not import or require
        # any retrieval stack (sentence_transformers / numpy embedding code).
        import backend.app.services.followup_service as fs
        src = open(fs.__file__, encoding="utf-8").read()
        for banned in ("sentence_transformers", "multilingual-e5", "Tfidf"):
            assert banned not in src


# ── graceful degradation of the harness itself ────────────────────────────

class TestHarnessFallbacks:
    def test_lexical_retriever_returns_full_ranking(self):
        corpus = build_corpus()
        ranking = LexicalRetriever(corpus).rank("chest pain since morning")
        assert len(ranking) == len({c["id"] for c in corpus})

    def test_missing_model_records_error_instead_of_crashing(self, monkeypatch):
        import backend.evaluation.multilingual_retrieval_eval as ev

        class BrokenE5:
            def __init__(self, corpus):
                raise RuntimeError("model unavailable")

        monkeypatch.setattr(ev, "E5Retriever", BrokenE5)
        out = run_eval(["e5"])
        assert "error" in out["methods"]["e5"]
        assert "model unavailable" in out["methods"]["e5"]["error"]

    def test_keyword_only_run_needs_no_ml_stack(self):
        out = run_eval(["keyword"])
        assert out["methods"]["keyword"]["n_queries"] == len(EVAL_SET)


# ── untouched guarantees: red flags + guideline fallback end-to-end ───────

class TestPreservedBehaviour:
    def test_red_flag_engine_still_escalates(self):
        flags = RedFlagEngine.evaluate_symptoms([
            {"section": "SITE", "answer_text": "Pain at center of chest"},
            {"section": "RADIATION", "answer_text": "Spreads to left arm"},
        ])
        assert any(f.rule_name == "ACUTE_CHEST_DISCOMFORT_TRIAGE" for f in flags)

    async def test_hindi_followup_fallback_serves_devanagari_questions(self, monkeypatch):
        # No local LLM available → deterministic guideline routing, localized.
        monkeypatch.setattr("backend.app.services.followup_service.LocalLLMClient.chat",
                            lambda self, **kw: _none_coro())
        result = await generate_followups(
            [{"question_text": "सांस में तकलीफ?", "answer_text": "रात को सांस लेने में तकलीफ होती है",
              "section_id": "RESPIRATORY_SYMPTOMS"}],
            language="hi", max_questions=3,
        )
        assert result["source"] == "rule_fallback"
        assert result["questions"]
        # Baseline keyword fix means the respiratory tree now surfaces.
        assert any(q["section"] in ("RESPIRATORY_SYMPTOMS", "RESPIRATORY_TRIGGERS", "INHALER_USAGE")
                   for q in result["questions"])

    async def test_unsupported_language_degrades_to_english(self, monkeypatch):
        monkeypatch.setattr("backend.app.services.followup_service.LocalLLMClient.chat",
                            lambda self, **kw: _none_coro())
        result = await generate_followups(
            [{"question_text": "", "answer_text": "chest pain", "section_id": "SITE"}],
            language="xx", max_questions=2,
        )
        assert result["language"] == "en"
        assert all("?" in q["text"] for q in result["questions"])


async def _none_coro():
    return None
