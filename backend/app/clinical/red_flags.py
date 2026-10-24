import os
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel

from backend.app.clinical.streams import AYUSH, stream_for

try:
    import joblib
except ImportError:
    joblib = None

logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODEL_DIR = os.path.join(PROJECT_ROOT, "model")
TRIAGE_MODEL_PATH = os.path.join(MODEL_DIR, "clinical_triage_classifier.joblib")
LEXICON_PATH = os.path.join(MODEL_DIR, "indic_clinical_lexicon.json")


class RedFlagEvaluation(BaseModel):
    is_triggered: bool
    priority: str = "ROUTINE" # "ROUTINE", "URGENT", "EMERGENCY"
    rule_name: Optional[str] = None
    alert_title: Optional[str] = None
    description: Optional[str] = None
    clinical_rationale: Optional[str] = None
    confidence: float = 1.0
    detected_department: Optional[str] = None


class RedFlagEngine:
    _triage_model = None
    _lexicon = None
    _init_attempted = False

    @classmethod
    def _load_artifacts(cls):
        if not cls._init_attempted:
            cls._init_attempted = True
            if joblib and os.path.exists(TRIAGE_MODEL_PATH):
                try:
                    cls._triage_model = joblib.load(TRIAGE_MODEL_PATH)
                    logger.info("Loaded Clinical Triage ML Classifier artifact.")
                except Exception as e:
                    logger.warning(f"Could not load triage artifact: {e}")
            if os.path.exists(LEXICON_PATH):
                try:
                    with open(LEXICON_PATH, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        cls._lexicon = data.get("lexicon", {})
                    logger.info("Loaded Indic Clinical Lexicon.")
                except Exception as e:
                    logger.warning(f"Could not load Indic lexicon: {e}")

    @classmethod
    def classify_complaint_ml(cls, text: str) -> Dict[str, Any]:
        """
        Evaluates unstructured patient complaints (English, Hindi, or Gujarati)
        using the trained multi-class TF-IDF + Logistic Regression pipeline
        and IndicVoices clinical grounding lexicon.
        """
        cls._load_artifacts()
        if not text or not text.strip():
            return {
                "department": "General Medicine",
                "priority": "ROUTINE",
                "confidence": 0.50,
                "matched_concepts": [],
                "is_red_flag": False,
                "requires_in_person_triage": False,
                "routing_review_required": False,
                "safety_notice": None,
                "engine": "Default Prior"
            }

        cleaned = text.strip()
        matched_concepts = []

        # 1. Lexicon grounding
        if cls._lexicon:
            cleaned_lower = cleaned.lower()
            for c_key, c_data in cls._lexicon.items():
                all_terms = c_data.get("en", []) + c_data.get("hi", []) + c_data.get("gu", [])
                if any(t.lower() in cleaned_lower for t in all_terms):
                    matched_concepts.append({
                        "key": c_key,
                        "concept_id": c_data.get("concept_id"),
                        "suggested_dept": c_data.get("department"),
                        "priority": c_data.get("priority")
                    })

        # 2. ML Pipeline inference
        if cls._triage_model:
            try:
                dept_clf = cls._triage_model["dept_pipeline"]
                prio_clf = cls._triage_model["prio_pipeline"]

                pred_dept = str(dept_clf.predict([cleaned])[0])
                pred_prio = str(prio_clf.predict([cleaned])[0])

                prio_probs = prio_clf.predict_proba([cleaned])[0]
                prio_idx = list(prio_clf.classes_).index(pred_prio)
                confidence = round(float(prio_probs[prio_idx]), 3)
                # True when the red-flag lexicon (not the model) raised the
                # confidence — surfaced in the UI so a rule-driven number is
                # never mistaken for model certainty.
                confidence_adjusted_by_rule = False

                # Prioritize emergency or urgent if detected in clinical lexicon
                if any(mc.get("priority") == "EMERGENCY" for mc in matched_concepts):
                    pred_prio = "EMERGENCY"
                    confidence = max(confidence, 0.95)
                    confidence_adjusted_by_rule = True
                elif any(mc.get("priority") == "URGENT" for mc in matched_concepts):
                    if pred_prio == "ROUTINE":
                        pred_prio = "URGENT"
                        confidence = max(confidence, 0.90)
                        confidence_adjusted_by_rule = True

                is_red_flag = pred_prio in ("EMERGENCY", "URGENT")
                alert = None
                if is_red_flag:
                    alert = {
                        "alert_title": f"Priority Triage: {pred_dept} ({pred_prio})",
                        "description": f"ML Triage detected high-priority symptom pattern: '{cleaned[:60]}...'",
                        "priority": pred_prio,
                        "rationale": "Matches emergency criteria trained on medical dialogue & Synthea triage benchmarks."
                    }

                # ---- Safety presentation (QA-09) -----------------------------
                # Department and priority are produced by two INDEPENDENT
                # models, so they can disagree (e.g. severe chest pain scored
                # EMERGENCY while the department lands on an AYUSH stream).
                # Neither prediction is rewritten here on purpose: changing
                # clinical routing needs a signed-off rule, not a code guess.
                # Instead every high-priority result is explicitly marked as
                # NOT a disposition, and an EMERGENCY + AYUSH combination is
                # flagged for staff review. Assumptions are documented in
                # QA_REPORT.md -> "Open clinical findings (QA-09)".
                requires_in_person_triage = is_red_flag
                routing_review_required = (
                    pred_prio == "EMERGENCY" and stream_for(pred_dept) == AYUSH
                )
                safety_notice = None
                if requires_in_person_triage:
                    article = "An" if pred_prio[0] in "AEIOU" else "A"
                    safety_notice = (
                        "Advisory only — not a clinical disposition. "
                        f"{article} {pred_prio.lower()} priority must be confirmed "
                        "by a clinician in person; this result does not mean the "
                        "patient has been assessed or seen."
                    )
                    if confidence_adjusted_by_rule:
                        safety_notice += (
                            " The confidence figure was raised by a red-flag "
                            "keyword rule, not by the classifier."
                        )
                    if routing_review_required:
                        safety_notice += (
                            " The predicted destination is a traditional "
                            "medicine stream, which is not an emergency "
                            "pathway: verify the destination before directing "
                            "the patient."
                        )

                return {
                    "department": pred_dept,
                    "priority": pred_prio,
                    "confidence": confidence,
                    "confidence_adjusted_by_rule": confidence_adjusted_by_rule,
                    "matched_concepts": matched_concepts,
                    "is_red_flag": is_red_flag,
                    "requires_in_person_triage": requires_in_person_triage,
                    "routing_review_required": routing_review_required,
                    "safety_notice": safety_notice,
                    "alert": alert,
                    "engine": "Trained Scikit-Learn TF-IDF Triage Classifier"
                }
            except Exception as e:
                logger.warning(f"ML triage execution error: {e}")

        # Deterministic fallback
        # QA-09: keep the response shape identical to the ML path so no caller
        # has to guard for missing safety keys, and keep is_red_flag truthful —
        # a fallback that reports EMERGENCY while claiming is_red_flag=False
        # would render an emergency as a routine case.
        fallback_priority = (
            "EMERGENCY" if ("chest" in cleaned.lower() and "sweat" in cleaned.lower()) else "ROUTINE"
        )
        fallback_is_emergency = fallback_priority == "EMERGENCY"
        return {
            "department": "Cardiology / Acute Medicine" if "chest" in cleaned.lower() else "General Medicine",
            "priority": fallback_priority,
            "confidence": 0.85,
            "confidence_adjusted_by_rule": False,
            "matched_concepts": matched_concepts,
            "is_red_flag": fallback_is_emergency,
            "requires_in_person_triage": fallback_is_emergency,
            "routing_review_required": False,
            "safety_notice": (
                "Advisory only — not a clinical disposition. An emergency "
                "priority must be confirmed by a clinician in person."
                if fallback_is_emergency
                else None
            ),
            "engine": "Deterministic Clinical Heuristics"
        }

    @staticmethod
    def evaluate_symptoms(responses: List[Dict[str, Any]]) -> List[RedFlagEvaluation]:
        """
        Evaluates a set of patient responses for predefined high-urgency clinical patterns.
        Strict rule: Generates priority triage flags, NEVER autonomous medical diagnoses.
        """
        alerts: List[RedFlagEvaluation] = []
        response_map = {r.get("section", ""): r.get("answer_text", "") for r in responses}
        
        # Check 1: Acute Coronary / Cardiac Red Flag
        # Central chest pain radiating to left arm/jaw OR associated with cold sweating / breathlessness
        site = response_map.get("SITE", "").lower()
        radiation = response_map.get("RADIATION", "").lower()
        associated = response_map.get("ASSOCIATED_SYMPTOMS", "").lower()
        character = response_map.get("CHARACTER", "").lower()
        
        has_cardiac_radiation = ("left arm" in radiation) or ("jaw" in radiation) or ("neck" in radiation)
        has_sweat_or_breath = ("cold sweat" in associated) or ("shortness of breath" in associated)
        has_crushing_pressure = ("crushing" in character) or ("squeezing" in character) or ("pressure" in character)
        
        if ("center" in site or "retrosternal" in site or "left" in site) and (has_cardiac_radiation or has_sweat_or_breath or has_crushing_pressure):
            alerts.append(RedFlagEvaluation(
                is_triggered=True,
                priority="EMERGENCY",
                rule_name="ACUTE_CHEST_DISCOMFORT_TRIAGE",
                alert_title="Priority Triage Alert: Cardiac Risk Pattern",
                description="Patient reports acute chest pain with radiating pain or autonomic signs (sweating/breathlessness). Immediate clinician assessment and 12-lead ECG recommended.",
                clinical_rationale="Meets clinical criteria for rapid triage evaluation to rule out acute coronary syndrome."
            ))
            
        # Check 2: Respiratory Distress Red Flag
        resp_symptoms = response_map.get("RESPIRATORY_SYMPTOMS", "").lower()
        inhaler_use = response_map.get("INHALER_USAGE", "").lower()
        if "shortness of breath" in resp_symptoms and "frequent rescue" in inhaler_use:
            alerts.append(RedFlagEvaluation(
                is_triggered=True,
                priority="URGENT",
                rule_name="ACUTE_BRONCHOSPASM_ALERT",
                alert_title="Priority Triage Alert: Respiratory Distress",
                description="Frequent rescue inhaler usage with persistent breathlessness indicates unstable bronchospasm. Prioritize for clinical assessment and peak flow / SpO2 evaluation.",
                clinical_rationale="High-frequency short-acting beta-agonist use correlates with acute asthma exacerbation risk."
            ))

        # Check 3: Acute Gastrointestinal Bleeding
        abdo_associated = response_map.get("ABDOMINAL_ASSOCIATED", "").lower()
        if "bleeding" in abdo_associated or "black" in abdo_associated or "blood" in abdo_associated:
            alerts.append(RedFlagEvaluation(
                is_triggered=True,
                priority="EMERGENCY",
                rule_name="GI_BLEED_TRIAGE",
                alert_title="Priority Triage Alert: Suspected Gastrointestinal Bleeding",
                description="Patient reports signs of upper or lower GI bleeding (black tarry stools or blood in emesis). Immediate clinical examination and hemodynamic check required.",
                clinical_rationale="Signs of potential hemorrhage require immediate medical stabilization."
            ))

        # Check 4: Meningeal / Neurological Sepsis Signs
        fever_pattern = response_map.get("FEVER_PATTERN", "").lower()
        if "stiff neck" in fever_pattern or "photophobia" in fever_pattern:
            alerts.append(RedFlagEvaluation(
                is_triggered=True,
                priority="EMERGENCY",
                rule_name="MENINGEAL_SIGNS_ALERT",
                alert_title="Priority Triage Alert: Febrile Meningeal Signs",
                description="Fever accompanied by neck stiffness or severe photophobia requires urgent clinical triage to rule out central nervous system infection.",
                clinical_rationale="Fever with meningismus warrants emergent lumbar puncture/clinical workup."
            ))

        # Check 5: Severe Diabetic Complication (Non-healing foot ulcer)
        dm_complications = response_map.get("DIABETES_COMPLICATIONS", "").lower()
        if "non-healing foot" in dm_complications or "wound" in dm_complications:
            alerts.append(RedFlagEvaluation(
                is_triggered=True,
                priority="URGENT",
                rule_name="DIABETIC_FOOT_RISK",
                alert_title="Priority Clinical Alert: Diabetic Foot Lesion",
                description="Patient with diabetes reports a non-healing foot wound. Requires expedited physical examination to assess ulcer grade and peripheral perfusion.",
                clinical_rationale="Early debridement and offloading prevents amputation."
            ))

        return alerts
