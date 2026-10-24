from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from backend.app.database.session import get_db
from backend.app.models.entities import HistorySession, HistoryResponse, Encounter, RedFlagAlert, Patient
from backend.app.clinical.red_flags import RedFlagEngine
from backend.app.services.llm_service import llm_service

router = APIRouter(prefix="/api/chat", tags=["MediKiosk AI Chatbot"])

class ChatMessageRequest(BaseModel):
    message: str
    role: str = "patient" # "patient", "doctor", "general"
    language: str = "en"  # "en", "hi", "gu"
    session_id: Optional[str] = None
    encounter_id: Optional[str] = None
    patient_id: Optional[str] = None
    chat_history: List[Dict[str, str]] = []

LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "gu": "Gujarati (ગુજરાતી)",
}

@router.post("/message")
async def send_chat_message(req: ChatMessageRequest, db: AsyncSession = Depends(get_db)):
    """
    Multilingual Clinical AI Chatbot endpoint powered by NVIDIA Nemotron 3 Ultra.
    Supports both Patient Kiosk conversational intake and Doctor Clinical Copilot assistance.
    """
    lang_name = LANGUAGE_NAMES.get(req.language, "English")
    active_alerts = []
    intake_saved = False

    # 1. Patient Intake Chat Context
    if req.role == "patient":
        patient_context = ""
        if req.session_id:
            sess_res = await db.execute(select(HistorySession).where(HistorySession.id == req.session_id))
            session = sess_res.scalars().first()
            if session:
                # Save the patient's chat message as an intake response
                chat_resp = HistoryResponse(
                    session_id=session.id,
                    section="CHAT_SYMPTOM",
                    question_text=f"Conversational Intake ({lang_name})",
                    answer_text=req.message,
                    input_method="chat",
                    confidence_score=0.98
                )
                db.add(chat_resp)
                intake_saved = True

                # Evaluate real-time red flags
                flags = RedFlagEngine.evaluate_symptoms([{"section": "CHAT_SYMPTOM", "answer_text": req.message}])
                if flags:
                    enc_res = await db.execute(select(Encounter).where(Encounter.id == session.encounter_id))
                    encounter = enc_res.scalars().first()
                    for f in flags:
                        if f.is_triggered:
                            if f.priority == "EMERGENCY":
                                encounter.priority = "EMERGENCY"
                            elif f.priority == "URGENT" and encounter.priority != "EMERGENCY":
                                encounter.priority = "URGENT"

                            alert = RedFlagAlert(
                                encounter_id=session.encounter_id,
                                patient_id=encounter.patient_id,
                                trigger_rule=f.rule_name or "CHAT_TRIGGER",
                                description=f.description or "",
                                priority=f.priority
                            )
                            db.add(alert)
                            active_alerts.append({
                                "title": f.alert_title,
                                "priority": f.priority,
                                "description": f.description
                            })
                await db.commit()

        system_prompt = (
            f"You are MediKiosk AI, an empathetic, highly skilled clinical intake assistant stationed at a hospital OPD kiosk in India.\n"
            f"The patient is communicating in {lang_name}.\n"
            f"RULES:\n"
            f"1. Always reply in {lang_name} (use clear native script or clear transliteration appropriate for India).\n"
            f"2. Be warm, respectful, reassuring, and clinically structured.\n"
            f"3. Help the patient describe their symptoms systematically using the SOCRATES clinical method (Site, Onset, Character, Radiation, Associated symptoms, Timing/Duration, Exacerbating/Relieving factors, Severity 1-10).\n"
            f"4. Ask ONLY 1 or 2 targeted questions at a time so the patient is not overwhelmed.\n"
            f"5. If you suspect emergency red flags (crushing chest pain, severe breathlessness, fainting, paralysis), instruct them calmly to alert the hospital staff immediately.\n"
            f"6. Keep replies concise (2 to 4 sentences max) for fast kiosk touchscreen reading."
        )

    elif req.role == "doctor":
        system_prompt = (
            "You are MediKiosk Clinical Copilot, an AI assistant for hospital physicians.\n"
            "Provide evidence-based, high-yield differential diagnoses, pharmacotherapy guidance, drug-drug interaction cautions, and clinical summaries.\n"
            "Be succinct, professional, and precise. Cite standard Indian and global clinical practice guidelines where relevant."
        )
    else:
        system_prompt = (
            "You are MediKiosk AI Health Assistant. Provide helpful, accurate, and easy-to-understand health guidance. "
            "Remind users to consult a qualified physician for clinical diagnosis and prescriptions."
        )

    # Format history for LLM
    formatted_messages = []
    for h in req.chat_history[-6:]: # Keep last 6 turns for context
        formatted_messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    formatted_messages.append({"role": "user", "content": req.message})

    reply, engine = await llm_service.chat_completion(
        messages=formatted_messages,
        system_prompt=system_prompt,
        temperature=0.3,
        return_engine=True,
    )

    # QA BUG-006: surface the actual engine that produced the reply so the UI
    # can label AI output with its true provenance instead of always naming a
    # commercial model that may not be the one generating the text.
    return {
        "reply": reply,
        "role": "assistant",
        "language": req.language,
        "session_id": req.session_id,
        "red_flags": active_alerts,
        "intake_saved": intake_saved,
        "engine": engine,
        "model": llm_service.model if engine in ("openrouter",) else None,
    }

@router.get("/prompts")
async def get_suggested_prompts(role: str = "patient", language: str = "en"):
    """
    Returns suggested quick-start prompts tailored by role and language.
    """
    if role == "doctor":
        return [
            {"id": "d1", "text": "Differential diagnosis for acute atypical chest pain in diabetic patient"},
            {"id": "d2", "text": "Check drug interactions: Metformin + Telmisartan + Aspirin"},
            {"id": "d3", "text": "Draft patient discharge lifestyle advice for Stage 2 Hypertension"},
            {"id": "d4", "text": "Summarize key clinical red flags for sudden onset unilateral weakness"}
        ]
    
    # Patient Kiosk prompts
    if language == "hi":
        return [
            {"id": "p1", "text": "मुझे सुबह से सीने में भारीपन और बेचैनी हो रही है"},
            {"id": "p2", "text": "मुझे 3 दिन से तेज बुखार और सूखी खांसी है"},
            {"id": "p3", "text": "नई दवाई शुरू करने के बाद चक्कर और उल्टी जैसा लग रहा है"},
            {"id": "p4", "text": "कल से तेज सिरदर्द है और धुंधला दिखाई दे रहा है"}
        ]
    elif language == "gu":
        return [
            {"id": "p1", "text": "મને સવારથી છાતીમાં ભારેપણું અને દુખાવો થાય છે"},
            {"id": "p2", "text": "મને 3 દિવસથી સખત તાવ અને ઉધરસ છે"},
            {"id": "p3", "text": "નવી દવા લીધા પછી મને ચક્કર આવે છે અને ઉબકા થાય છે"},
            {"id": "p4", "text": "ગઈકાલથી સખત માથાનો દુખાવો છે અને ઝાંખું દેખાય છે"}
        ]
    else:
        return [
            {"id": "p1", "text": "I have been having central chest tightness since this morning"},
            {"id": "p2", "text": "I have high fever and severe dry cough for 3 days"},
            {"id": "p3", "text": "I am feeling dizzy and nauseous after starting new medication"},
            {"id": "p4", "text": "Severe throbbing headache with blurry vision since yesterday"}
        ]
