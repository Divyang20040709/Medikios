import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from datetime import datetime, timedelta
from passlib.context import CryptContext
from sqlalchemy.future import select

from backend.app.database.session import async_session_factory, init_db, engine
from backend.app.models.entities import (
    User, Patient, Encounter, ConsentRecord, HistorySession, HistoryResponse,
    MedicalDocument, ExtractedEntity, Medication, Observation, Allergy,
    Surgery, TimelineEvent, ClinicalSummary, RedFlagAlert, AuditLog
)

# Phase 6: seed accounts use the same salted bcrypt hashing as live sign-up
# (auth_router.get_password_hash), never raw unsalted SHA-256.
from backend.app.api.auth_router import get_password_hash as hash_pw
from backend.app.clinical.streams import (
    AYUSH_DOCTOR_DEPARTMENT, MODERN_DOCTOR_DEPARTMENT
)

# One kiosk, two OPD streams: each physician account carries its stream in
# `department`, and the kiosk routes an encounter to the matching physician
# (backend/app/clinical/streams.py + GET /api/doctor/queue).
STAFF_ACCOUNTS = [
    {
        "email": "general@hospital.in",
        "password": "general@hospital.in",
        "full_name": "Dr. Ananya Sengupta, MD",
        "role": "DOCTOR",
        "department": MODERN_DOCTOR_DEPARTMENT,
        "doctor_registration_no": "WB-MC-48291",
        "phone": "9876543210",
        "legacy_email": "doctor@hospital.in",
    },
    {
        "email": "ayush@hospital.in",
        "password": "ayush@hospital.in",
        "full_name": "Dr. Vandana Sharma, BAMS",
        "role": "DOCTOR",
        "department": AYUSH_DOCTOR_DEPARTMENT,
        "doctor_registration_no": "WB-AY-11904",
        "phone": "9876543212",
        "legacy_email": None,
    },
    {
        "email": "admin@hospital.in",
        "password": "admin@hospital.in",
        "full_name": "Apollo Hospital OPD Admin",
        "role": "ADMIN",
        "department": "Hospital Administration",
        "doctor_registration_no": None,
        "phone": "9876543211",
        "legacy_email": None,
    },
]


async def ensure_staff_accounts(db) -> None:
    """Create-or-update the demo staff logins (idempotent, safe to re-run).

    Existing rows are updated in place so linked clinical data (encounters,
    summaries, audit logs) is preserved. The legacy single-physician account
    `doctor@hospital.in` is RENAMED to the General & Modern Medicine account
    rather than duplicated, so the hospital ends up with exactly two OPD
    physicians (General + AYUSH) and one admin.
    """
    for spec in STAFF_ACCOUNTS:
        user = (
            await db.execute(select(User).where(User.email == spec["email"]))
        ).scalars().first()
        if user is None and spec.get("legacy_email"):
            user = (
                await db.execute(select(User).where(User.email == spec["legacy_email"]))
            ).scalars().first()

        if user is None:
            user = User(
                email=spec["email"],
                phone=spec["phone"],
                full_name=spec["full_name"],
                role=spec["role"],
                password_hash=hash_pw(spec["password"]),
                doctor_registration_no=spec["doctor_registration_no"],
                department=spec["department"],
            )
            db.add(user)
            print(f" [seed] created staff account {spec['email']} "
                  f"({spec['role']} - {spec['department']})")
        else:
            user.email = spec["email"]
            user.role = spec["role"]
            user.full_name = spec["full_name"]
            user.department = spec["department"]
            user.password_hash = hash_pw(spec["password"])
            user.doctor_registration_no = spec["doctor_registration_no"]
            if not user.phone:
                user.phone = spec["phone"]
            print(f" [seed] updated staff account {spec['email']} "
                  f"({spec['role']} - {spec['department']})")
        await db.commit()

async def seed_data():
    print("Initializing database tables...")
    await init_db()

    async with async_session_factory() as db:
        # Check if clinical seed data already exists. Keyed on patients (not on
        # a staff e-mail) so renaming/replacing a demo login never re-runs the
        # clinical seed and duplicates demo patients.
        existing_patient = (
            await db.execute(select(Patient.id).limit(1))
        ).scalars().first()
        already_seeded = existing_patient is not None

        # Staff logins are upserted on EVERY run, before the early return, so a
        # password or specialisation change here is applied by re-running this
        # script against the live database.
        await ensure_staff_accounts(db)

        if already_seeded:
            print("Database already contains seed users. Skipping clinical data.")
            return

        print("Seeding demo users and clinical data...")

        # 1. Staff logins were created above by ensure_staff_accounts().

        # 2. Patient 1: Ramesh Kumar (Chest Pain + CAD + Red Flag)
        p1 = Patient(
            name="Ramesh Kumar",
            age=58,
            gender="MALE",
            phone="9830112233",
            abha_id="91-8832-1102-9912",
            aadhaar_last4="4891",
            mrn="MRN-2026-9021",
            blood_group="B+",
            emergency_contact="9830112234 (Son - Rajesh)",
            preferred_language="en"
        )
        db.add(p1)
        await db.commit()
        await db.refresh(p1)

        # Encounter 1 (Emergency Priority due to Red Flag)
        enc1 = Encounter(
            patient_id=p1.id,
            department="Cardiology / Internal Medicine",
            token_number="OPD-101",
            status="INTAKE_COMPLETED",
            priority="EMERGENCY",
            kiosk_id="KIOSK-01"
        )
        db.add(enc1)
        await db.commit()
        await db.refresh(enc1)

        # Consent
        consent1 = ConsentRecord(
            encounter_id=enc1.id,
            patient_id=p1.id,
            purpose="Clinical OPD Intake and AI-Assisted History Taking",
            granted=True,
            audio_consent_granted=True
        )
        db.add(consent1)

        # Red Flag Alert
        rf1 = RedFlagAlert(
            encounter_id=enc1.id,
            patient_id=p1.id,
            trigger_rule="ACUTE_CHEST_DISCOMFORT_TRIAGE",
            description="Patient reports crushing retrosternal chest pain radiating to left arm with cold sweating for 2 days, worse on exertion. Priority triage for rapid ECG and physician review.",
            priority="EMERGENCY"
        )
        db.add(rf1)

        # Clinical Summary Draft
        sum1 = ClinicalSummary(
            encounter_id=enc1.id,
            patient_id=p1.id,
            chief_complaint="Chest pain and heaviness radiating to left arm for 2 days",
            hpi="58-year-old male presents with acute central retrosternal chest pain of 2 days duration. Characterized as crushing pressure (severity 8/10), aggravated by walking and relieved somewhat by rest. Associated with cold sweating and mild dyspnea. Has a known history of CAD s/p PTCA in 2023.",
            past_medical_history=[
                {"condition": "Coronary Artery Disease (CAD)", "duration": "Post-PTCA 2023", "status": "Active"},
                {"condition": "Essential Hypertension", "duration": "8 years", "status": "Active"},
                {"condition": "Type 2 Diabetes Mellitus", "duration": "5 years", "status": "Active"}
            ],
            past_surgical_history=[
                {"procedure": "Percutaneous Coronary Intervention (PTCA) with Drug Eluting Stent in LAD", "year": "2023", "notes": "Done at Apollo Heart Center"}
            ],
            drug_history=[
                {"name": "Tab Metformin", "dosage": "500 mg", "frequency": "1-0-1 (BD)", "source": "Prescription OCR"},
                {"name": "Tab Telmisartan", "dosage": "40 mg", "frequency": "1-0-0 (OD)", "source": "Prescription OCR"},
                {"name": "Tab Atorvastatin", "dosage": "20 mg", "frequency": "0-0-1 (HS)", "source": "Prescription OCR"},
                {"name": "Tab Ecosprin (Aspirin)", "dosage": "75 mg", "frequency": "0-1-0 (After lunch)", "source": "Prescription OCR"}
            ],
            allergies=[
                {"allergen": "Penicillin", "reaction": "Skin rash / urticaria", "severity": "MODERATE"}
            ],
            family_history=[{"relation": "Father", "condition": "Myocardial infarction at age 62"}],
            personal_history=[{"habit": "Tobacco", "details": "Quit smoking 3 years ago; non-alcoholic"}],
            review_of_systems=[
                {"system": "Cardiovascular", "findings": "Chest heaviness radiating to left arm"},
                {"system": "Respiratory", "findings": "Shortness of breath on walking"}
            ],
            investigations=[
                {"test": "Fasting Blood Glucose", "value": "148 mg/dL", "flag": "HIGH"},
                {"test": "HbA1c", "value": "8.2 %", "flag": "HIGH"},
                {"test": "Serum Creatinine", "value": "1.1 mg/dL", "flag": "NORMAL"},
                {"test": "Troponin I", "value": "Pending STAT", "flag": "NORMAL"}
            ],
            red_flags=[
                {"alert": "Priority Triage Alert: Cardiac Risk Pattern", "severity": "EMERGENCY", "rationale": "Crushing chest pain radiating to left arm with diaphoresis."}
            ],
            doctor_notes="AI-assisted clinical draft. Triage elevated to EMERGENCY.",
            is_confirmed_by_doctor=False
        )
        db.add(sum1)

        # Timeline Events for Ramesh Kumar
        t1 = TimelineEvent(
            patient_id=p1.id,
            event_date="Jun 2023",
            event_type="SURGERY",
            title="Coronary Angioplasty (PTCA Stent)",
            description="Drug-eluting stent placed in Left Anterior Descending (LAD) artery.",
            confidence=0.98
        )
        t2 = TimelineEvent(
            patient_id=p1.id,
            event_date="Jan 2026",
            event_type="DISCHARGE_SUMMARY",
            title="Cardiology Review & Discharge Note",
            description="Stable exercise tolerance, advised continuation of Dual Antiplatelet Therapy.",
            confidence=0.96
        )
        t3 = TimelineEvent(
            patient_id=p1.id,
            event_date="Jun 2026",
            event_type="PRESCRIPTION",
            title="OPD Prescription Refill",
            description="Metformin 500mg BD, Telmisartan 40mg OD, Atorvastatin 20mg HS.",
            confidence=0.95
        )
        t4 = TimelineEvent(
            patient_id=p1.id,
            event_date="Aug 2026",
            event_type="LAB_REPORT",
            title="Biochemistry Panel (HbA1c & Lipids)",
            description="HbA1c 8.2%, Fasting Glucose 148 mg/dL, Total Cholesterol 210 mg/dL.",
            confidence=0.99
        )
        db.add_all([t1, t2, t3, t4])

        # Medications
        m1 = Medication(patient_id=p1.id, name="Metformin", dosage="500 mg", frequency="1-0-1", provenance="Prescription OCR")
        m2 = Medication(patient_id=p1.id, name="Telmisartan", dosage="40 mg", frequency="1-0-0", provenance="Prescription OCR")
        m3 = Medication(patient_id=p1.id, name="Atorvastatin", dosage="20 mg", frequency="0-0-1", provenance="Prescription OCR")
        m4 = Medication(patient_id=p1.id, name="Aspirin (Ecosprin)", dosage="75 mg", frequency="0-1-0", provenance="Prescription OCR")
        db.add_all([m1, m2, m3, m4])

        # Observations
        o1 = Observation(patient_id=p1.id, test_name="HbA1c", test_value="8.2", unit="%", reference_range="4.0 - 5.6%", flag="HIGH")
        o2 = Observation(patient_id=p1.id, test_name="Fasting Glucose", test_value="148", unit="mg/dL", reference_range="70 - 100", flag="HIGH")
        o3 = Observation(patient_id=p1.id, test_name="Serum Creatinine", test_value="1.1", unit="mg/dL", reference_range="0.7 - 1.2", flag="NORMAL")
        db.add_all([o1, o2, o3])

        # Allergy & Surgery
        alg1 = Allergy(patient_id=p1.id, allergen="Penicillin", reaction="Skin urticaria", severity="MODERATE")
        surg1 = Surgery(patient_id=p1.id, procedure_name="Coronary Angioplasty (PTCA LAD Stent)", approximate_year="2023", notes="Apollo Hospital")
        db.add_all([alg1, surg1])

        # 3. Patient 2: Sunita Devi (Diabetes Follow-up + Diabetic Foot Risk)
        p2 = Patient(
            name="Sunita Devi",
            age=52,
            gender="FEMALE",
            phone="9830554433",
            abha_id="91-4412-8871-3329",
            aadhaar_last4="7721",
            mrn="MRN-2026-9022",
            blood_group="O+",
            preferred_language="hi"
        )
        db.add(p2)
        await db.commit()
        await db.refresh(p2)

        enc2 = Encounter(
            patient_id=p2.id,
            department="Endocrinology & Diabetology",
            token_number="OPD-102",
            status="INTAKE_COMPLETED",
            priority="URGENT",
            kiosk_id="KIOSK-01"
        )
        db.add(enc2)
        await db.commit()
        await db.refresh(enc2)

        rf2 = RedFlagAlert(
            encounter_id=enc2.id,
            patient_id=p2.id,
            trigger_rule="DIABETIC_FOOT_RISK",
            description="Patient with 8-year diabetes history reports tingling in feet and a non-healing sore under the right great toe. Requires priority clinical assessment.",
            priority="URGENT"
        )
        db.add(rf2)

        sum2 = ClinicalSummary(
            encounter_id=enc2.id,
            patient_id=p2.id,
            chief_complaint="Uncontrolled sugar checkup and numbness with sore under right toe",
            hpi="52-year-old female with long-standing Type 2 Diabetes presents for routine review. Reports worsening burning numbness in both feet and noted a non-healing painless ulcer under right toe for 3 weeks.",
            past_medical_history=[{"condition": "Type 2 Diabetes Mellitus", "duration": "8 years", "status": "Suboptimally controlled"}],
            drug_history=[
                {"name": "Glimepiride", "dosage": "2 mg", "frequency": "1-0-0", "source": "Prescription OCR"},
                {"name": "Metformin", "dosage": "1000 mg", "frequency": "1-0-1", "source": "Prescription OCR"}
            ],
            allergies=[{"allergen": "Sulfa drugs", "reaction": "Skin rash", "severity": "MILD"}],
            investigations=[{"test": "Fasting Glucose", "value": "194 mg/dL", "flag": "HIGH"}, {"test": "HbA1c", "value": "9.1 %", "flag": "HIGH"}],
            red_flags=[{"alert": "Priority Clinical Alert: Diabetic Foot Lesion", "severity": "URGENT", "rationale": "Non-healing wound in diabetic patient."}],
            is_confirmed_by_doctor=False
        )
        db.add(sum2)

        # 4. Patient 3: Arjun Singh (Asthma / Wheezing)
        p3 = Patient(
            name="Arjun Singh",
            age=24,
            gender="MALE",
            phone="9830887766",
            abha_id="91-7721-6654-1108",
            aadhaar_last4="9012",
            mrn="MRN-2026-9023",
            blood_group="A+",
            preferred_language="en"
        )
        db.add(p3)
        await db.commit()
        await db.refresh(p3)

        enc3 = Encounter(
            patient_id=p3.id,
            department="Pulmonology / Chest Clinic",
            token_number="OPD-103",
            status="QUEUED",
            priority="ROUTINE",
            kiosk_id="KIOSK-02"
        )
        db.add(enc3)
        await db.commit()
        await db.refresh(enc3)

        sum3 = ClinicalSummary(
            encounter_id=enc3.id,
            patient_id=p3.id,
            chief_complaint="Persistent dry cough and nighttime wheezing for 5 days",
            hpi="24-year-old college student with childhood asthma presents with exacerbation triggered by cold weather and dust. Using Salbutamol inhaler twice daily.",
            past_medical_history=[{"condition": "Bronchial Asthma", "duration": "Since childhood", "status": "Intermittent"}],
            drug_history=[{"name": "Salbutamol Inhaler 100mcg", "dosage": "2 puffs", "frequency": "PRN / SOS", "source": "Patient Reported"}],
            allergies=[{"allergen": "Dust mites / Pollen", "reaction": "Rhinitis & Wheezing", "severity": "MODERATE"}],
            investigations=[],
            red_flags=[],
            is_confirmed_by_doctor=False
        )
        db.add(sum3)

        await db.commit()
        print("Database successfully seeded with synthetic patients, encounters, summaries, and Doctor Memory Graph relations!")
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(seed_data())
