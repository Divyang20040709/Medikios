# -*- coding: utf-8 -*-
import os
import re

ROOT = r"c:\Users\Solanki Divyang\OneDrive\Desktop\Medikiosk-main"

# 1. Update types.ts
types_path = os.path.join(ROOT, "frontend", "src", "lib", "types.ts")
with open(types_path, "r", encoding="utf-8") as f:
    c = f.read()
c = re.sub(r"export type LanguageCode = [^;]+;", "export type LanguageCode = 'en' | 'hi' | 'gu';", c)
with open(types_path, "w", encoding="utf-8") as f:
    f.write(c)
print("1. Updated types.ts")

# 2. Update Step1Language.tsx
step1_path = os.path.join(ROOT, "frontend", "src", "components", "kiosk", "Step1Language.tsx")
step1_content = """'use client';

import React from 'react';
import { Globe, ArrowRight, ArrowLeft, Clock } from 'lucide-react';
import { LanguageCode } from '@/lib/types';

interface Step1LanguageProps {
  currentLanguage: LanguageCode;
  onSelectLanguage: (lang: LanguageCode) => void;
  onContinue: () => void;
  onBack: () => void;
}

export function Step1Language({
  currentLanguage,
  onSelectLanguage,
  onContinue,
  onBack,
}: Step1LanguageProps) {
  const languages: Array<{
    code: LanguageCode;
    native: string;
    label: string;
    greeting: string;
    subtext: string;
  }> = [
    {
      code: 'en',
      native: 'English',
      label: 'English',
      greeting: 'Welcome to MediKiosk',
      subtext: 'Medical terms in simple conversational English',
    },
    {
      code: 'hi',
      native: 'हिन्दी',
      label: 'Hindi',
      greeting: 'मेडीकिओस्क में आपका स्वागत है',
      subtext: 'सरल हिन्दी में अपनी स्वास्थ्य समस्याओं की जानकारी दें',
    },
    {
      code: 'gu',
      native: 'ગુજરાતી',
      label: 'Gujarati',
      greeting: 'મેડીકિયોસ્કમાં તમારું સ્વાગત છે',
      subtext: 'સરળ ગુજરાતીમાં તમારા લક્ષણો અને આરોગ્ય વિગતો જણાવો',
    },
  ];

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Step Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-[#6C3FC5] uppercase tracking-wider font-bold">Step 1 of 5: Language Selection</span>
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            Estimated total time: 8–12 minutes
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          Choose your preferred language
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          You can change your language anytime using the header menu.
        </p>
      </div>

      {/* Language Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {languages.map((item) => {
          const isSelected = currentLanguage === item.code;
          return (
            <div
              key={item.code}
              onClick={() => onSelectLanguage(item.code)}
              className={`cursor-pointer p-5 rounded-xl border-2 transition-all flex flex-col justify-between space-y-4 ${
                isSelected
                  ? 'border-[#6C3FC5] bg-[#F3EEFC]/50 shadow-sm'
                  : 'border-neutral-200 hover:border-[#6C3FC5]/40 hover:bg-[#F3EEFC]/20 bg-white'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-xl sm:text-2xl font-bold text-[#171717]">
                    {item.native}
                  </h3>
                  <span className="text-xs text-[#666666] font-medium">{item.label}</span>
                </div>
                <div
                  className={`w-6 h-6 rounded-full border-2 flex items-center justify-center ${
                    isSelected ? 'border-[#6C3FC5] bg-[#6C3FC5]' : 'border-neutral-300'
                  }`}
                >
                  {isSelected && <span className="w-2 h-2 rounded-full bg-white" />}
                </div>
              </div>

              <div>
                <p className="text-xs font-medium text-[#171717]">{item.greeting}</p>
                <p className="text-xs text-[#666666] mt-0.5">{item.subtext}</p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Navigation Buttons */}
      <div className="pt-6 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Home</span>
        </button>

        <button
          type="button"
          onClick={onContinue}
          className="flex items-center gap-2 px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>Continue to Patient ID</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
"""
with open(step1_path, "w", encoding="utf-8") as f:
    f.write(step1_content)
print("2. Updated Step1Language.tsx")

# 3. Update KioskHeader.tsx
kiosk_header_path = os.path.join(ROOT, "frontend", "src", "components", "kiosk", "KioskHeader.tsx")
with open(kiosk_header_path, "r", encoding="utf-8") as f:
    kh = f.read()

old_langs_pattern = r"const languages: Array<\{ code: LanguageCode; label: string; native: string \}> = \[[\s\S]*?\];"
new_langs = """const languages: Array<{ code: LanguageCode; label: string; native: string }> = [
    { code: 'en', label: 'English', native: 'English' },
    { code: 'hi', label: 'Hindi', native: 'हिन्दी' },
    { code: 'gu', label: 'Gujarati', native: 'ગુજરાતી' },
  ];"""
kh = re.sub(old_langs_pattern, new_langs, kh)
with open(kiosk_header_path, "w", encoding="utf-8") as f:
    f.write(kh)
print("3. Updated KioskHeader.tsx")

# 4. Update clinicalStore.ts
clinical_path = os.path.join(ROOT, "frontend", "src", "lib", "clinicalStore.ts")
with open(clinical_path, "r", encoding="utf-8") as f:
    cs = f.read()

old_switch_pattern = r"switch \(lang\) \{[\s\S]*?default:[\s\S]*?break;\s*\}"
new_switch = """switch (lang) {
          case 'hi':
            utterance.lang = 'hi-IN';
            break;
          case 'gu':
            utterance.lang = 'gu-IN';
            break;
          default:
            utterance.lang = 'en-IN';
            break;
        }"""
cs = re.sub(old_switch_pattern, new_switch, cs)

old_recog_lang = r"recognition\.lang = lang === 'hi' \? 'hi-IN' : lang === 'bn' \? 'bn-IN' : lang === 'ne' \? 'ne-NP' : 'en-IN';"
new_recog_lang = "recognition.lang = lang === 'hi' ? 'hi-IN' : lang === 'gu' ? 'gu-IN' : 'en-IN';"
cs = re.sub(old_recog_lang, new_recog_lang, cs)

with open(clinical_path, "w", encoding="utf-8") as f:
    f.write(cs)
print("4. Updated clinicalStore.ts")

# 5. Update app/chat/page.tsx
chat_page_path = os.path.join(ROOT, "frontend", "src", "app", "chat", "page.tsx")
with open(chat_page_path, "r", encoding="utf-8") as f:
    cp = f.read()

cp = re.sub(
    r"preferred language \(English, [^)]*\)",
    "preferred language (English, हिन्दी, ગુજરાતી)",
    cp
)

cp = cp.replace(
    "language === 'hi' ? 'hi-IN' : (language === 'bn' ? 'bn-IN' : 'en-US')",
    "language === 'hi' ? 'hi-IN' : (language === 'gu' ? 'gu-IN' : 'en-US')"
)

old_select = r"<select[\s\S]*?aria-label=\"Select Language\"[\s\S]*?>[\s\S]*?</select>"
new_select = """<select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              aria-label="Select Language"
              className="bg-[#0b1322] border border-white/10 text-white/80 rounded-xl px-3 py-1 text-xs focus:outline-none focus:border-cyan-400"
            >
              <option value="en">English</option>
              <option value="hi">हिन्दी (Hindi)</option>
              <option value="gu">ગુજરાતી (Gujarati)</option>
            </select>"""
cp = re.sub(old_select, new_select, cp)

old_placeholder = r"placeholder=\{[\s\S]*?language === 'hi'[\s\S]*?: 'Describe your symptoms in your own words\.\.\.'\s*\}"
new_placeholder = """placeholder={
              language === 'hi'
                ? 'अपने लक्षण अपनी भाषा में बताएं (उदा. मुझे 3 दिन से तेज बुखार है)...'
                : language === 'gu'
                ? 'તમારા લક્ષણો તમારી ભાષામાં જણાવો (દા.ત. મને 3 દિવસથી તાવ છે)...'
                : role === 'doctor'
                ? 'Ask clinical questions, drug interactions, or guidelines...'
                : 'Describe your symptoms in your own words...'
            }"""
cp = re.sub(old_placeholder, new_placeholder, cp)

with open(chat_page_path, "w", encoding="utf-8") as f:
    f.write(cp)
print("5. Updated chat/page.tsx")

# 6. Update AIChatbotDrawer.tsx
drawer_path = os.path.join(ROOT, "frontend", "src", "components", "common", "AIChatbotDrawer.tsx")
with open(drawer_path, "r", encoding="utf-8") as f:
    cd = f.read()

cd = cd.replace(
    "language === 'hi' ? 'hi-IN' : (language === 'bn' ? 'bn-IN' : 'en-US')",
    "language === 'hi' ? 'hi-IN' : (language === 'gu' ? 'gu-IN' : 'en-US')"
)

old_drawer_select = r"<select[\s\S]*?aria-label=\"Select Chat Language\"[\s\S]*?>[\s\S]*?</select>"
new_drawer_select = """<select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              aria-label="Select Chat Language"
              className="bg-[#0b1322] border border-white/10 text-white/80 rounded-xl px-2.5 py-1 text-[11px] focus:outline-none focus:border-cyan-400"
            >
              <option value="en">English</option>
              <option value="hi">हिन्दी (Hindi)</option>
              <option value="gu">ગુજરાતી (Gujarati)</option>
            </select>"""
cd = re.sub(old_drawer_select, new_drawer_select, cd)

old_drawer_placeholder = r"placeholder=\{[\s\S]*?language === 'hi'[\s\S]*?: 'Describe symptoms or ask clinical questions\.\.\.'\s*\}"
new_drawer_placeholder = """placeholder={
                language === 'hi'
                  ? 'लक्षण बताएं या प्रश्न पूछें...'
                  : language === 'gu'
                  ? 'લક્ષણો જણાવો અથવા પ્રશ્ન પૂછો...'
                  : 'Describe symptoms or ask clinical questions...'
              }"""
cd = re.sub(old_drawer_placeholder, new_drawer_placeholder, cd)

with open(drawer_path, "w", encoding="utf-8") as f:
    f.write(cd)
print("6. Updated AIChatbotDrawer.tsx")

# 7. Update chat_router.py
router_path = os.path.join(ROOT, "backend", "app", "api", "chat_router.py")
with open(router_path, "r", encoding="utf-8") as f:
    cr = f.read()

cr = re.sub(r'language: str = "en" #[^\n]*', 'language: str = "en"  # "en", "hi", "gu"', cr)

old_lang_names = r'LANGUAGE_NAMES = \{[\s\S]*?\}'
new_lang_names = """LANGUAGE_NAMES = {
    "en": "English",
    "hi": "Hindi (हिन्दी)",
    "gu": "Gujarati (ગુજરાતી)",
}"""
cr = re.sub(old_lang_names, new_lang_names, cr)

old_prompts = r'# Patient Kiosk prompts[\s\S]*?else:\s*return \[[\s\S]*?\]'
new_prompts = """# Patient Kiosk prompts
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
        ]"""
cr = re.sub(old_prompts, new_prompts, cr)

with open(router_path, "w", encoding="utf-8") as f:
    f.write(cr)
print("7. Updated chat_router.py")

# 8. Update test_chat_router.py
test_path = os.path.join(ROOT, "backend", "tests", "test_chat_router.py")
with open(test_path, "r", encoding="utf-8") as f:
    tc = f.read()

if 'language="gu"' not in tc:
    tc = tc.replace(
        'hindi_prompts = await get_suggested_prompts(role="patient", language="hi")\n    assert len(hindi_prompts) >= 3',
        'hindi_prompts = await get_suggested_prompts(role="patient", language="hi")\n    assert len(hindi_prompts) >= 3\n\n    gujarati_prompts = await get_suggested_prompts(role="patient", language="gu")\n    assert len(gujarati_prompts) >= 3'
    )
    with open(test_path, "w", encoding="utf-8") as f:
        f.write(tc)
    print("8. Updated test_chat_router.py")

print("ALL LANGUAGE UPDATES APPLIED SUCCESSFULLY!")
