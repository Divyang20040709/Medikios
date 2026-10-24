from typing import Dict, List, Any, Optional
from backend.app.schemas.pydantic_models import ClinicalQuestion, QuestionOption

SUPPORTED_LANGUAGES = {
    "en": {"name": "English", "native": "English", "greeting": "Welcome to MediKiosk"},
    "hi": {"name": "Hindi", "native": "हिन्दी", "greeting": "मेडीकिओस्क में आपका स्वागत है"},
    "bn": {"name": "Bengali", "native": "বাংলা", "greeting": "মেডিকিয়স্কে আপনাকে স্বাগতম"},
    "ta": {"name": "Tamil", "native": "தமிழ்", "greeting": "மெடிகியோஸ்கிற்கு வரவேற்கிறோம்"},
    "te": {"name": "Telugu", "native": "తెలుగు", "greeting": "మెడికియోస్క్‌కు స్వాగతం"},
    "mr": {"name": "Marathi", "native": "मराठी", "greeting": "मेडीकिओस्कमध्ये आपले स्वागत आहे"},
    "gu": {"name": "Gujarati", "native": "ગુજરાતી", "greeting": "મેડિકિઓસ્કમાં આપનું સ્વાગત છે"},
    "kn": {"name": "Kannada", "native": "ಕನ್ನಡ", "greeting": "ಮೆಡಿಕಿಯೋಸ್ಕ್‌ಗೆ ಸುಸ್ವಾಗತ"},
    "ml": {"name": "Malayalam", "native": "മലയാളം", "greeting": "മെഡിക്കിയോസ്കിലേക്ക് സ്വാഗതം"},
    "pa": {"name": "Punjabi", "native": "ਪੰਜਾਬੀ", "greeting": "ਮੈਡੀਕਿਓਸਕ ਵਿੱਚ ਤੁਹਾਡਾ ਸੁਆਗਤ ਹੈ"},
}

COMPLAINT_CATEGORIES = [
    {
        "id": "CHEST_PAIN",
        "title": "Chest Pain / Discomfort",
        "description": "Chest tightness, pain spreading to arm or jaw, breathlessness",
        "icon": "HeartPulse",
        "priority_check": True
    },
    {
        "id": "DIABETES",
        "title": "Diabetes / Blood Sugar Review",
        "description": "Routine sugar follow-up, high readings, foot numbness, insulin review",
        "icon": "Activity",
        "priority_check": False
    },
    {
        "id": "ASTHMA_RESPIRATORY",
        "title": "Asthma / Breathlessness / Cough",
        "description": "Wheezing, shortness of breath, chronic cough, inhaler review",
        "icon": "Wind",
        "priority_check": True
    },
    {
        "id": "ABDOMINAL_PAIN",
        "title": "Abdominal / Stomach Pain",
        "description": "Stomach ache, burning sensation, acidity, nausea, digestive upset",
        "icon": "Stethoscope",
        "priority_check": False
    },
    {
        "id": "FEVER_INFECTION",
        "title": "Fever / Body Ache",
        "description": "Temperature, chills, weakness, joint pain, cough, infection signs",
        "icon": "Thermometer",
        "priority_check": False
    },
    {
        "id": "GENERAL_OPD",
        "title": "Other / General Consultation",
        "description": "Skin conditions, joint pains, headaches, general health checkup",
        "icon": "UserCheck",
        "priority_check": False
    }
]

# SOCRATES and Adaptive Question Trees
QUESTION_TREES: Dict[str, List[ClinicalQuestion]] = {
    "CHEST_PAIN": [
        ClinicalQuestion(
            id="cp_socrates_site",
            section="SITE",
            category="SOCRATES",
            question_en="Where exactly in your chest do you feel the pain or discomfort?",
            translations={
                "hi": "आपके सीने में दर्द या बेचैनी ठीक किस जगह महसूस हो रही है?",
                "bn": "আপনার বুকের ঠিক কোন জায়গায় ব্যথা বা অস্বস্তি হচ্ছে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="cp_site_center", label="Center of chest (Retrosternal)", value="Center of chest"),
                QuestionOption(id="cp_site_left", label="Left side of chest", value="Left chest"),
                QuestionOption(id="cp_site_right", label="Right side of chest", value="Right chest"),
                QuestionOption(id="cp_site_epigastric", label="Upper middle abdomen / beneath ribs", value="Upper epigastric"),
            ],
            next_question_id="cp_socrates_onset"
        ),
        ClinicalQuestion(
            id="cp_socrates_onset",
            section="ONSET",
            category="SOCRATES",
            question_en="How and when did this chest pain start?",
            translations={
                "hi": "यह सीने का दर्द कब और कैसे शुरू हुआ?",
                "bn": "এই বুকের ব্যথা কখন এবং কীভাবে শুরু হয়েছিল?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="cp_onset_sudden", label="Suddenly within minutes", value="Sudden onset within minutes"),
                QuestionOption(id="cp_onset_gradual", label="Gradually over hours or days", value="Gradual onset"),
                QuestionOption(id="cp_onset_exertion", label="Immediately during walking or exertion", value="Triggered by exertion"),
                QuestionOption(id="cp_onset_intermittent", label="Comes and goes intermittently", value="Intermittent"),
            ],
            next_question_id="cp_socrates_character"
        ),
        ClinicalQuestion(
            id="cp_socrates_character",
            section="CHARACTER",
            category="SOCRATES",
            question_en="What does the pain feel like?",
            translations={
                "hi": "दर्द का प्रकार कैसा है?",
                "bn": "ব্যথার ধরনটা কেমন মনে হচ্ছে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="cp_char_pressure", label="Heavy pressure, squeezing, or crushing", value="Crushing / squeezing pressure"),
                QuestionOption(id="cp_char_sharp", label="Sharp, stabbing like a needle", value="Sharp stabbing pain"),
                QuestionOption(id="cp_char_burning", label="Burning sensation like severe acidity", value="Burning acidity-like sensation"),
                QuestionOption(id="cp_char_ache", label="Dull, continuous ache", value="Dull ache"),
            ],
            next_question_id="cp_socrates_radiation"
        ),
        ClinicalQuestion(
            id="cp_socrates_radiation",
            section="RADIATION",
            category="SOCRATES",
            question_en="Does the pain spread (radiate) to any other part of your body?",
            translations={
                "hi": "क्या दर्द शरीर के किसी अन्य हिस्से में फैल रहा है?",
                "bn": "ব্যথা কি শরীরের অন্য কোনো জায়গায় ছড়িয়ে পড়ছে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="cp_rad_arm", label="Spreads to left arm or shoulder", value="Radiates to left arm / shoulder"),
                QuestionOption(id="cp_rad_jaw", label="Spreads to neck or jaw", value="Radiates to jaw / neck"),
                QuestionOption(id="cp_rad_back", label="Spreads straight to back between shoulder blades", value="Radiates to back"),
                QuestionOption(id="cp_rad_none", label="Does not spread anywhere", value="No radiation"),
            ],
            next_question_id="cp_socrates_associated",
            red_flag_triggers=[
                {"condition": "cp_rad_arm", "alert": "Radiation to left arm requires acute coronary triage."}
            ]
        ),
        ClinicalQuestion(
            id="cp_socrates_associated",
            section="ASSOCIATED_SYMPTOMS",
            category="SOCRATES",
            question_en="Are you experiencing any of these associated symptoms with the pain?",
            translations={
                "hi": "क्या दर्द के साथ इनमें से कोई अन्य लक्षण भी हैं?",
                "bn": "ব্যথার সাথে সাথে কি নিচের কোনো লক্ষণ দেখতে পাচ্ছেন?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="cp_assoc_sweat", label="Excessive cold sweating (Diaphoresis)", value="Cold sweating"),
                QuestionOption(id="cp_assoc_breath", label="Severe shortness of breath", value="Severe shortness of breath"),
                QuestionOption(id="cp_assoc_nausea", label="Nausea or vomiting", value="Nausea / vomiting"),
                QuestionOption(id="cp_assoc_dizzy", label="Dizziness, lightheadedness, or feeling faint", value="Dizziness / near-syncope"),
                QuestionOption(id="cp_assoc_none", label="None of these", value="None"),
            ],
            next_question_id="cp_socrates_exacerbating",
            red_flag_triggers=[
                {"condition": "cp_assoc_sweat", "alert": "Cold sweating combined with chest discomfort indicates high-priority triage."},
                {"condition": "cp_assoc_breath", "alert": "Severe acute dyspnea requires immediate triage."}
            ]
        ),
        ClinicalQuestion(
            id="cp_socrates_exacerbating",
            section="EXACERBATING_RELIEVING",
            category="SOCRATES",
            question_en="What makes the discomfort better or worse?",
            translations={
                "hi": "किस चीज़ से दर्द कम या ज्यादा होता है?",
                "bn": "কী করলে ব্যথা বাড়ে বা কমে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="cp_exac_exertion", label="Worse with walking/stairs, better with complete rest", value="Worse on exertion, relieved by rest"),
                QuestionOption(id="cp_exac_breath", label="Worse when taking deep breaths or coughing", value="Pleuritic (worse with inspiration)"),
                QuestionOption(id="cp_exac_antacid", label="Relieved after taking antacids or water", value="Relieved by antacids"),
                QuestionOption(id="cp_exac_constant", label="Constant pain regardless of movement or rest", value="Constant"),
            ],
            next_question_id="cp_socrates_severity"
        ),
        ClinicalQuestion(
            id="cp_socrates_severity",
            section="SEVERITY",
            category="SOCRATES",
            question_en="On a scale of 1 to 10, how severe is your pain right now?",
            translations={
                "hi": "1 से 10 के पैमाने पर, अभी आपका दर्द कितना गंभीर है?",
                "bn": "১ থেকে ১০ এর মধ্যে, এখন আপনার ব্যথা কতটা তীব্র?",
            },
            input_type="scale",
            options=[
                QuestionOption(id="scale_1_3", label="1 to 3 (Mild discomfort)", value="Mild (1-3)"),
                QuestionOption(id="scale_4_6", label="4 to 6 (Moderate pain, interferes with tasks)", value="Moderate (4-6)"),
                QuestionOption(id="scale_7_8", label="7 to 8 (Severe pain, distressing)", value="Severe (7-8)"),
                QuestionOption(id="scale_9_10", label="9 to 10 (Extremely severe / worst ever)", value="Very severe (9-10)"),
            ],
            next_question_id="common_past_medical"
        )
    ],

    "DIABETES": [
        ClinicalQuestion(
            id="dm_duration",
            section="DIABETES_DURATION",
            category="HISTORY",
            question_en="How long have you been diagnosed with diabetes or high blood sugar?",
            translations={
                "hi": "आपको शुगर (डायबिटीज) की समस्या कितने समय से है?",
                "bn": "আপনার কতদিন ধরে ডায়াবেটিস বা ব্লাড সুগার রয়েছে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="dm_dur_recent", label="Less than 1 year (recently diagnosed)", value="< 1 year"),
                QuestionOption(id="dm_dur_1_5", label="1 to 5 years", value="1-5 years"),
                QuestionOption(id="dm_dur_5_10", label="5 to 10 years", value="5-10 years"),
                QuestionOption(id="dm_dur_10plus", label="More than 10 years", value="> 10 years"),
                QuestionOption(id="dm_dur_suspected", label="Not yet diagnosed / testing for the first time", value="New / suspected"),
            ],
            next_question_id="dm_medications"
        ),
        ClinicalQuestion(
            id="dm_medications",
            section="DIABETES_MEDICATIONS",
            category="MEDICATIONS",
            question_en="What medications or insulin are you currently taking for diabetes?",
            translations={
                "hi": "डायबिटीज के लिए आप वर्तमान में कौन सी दवाएं या इंसुलिन ले रहे हैं?",
                "bn": "ডায়াবেটিসের জন্য বর্তমানে আপনি কী ওষুধ বা ইনসুলিন নিচ্ছেন?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="dm_med_metformin", label="Metformin tablets", value="Metformin"),
                QuestionOption(id="dm_med_sulfo", label="Other sugar tablets (Glimepiride / Gliclazide / Teneligliptin)", value="Oral hypoglycemics"),
                QuestionOption(id="dm_med_insulin", label="Insulin injections (daily or twice daily)", value="Insulin therapy"),
                QuestionOption(id="dm_med_lifestyle", label="Diet and exercise control only", value="Diet/Lifestyle"),
                QuestionOption(id="dm_med_irregular", label="Prescribed medications, but taking irregularly", value="Irregular adherence"),
            ],
            next_question_id="dm_hba1c"
        ),
        ClinicalQuestion(
            id="dm_hba1c",
            section="DIABETES_HBA1C",
            category="OBSERVATIONS",
            question_en="What was your last HbA1c (3-month average sugar) or fasting sugar reading?",
            translations={
                "hi": "आपकी पिछली HbA1c (3 महीने की शुगर) या खाली पेट शुगर की रिपोर्ट क्या थी?",
                "bn": "আপনার শেষ তিন মাসের গড় সুগার (HbA1c) বা খালি পেটের সুগার কেমন ছিল?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="dm_hba1c_good", label="Controlled (HbA1c < 7.0% / Fasting < 130)", value="Well controlled (< 7.0%)"),
                QuestionOption(id="dm_hba1c_moderate", label="Moderately High (HbA1c 7.0% - 8.5%)", value="Moderately elevated (7.0-8.5%)"),
                QuestionOption(id="dm_hba1c_high", label="Very High (HbA1c > 8.5% / Sugar > 250)", value="Uncontrolled (> 8.5%)"),
                QuestionOption(id="dm_hba1c_unknown", label="Have not tested in the last 6 months / Don't remember", value="Untested recently"),
            ],
            next_question_id="dm_complications"
        ),
        ClinicalQuestion(
            id="dm_complications",
            section="DIABETES_COMPLICATIONS",
            category="ROS",
            question_en="Are you experiencing any of these complications or warning signs?",
            translations={
                "hi": "क्या आपको इनमें से कोई परेशानी या लक्षण महसूस हो रहे हैं?",
                "bn": "আপনার কি নিচের কোনো সমস্যা হচ্ছে?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="dm_comp_feet", label="Burning sensation, numbness, or tingling in feet / legs", value="Peripheral neuropathy symptoms"),
                QuestionOption(id="dm_comp_vision", label="Blurring of vision or difficulty reading", value="Visual blurring"),
                QuestionOption(id="dm_comp_wound", label="Non-healing foot ulcer, cut, or wound", value="Non-healing foot wound"),
                QuestionOption(id="dm_comp_hypo", label="Episodes of low sugar (shivering, excessive sweating, confusion)", value="Hypoglycemic episodes"),
                QuestionOption(id="dm_comp_none", label="None of these symptoms", value="No target organ complaints"),
            ],
            next_question_id="common_past_medical",
            red_flag_triggers=[
                {"condition": "dm_comp_wound", "alert": "Diabetic non-healing foot wound requires prompt clinical evaluation to prevent ulceration."},
                {"condition": "dm_comp_hypo", "alert": "Frequent hypoglycemia episodes require dosage review."}
            ]
        )
    ],

    "ASTHMA_RESPIRATORY": [
        ClinicalQuestion(
            id="resp_symptoms",
            section="RESPIRATORY_SYMPTOMS",
            category="COMPLAINT",
            question_en="What is your primary respiratory difficulty?",
            translations={
                "hi": "सांस संबंधी आपकी मुख्य परेशानी क्या है?",
                "bn": "আপনার শ্বাসকষ্ট সংক্রান্ত মূল সমস্যাটি কী?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="resp_wheeze", label="Audible wheezing or whistling sound while breathing", value="Wheezing"),
                QuestionOption(id="resp_dyspnea", label="Shortness of breath on walking or lying flat", value="Shortness of breath"),
                QuestionOption(id="resp_cough", label="Persistent cough with phlegm/sputum", value="Productive cough"),
                QuestionOption(id="resp_tight", label="Tightness across the upper chest", value="Chest tightness"),
            ],
            next_question_id="resp_triggers"
        ),
        ClinicalQuestion(
            id="resp_triggers",
            section="RESPIRATORY_TRIGGERS",
            category="HISTORY",
            question_en="What triggers or worsens your breathing trouble?",
            translations={
                "hi": "किन कारणों से आपकी सांस की तकलीफ बढ़ जाती है?",
                "bn": "কী কারণে আপনার শ্বাসকষ্ট বেড়ে যায়?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="resp_trig_cold", label="Cold weather or early morning air", value="Cold exposure"),
                QuestionOption(id="resp_trig_dust", label="Dust, smoke, incense, or pollution", value="Dust / smoke"),
                QuestionOption(id="resp_trig_exertion", label="Physical climbing stairs or exertion", value="Exertion"),
                QuestionOption(id="resp_trig_night", label="Waking up choking or breathless at night", value="Nocturnal dyspnea"),
            ],
            next_question_id="resp_inhaler_usage"
        ),
        ClinicalQuestion(
            id="resp_inhaler_usage",
            section="INHALER_USAGE",
            category="MEDICATIONS",
            question_en="Do you currently use an inhaler, and how often?",
            translations={
                "hi": "क्या आप इनहेलर का उपयोग करते हैं, और कितनी बार?",
                "bn": "আপনি কি ইনহেলার ব্যবহার করেন, এবং কত ঘন ঘন?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="inh_daily", label="Yes, daily preventer/controller inhaler", value="Daily preventer"),
                QuestionOption(id="inh_frequent", label="Using emergency rescue inhaler multiple times a day", value="Frequent rescue inhaler use"),
                QuestionOption(id="inh_occasional", label="Occasionally only when breathing worsens", value="Occasional PRN use"),
                QuestionOption(id="inh_none", label="Never prescribed or used an inhaler", value="No inhaler use"),
            ],
            next_question_id="common_past_medical",
            red_flag_triggers=[
                {"condition": "inh_frequent", "alert": "High rescue inhaler usage indicates unstable bronchospasm."}
            ]
        )
    ],

    "ABDOMINAL_PAIN": [
        ClinicalQuestion(
            id="abdo_site",
            section="ABDOMINAL_SITE",
            category="SOCRATES",
            question_en="Where is the stomach / abdominal pain located?",
            translations={
                "hi": "पेट का दर्द किस जगह पर हो रहा है?",
                "bn": "পেটের ব্যথা ঠিক কোন অংশে হচ্ছে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="abdo_epigastric", label="Upper middle abdomen (above navel)", value="Epigastric"),
                QuestionOption(id="abdo_ruq", label="Right upper side beneath ribs", value="Right upper quadrant"),
                QuestionOption(id="abdo_rlq", label="Right lower abdomen (near hip bone)", value="Right lower quadrant"),
                QuestionOption(id="abdo_diffuse", label="All over the entire abdomen", value="Generalized diffuse"),
            ],
            next_question_id="abdo_associated"
        ),
        ClinicalQuestion(
            id="abdo_associated",
            section="ABDOMINAL_ASSOCIATED",
            category="ROS",
            question_en="Do you have any of these associated digestive symptoms?",
            translations={
                "hi": "क्या आपको पाचन से संबंधित इनमें से कोई अन्य लक्षण हैं?",
                "bn": "আপনার কি হজম সংক্রান্ত অন্য কোনো লক্ষণ আছে?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="abdo_vomit", label="Repeated vomiting or inability to keep fluids down", value="Persistent vomiting"),
                QuestionOption(id="abdo_blood", label="Black tarry stool or blood in vomit", value="Upper GI bleeding signs"),
                QuestionOption(id="abdo_fever", label="High fever with shivering", value="Fever with abdominal pain"),
                QuestionOption(id="abdo_bowel", label="Severe diarrhea or constipation", value="Altered bowel habit"),
                QuestionOption(id="abdo_none", label="None of these", value="None"),
            ],
            next_question_id="common_past_medical",
            red_flag_triggers=[
                {"condition": "abdo_blood", "alert": "Gastrointestinal bleeding signs require urgent clinical evaluation."},
                {"condition": "abdo_rlq", "alert": "Right lower quadrant pain requires evaluation for acute appendicitis."}
            ]
        )
    ],

    "FEVER_INFECTION": [
        ClinicalQuestion(
            id="fever_duration",
            section="FEVER_DURATION",
            category="COMPLAINT",
            question_en="How many days have you had fever?",
            translations={
                "hi": "आपको कितने दिनों से बुखार है?",
                "bn": "আপনার কতদিন ধরে জ্বর আছে?",
            },
            input_type="single_select",
            options=[
                QuestionOption(id="fev_1_2", label="1 to 2 days", value="1-2 days"),
                QuestionOption(id="fev_3_5", label="3 to 5 days", value="3-5 days"),
                QuestionOption(id="fev_week", label="1 to 2 weeks", value="1-2 weeks"),
                QuestionOption(id="fev_prolonged", label="More than 2 weeks", value="> 2 weeks prolonged"),
            ],
            next_question_id="fever_pattern"
        ),
        ClinicalQuestion(
            id="fever_pattern",
            section="FEVER_PATTERN",
            category="ROS",
            question_en="Are you having any of these symptoms along with fever?",
            translations={
                "hi": "बुखार के साथ क्या आपको इनमें से कोई अन्य परेशानी है?",
                "bn": "জ্বরের সাথে সাথে আপনার কি অন্য কোনো উপসর্গ আছে?",
            },
            input_type="multi_select",
            options=[
                QuestionOption(id="fev_chills", label="Severe shaking chills and shivering (Rigors)", value="Chills and rigors"),
                QuestionOption(id="fev_rash", label="Red spots or skin rash", value="Skin rash"),
                QuestionOption(id="fev_neck", label="Severe headache with stiff neck or sensitivity to light", value="Stiff neck / photophobia"),
                QuestionOption(id="fev_urine", label="Burning or painful urination", value="Dysuria"),
                QuestionOption(id="fev_joint", label="Severe body ache and joint pain", value="Severe arthralgia / myalgia"),
            ],
            next_question_id="common_past_medical",
            red_flag_triggers=[
                {"condition": "fev_neck", "alert": "Fever with neck stiffness requires immediate evaluation for meningitis."}
            ]
        )
    ],

    "GENERAL_OPD": [
        ClinicalQuestion(
            id="gen_chief_complaint",
            section="CHIEF_COMPLAINT",
            category="COMPLAINT",
            question_en="What is the primary reason for your consultation today?",
            translations={
                "hi": "आज डॉक्टर से परामर्श लेने का मुख्य कारण क्या है?",
                "bn": "আজ ডাক্তার দেখানোর মূল কারণ কী?",
            },
            input_type="voice_or_touch",
            options=[
                QuestionOption(id="gen_joint", label="Joint or back pain", value="Musculoskeletal pain"),
                QuestionOption(id="gen_skin", label="Skin allergy, rash, or itch", value="Dermatological condition"),
                QuestionOption(id="gen_headache", label="Headache or dizziness", value="Headache / dizziness"),
                QuestionOption(id="gen_routine", label="Routine general health checkup / medicine refill", value="Routine follow-up"),
            ],
            next_question_id="common_past_medical"
        )
    ]
}

# Common past medical history questions appended to all workflows
COMMON_QUESTIONS: List[ClinicalQuestion] = [
    ClinicalQuestion(
        id="common_past_medical",
        section="PAST_MEDICAL_HISTORY",
        category="PAST_HISTORY",
        question_en="Do you have any existing long-term medical conditions?",
        translations={
            "hi": "क्या आपको पहले से कोई पुरानी बीमारी है?",
            "bn": "আপনার কি আগে থেকেই কোনো পুরনো রোগ আছে?",
        },
        input_type="multi_select",
        options=[
            QuestionOption(id="pmh_htn", label="High Blood Pressure (Hypertension)", value="Hypertension"),
            QuestionOption(id="pmh_dm", label="Diabetes", value="Diabetes Mellitus"),
            QuestionOption(id="pmh_heart", label="Heart disease / Previous stent / Heart attack", value="Coronary Artery Disease"),
            QuestionOption(id="pmh_kidney", label="Kidney disease / High creatinine", value="Chronic Kidney Disease"),
            QuestionOption(id="pmh_thyroid", label="Thyroid disorder", value="Thyroid Disorder"),
            QuestionOption(id="pmh_none", label="No known chronic conditions", value="None"),
        ],
        next_question_id="common_allergies"
    ),
    ClinicalQuestion(
        id="common_allergies",
        section="ALLERGIES",
        category="ALLERGIES",
        question_en="Are you allergic to any medicines or food?",
        translations={
            "hi": "क्या आपको किसी दवा या भोजन से एलर्जी है?",
            "bn": "আপনার কি কোনো ওষুধ বা খাবারে অ্যালার্জি আছে?",
        },
        input_type="multi_select",
        options=[
            QuestionOption(id="alg_penicillin", label="Penicillin / Amoxicillin antibiotics", value="Penicillin allergy"),
            QuestionOption(id="alg_nsaids", label="Painkillers (Aspirin, Ibuprofen, Diclofenac)", value="NSAID allergy"),
            QuestionOption(id="alg_sulfa", label="Sulfa drugs", value="Sulfa allergy"),
            QuestionOption(id="alg_food", label="Food allergy (Eggs, Peanuts, Seafood)", value="Food allergy"),
            QuestionOption(id="alg_none", label="No known drug allergies (NKDA)", value="NKDA"),
        ],
        next_question_id="common_surgeries"
    ),
    ClinicalQuestion(
        id="common_surgeries",
        section="PAST_SURGICAL_HISTORY",
        category="PAST_HISTORY",
        question_en="Have you undergone any major surgery in the past?",
        translations={
            "hi": "क्या आपकी पहले कोई बड़ी सर्जरी या ऑपरेशन हुआ है?",
            "bn": "আপনার কি অতীতে কোনো বড় অপারেশন বা অস্ত্রোপচার হয়েছে?",
        },
        input_type="single_select",
        options=[
            QuestionOption(id="surg_heart", label="Heart bypass (CABG) or Angioplasty / Stent", value="Cardiac surgery / Stent"),
            QuestionOption(id="surg_abdo", label="Abdominal surgery (Appendix, Gallbladder, Hernia)", value="Abdominal surgery"),
            QuestionOption(id="surg_ortho", label="Bone / Joint replacement / Fracture surgery", value="Orthopedic surgery"),
            QuestionOption(id="surg_none", label="No past surgeries", value="No surgical history"),
        ],
        next_question_id=None # End of interview questionnaire
    )
]
