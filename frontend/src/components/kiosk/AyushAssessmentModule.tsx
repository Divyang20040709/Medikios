'use client';

import React, { useState } from 'react';
import { Flower2, CheckCircle2, ArrowRight, ArrowLeft } from 'lucide-react';
import { Patient, AyushAssessment } from '@/lib/types';
import { clinicalStore } from '@/lib/clinicalStore';

interface AyushAssessmentModuleProps {
  patient: Patient;
  initialAssessment?: AyushAssessment;
  onSave: (assessment: AyushAssessment) => void;
  onBack: () => void;
}

export function AyushAssessmentModule({
  patient,
  initialAssessment,
  onSave,
  onBack,
}: AyushAssessmentModuleProps) {
  const [prakriti, setPrakriti] = useState(initialAssessment?.prakriti || 'Vata-Kapha');
  const [vikriti, setVikriti] = useState(initialAssessment?.vikriti || 'Vata-Kapha with Sama Lakshana (Ama involvement)');
  const [sara, setSara] = useState(initialAssessment?.sara || 'Madhyama');
  const [samhanana, setSamhanana] = useState(initialAssessment?.samhanana || 'Madhyama (Moderate)');
  const [pramana, setPramana] = useState(initialAssessment?.pramana || 'Madhyama (Proportionate)');
  const [satmya, setSatmya] = useState(initialAssessment?.satmya || 'Vyayamadi Satmya');
  const [sattva, setSattva] = useState(initialAssessment?.sattva || 'Madhyama (Moderate)');
  const [aharaShakti, setAharaShakti] = useState(initialAssessment?.aharaShakti || 'Manda (Low Intake & Digestion)');
  const [vyayamaShakti, setVyayamaShakti] = useState(initialAssessment?.vyayamaShakti || 'Heena (Low)');
  const [vaya, setVaya] = useState(initialAssessment?.vaya || 'Madhyama (Adult)');
  const [agni, setAgni] = useState(initialAssessment?.agni || 'Mandagni');
  const [koshtha, setKoshtha] = useState(initialAssessment?.koshtha || 'Krura');
  const [ahara, setAhara] = useState(initialAssessment?.ahara || 'Guru, Snigdha, Sheeta, Dadhi, Viruddha Ahara');
  const [vihara, setVihara] = useState(initialAssessment?.vihara || 'Diwaswapna (daytime sleep), lack of physical activity');
  const [nidana, setNidana] = useState(initialAssessment?.nidana || 'Viruddha Ahara sevana, Sheeta vatasevana, Mandagni');

  const handleSave = () => {
    const assessment: AyushAssessment = {
      id: initialAssessment?.id || `ayush-${Date.now()}`,
      patientId: patient.id,
      prakriti,
      vikriti,
      sara,
      samhanana,
      pramana,
      satmya,
      sattva,
      aharaShakti,
      vyayamaShakti,
      vaya,
      agni,
      koshtha,
      ahara,
      vihara,
      nidana,
      sampraptiSummary: `Ama produced due to ${agni} gets propelled by aggravated Vata causing lakshanas.`,
    };

    const existingCase = clinicalStore.getCaseByPatientId(patient.id);
    if (existingCase) {
      existingCase.ayushAssessment = assessment;
      clinicalStore.saveCase(existingCase);
    }
    onSave(assessment);
  };

  return (
    <div className="max-w-4xl mx-auto w-full px-4 sm:px-6 py-8 sm:py-12 flex flex-col space-y-8 animate-in fade-in duration-150">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center justify-between text-xs font-semibold text-[#666666]">
          <span className="text-emerald-700 uppercase tracking-wider font-bold flex items-center gap-1.5">
            <Flower2 className="w-4 h-4 text-emerald-600" />
            Ayurvedic Dashavidha Pariksha Intake Assessment
          </span>
          <span className="font-mono bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded border border-emerald-200">
            Kayachikitsa OPD
          </span>
        </div>
        <h2 className="text-2xl sm:text-3xl font-serif font-bold text-[#171717]">
          Dashavidha Pariksha Questionnaire
        </h2>
        <p className="text-xs sm:text-sm text-[#666666]">
          Evaluating Deha Prakriti, Agni Bala, and Hetu/Samprapti factors for Ayurvedic diagnosis.
        </p>
      </div>

      {/* Form Grid */}
      <div className="p-5 sm:p-6 rounded-2xl border border-neutral-200 bg-white space-y-5 shadow-xs">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
          {/* Prakriti */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Deha Prakriti (Constitutional Type)</label>
            <select
              value={prakriti}
              onChange={(e) => setPrakriti(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            >
              <option value="Vata-Pitta">Vata-Pitta</option>
              <option value="Vata-Kapha">Vata-Kapha</option>
              <option value="Pitta-Kapha">Pitta-Kapha</option>
              <option value="Tridoshaja">Tridoshaja (Sannipataja)</option>
            </select>
          </div>

          {/* Vikriti */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Vikriti (Dosha Imbalance)</label>
            <input
              type="text"
              value={vikriti}
              onChange={(e) => setVikriti(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Agni */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Agni (Digestive Fire)</label>
            <select
              value={agni}
              onChange={(e) => setAgni(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            >
              <option value="Samagni">Samagni (Balanced)</option>
              <option value="Mandagni">Mandagni (Sluggish / Low)</option>
              <option value="Tikshnagni">Tikshnagni (Hyperactive)</option>
              <option value="Vishamagni">Vishamagni (Irregular)</option>
            </select>
          </div>

          {/* Koshtha */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Koshtha (Bowel Habit)</label>
            <select
              value={koshtha}
              onChange={(e) => setKoshtha(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            >
              <option value="Mrudu">Mrudu (Soft / Easy)</option>
              <option value="Madhyama">Madhyama (Normal)</option>
              <option value="Krura">Krura (Constipated / Hard)</option>
            </select>
          </div>

          {/* Ahara Shakti */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Ahara Shakti (Appetite & Intake)</label>
            <input
              type="text"
              value={aharaShakti}
              onChange={(e) => setAharaShakti(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          {/* Vyayama Shakti */}
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Vyayama Shakti (Physical Stamina)</label>
            <select
              value={vyayamaShakti}
              onChange={(e) => setVyayamaShakti(e.target.value)}
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            >
              <option value="Uttama">Uttama (High)</option>
              <option value="Madhyama">Madhyama (Moderate)</option>
              <option value="Heena">Heena (Low / Poor)</option>
            </select>
          </div>
        </div>

        {/* Dietary Triggers & Lifestyle */}
        <div className="space-y-3 pt-3 border-t border-neutral-100 text-xs">
          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Ahara (Dietary Triggers)</label>
            <input
              type="text"
              value={ahara}
              onChange={(e) => setAhara(e.target.value)}
              placeholder="e.g. Guru, Snigdha, Sheeta, Dadhi, Viruddha Ahara"
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>

          <div className="space-y-1">
            <label className="font-bold text-[#171717]">Vihara (Lifestyle & Daily Routine)</label>
            <input
              type="text"
              value={vihara}
              onChange={(e) => setVihara(e.target.value)}
              placeholder="e.g. Diwaswapna (daytime sleep), lack of physical activity"
              className="w-full px-3 py-2 bg-neutral-50 border border-neutral-200 rounded-lg text-xs"
            />
          </div>
        </div>
      </div>

      <div className="p-4 bg-emerald-50 rounded-xl border border-emerald-200 text-xs text-emerald-800 flex items-center gap-2">
        <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
        <span>Ayurvedic clinical details will be appended directly into the doctor&apos;s consultation view.</span>
      </div>

      {/* Buttons */}
      <div className="pt-4 border-t border-neutral-200 flex items-center justify-between">
        <button
          type="button"
          onClick={onBack}
          className="flex items-center gap-2 px-5 py-2.5 text-xs sm:text-sm font-semibold text-[#666666] hover:text-[#171717] hover:bg-neutral-100 rounded-lg transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Symptoms</span>
        </button>

        <button
          type="button"
          onClick={handleSave}
          className="flex items-center gap-2 px-7 py-3 bg-[#6C3FC5] hover:bg-[#4B238C] text-white text-xs sm:text-sm font-bold rounded-xl shadow-sm hover:shadow-md transition-all active:scale-[0.99]"
        >
          <span>Save AYUSH Assessment</span>
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
