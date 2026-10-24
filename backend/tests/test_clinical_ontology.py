import pytest
from backend.app.clinical.ontology import QUESTION_TREES, COMPLAINT_CATEGORIES, SUPPORTED_LANGUAGES
from backend.app.clinical.red_flags import RedFlagEngine

def test_supported_languages():
    assert len(SUPPORTED_LANGUAGES) >= 10
    assert "hi" in SUPPORTED_LANGUAGES
    assert "en" in SUPPORTED_LANGUAGES
    assert "bn" in SUPPORTED_LANGUAGES
    assert "ta" in SUPPORTED_LANGUAGES

def test_socrates_chest_pain_tree():
    cp_tree = QUESTION_TREES.get("CHEST_PAIN")
    assert cp_tree is not None
    sections = [q.section for q in cp_tree]
    assert "SITE" in sections
    assert "ONSET" in sections
    assert "CHARACTER" in sections
    assert "RADIATION" in sections
    assert "ASSOCIATED_SYMPTOMS" in sections
    assert "EXACERBATING_RELIEVING" in sections
    assert "SEVERITY" in sections

def test_red_flag_engine_cardiac_trigger():
    # Symptoms representing acute cardiac risk pattern
    responses = [
        {"section": "SITE", "answer_text": "Center of chest (Retrosternal)"},
        {"section": "CHARACTER", "answer_text": "Crushing / squeezing pressure"},
        {"section": "RADIATION", "answer_text": "Radiates to left arm / shoulder"},
        {"section": "ASSOCIATED_SYMPTOMS", "answer_text": "Cold sweating and shortness of breath"},
        {"section": "SEVERITY", "answer_text": "Severe (8/10)"}
    ]
    alerts = RedFlagEngine.evaluate_symptoms(responses)
    assert len(alerts) >= 1
    assert any(a.priority == "EMERGENCY" for a in alerts)
    assert any("Cardiac" in a.alert_title for a in alerts)
    # Validate non-autonomous wording:
    for a in alerts:
        assert "you have a heart attack" not in a.description.lower()
        assert "triage" in a.description.lower() or "assessment" in a.description.lower()

def test_red_flag_engine_routine_symptoms():
    responses = [
        {"section": "SITE", "answer_text": "Right upper side"},
        {"section": "CHARACTER", "answer_text": "Mild ache"},
        {"section": "RADIATION", "answer_text": "No radiation"},
        {"section": "ASSOCIATED_SYMPTOMS", "answer_text": "None"},
        {"section": "SEVERITY", "answer_text": "Mild (2/10)"}
    ]
    alerts = RedFlagEngine.evaluate_symptoms(responses)
    assert len(alerts) == 0
