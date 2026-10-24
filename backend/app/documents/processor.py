import os
import io
import sys
import re
import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple, Optional
from pydantic import BaseModel
from PIL import Image

try:
    import pypdf
except ImportError:
    pypdf = None

logger = logging.getLogger(__name__)

# Ensure local model directory is discoverable in Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
MODEL_DIR = os.path.join(PROJECT_ROOT, "model")
PADDLEOCR_DIR = os.path.join(MODEL_DIR, "paddleocr")

if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

class PaddleOCRProcessor:
    """
    PaddleOCR integration using the local model package located in 'model/paddleocr'.
    Performs text detection and recognition on medical documents, prescriptions, and lab reports.
    """
    def __init__(self, model_dir: Optional[str] = None):
        self.model_dir = model_dir or os.getenv("PADDLEOCR_MODEL_PATH", PADDLEOCR_DIR)
        self._ocr_engine = None
        self._init_attempted = False

    def _get_engine(self):
        if not self._init_attempted:
            self._init_attempted = True
            try:
                from paddleocr import PaddleOCR
                logger.info(f"Initializing local PaddleOCR engine from: {self.model_dir}")
                # Phase 7: paddlepaddle 3.3.1's oneDNN CPU path crashes every
                # inference call on this machine (NotImplementedError:
                # ConvertPirAttribute2RuntimeAttribute not supported). Running
                # the same models with oneDNN/mkldnn disabled is verified to
                # work on pure CPU — no GPU, no dependency changes. Older
                # paddleocr releases lack the kwarg; fall back to their
                # signature unchanged.
                try:
                    self._ocr_engine = PaddleOCR(lang="en", enable_mkldnn=False)
                except TypeError:
                    self._ocr_engine = PaddleOCR(use_angle_cls=True, lang="en")
                logger.info("Local PaddleOCR engine initialized successfully.")
            except BaseException as e:
                # ImportError AND broken native installs (OSError from Paddle DLLs)
                # must degrade to the parsing pipeline — never fake OCR output.
                logger.info(
                    f"PaddleOCR local model at {self.model_dir} ({e}); "
                    "operating in clinical parsing fallback mode."
                )
                self._ocr_engine = None
        return self._ocr_engine

    def available(self) -> bool:
        """True when the image OCR engine actually loaded (probed once)."""
        return self._get_engine() is not None

    def extract_text(self, image_path: str) -> Optional[str]:
        engine = self._get_engine()
        if not engine:
            return None
        try:
            # Run OCR prediction
            if hasattr(engine, "predict"):
                results = engine.predict(image_path)
            elif hasattr(engine, "ocr"):
                results = engine.ocr(image_path)
            else:
                return None

            lines = []
            if isinstance(results, list):
                for item in results:
                    if isinstance(item, list):
                        for sub in item:
                            if isinstance(sub, (list, tuple)) and len(sub) >= 2 and isinstance(sub[1], (list, tuple)):
                                lines.append(str(sub[1][0]))
                            elif isinstance(sub, str):
                                lines.append(sub)
                    elif isinstance(item, dict):
                        rec_texts = item.get("rec_texts") or item.get("rec_text") or []
                        if isinstance(rec_texts, list):
                            lines.extend([str(t) for t in rec_texts])
                        elif isinstance(rec_texts, str):
                            lines.append(rec_texts)
            elif isinstance(results, dict):
                rec_texts = results.get("rec_texts") or results.get("rec_text") or []
                if isinstance(rec_texts, list):
                    lines.extend([str(t) for t in rec_texts])
                elif isinstance(rec_texts, str):
                    lines.append(rec_texts)

            cleaned_text = "\n".join([line.strip() for line in lines if line.strip()]).strip()
            if cleaned_text:
                logger.info(f"PaddleOCR successfully extracted {len(lines)} text lines from {image_path}")
                return cleaned_text
        except Exception as e:
            logger.warning(f"PaddleOCR extraction failed on {image_path}: {e}")
        return None

class ExtractedClinicalData(BaseModel):
    document_type: str # PRESCRIPTION, LAB_REPORT, DISCHARGE_SUMMARY, OTHER
    raw_text: str
    overall_confidence: float
    patient_name: Dict[str, Any]
    medications: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    diagnoses: List[Dict[str, Any]]
    allergies: List[Dict[str, Any]]
    surgeries: List[Dict[str, Any]]

class DocumentProcessor(ABC):
    @abstractmethod
    async def classify(self, file_path: str, mime_type: str) -> str:
        pass

    @abstractmethod
    async def extract(self, file_path: str, mime_type: str) -> ExtractedClinicalData:
        pass

class ClinicalDocumentProcessor(DocumentProcessor):
    """
    Production-grade document processor implementing OCR, document classification,
    and clinical entity extraction for Indian healthcare OPDs.
    Powered by PaddleOCR (using local model in 'model/paddleocr') and PDF clinical parsers.
    """
    def __init__(self):
        self.paddle_ocr = PaddleOCRProcessor()

    def engine_available(self) -> bool:
        return self.paddle_ocr.available()

    async def classify(self, file_path: str, mime_type: str) -> str:
        return self._classify_text(self._extract_text_blocking(file_path, mime_type))

    def _classify_text(self, text: str) -> str:
        # OCR output is evidence, not confirmed truth: classify as OTHER unless
        # the document text itself matches a known type — never overwrite a
        # human-selected type with a fabricated guess.
        text_lower = (text or "").lower()
        if not text_lower.strip():
            return "OTHER"

        if "discharge summary" in text_lower or "date of admission" in text_lower or "hospital discharge" in text_lower:
            return "DISCHARGE_SUMMARY"
        elif "lab report" in text_lower or "investigation" in text_lower or "hemoglobin" in text_lower or "hba1c" in text_lower or "pathology" in text_lower:
            return "LAB_REPORT"
        elif "rx" in text_lower or "prescription" in text_lower or "tablet" in text_lower or "syrup" in text_lower or "capsule" in text_lower or "mg" in text_lower:
            return "PRESCRIPTION"
        return "OTHER"

    async def extract(self, file_path: str, mime_type: str) -> ExtractedClinicalData:
        # Async façade kept for existing callers; the work itself is blocking
        # and exposed via extract_blocking() so routers can run it in a thread
        # with a timeout.
        return self.extract_blocking(file_path, mime_type)

    def extract_blocking(self, file_path: str, mime_type: str) -> ExtractedClinicalData:
        raw_text = self._extract_text_blocking(file_path, mime_type)
        doc_type = self._classify_text(raw_text)

        if not raw_text.strip():
            # Nothing readable — report honestly with zero entities instead of
            # inventing clinical content. Type stays OTHER for the router's call.
            return ExtractedClinicalData(
                document_type="OTHER",
                raw_text="",
                overall_confidence=0.0,
                patient_name={"name": "", "confidence": 0.0},
                medications=[],
                observations=[],
                diagnoses=[],
                allergies=[],
                surgeries=[],
            )

        medications: List[Dict[str, Any]] = []
        observations: List[Dict[str, Any]] = []
        diagnoses: List[Dict[str, Any]] = []
        allergies: List[Dict[str, Any]] = []
        surgeries: List[Dict[str, Any]] = []
        
        # Parse based on text patterns & clinical heuristics
        med_patterns = [
            r"(?:Tab(?:let)?|Cap(?:sule)?|Inj(?:ection)?|Syp)?\s*([A-Za-z]+(?:\s+[A-Za-z]+)?)\s*(\d+(?:\.\d+)?\s*(?:mg|mcg|ml|g|IU))\s*(1-0-1|1-0-0|0-0-1|1-1-1|OD|BD|TDS|QID|SOS|PRN)?",
            r"(Metformin|Glimepiride|Atorvastatin|Telmisartan|Amlodipine|Aspirin|Pantoprazole|Montelukast|Levothyroxine|Amoxicillin|Paracetamol)\s*(\d+\s*mg)?"
        ]
        
        for pat in med_patterns:
            matches = re.finditer(pat, raw_text, re.IGNORECASE)
            for m in matches:
                name = m.group(1).strip()
                # Never invent missing dosage/frequency — record exactly what
                # the document shows (empty means "not readable").
                dose = m.group(2).strip() if len(m.groups()) >= 2 and m.group(2) else ""
                freq = m.group(3).strip() if len(m.groups()) >= 3 and m.group(3) else ""

                # Confidence determination (OCR output is NEVER auto-verified)
                conf = 0.95 if dose and any(known in name.lower() for known in ["metformin", "atorvastatin", "telmisartan", "aspirin"]) else 0.85

                medications.append({
                    "name": name,
                    "dosage": dose,
                    "frequency": freq,
                    "confidence": conf,
                    "source_snippet": m.group(0),
                    "doctor_verified": False
                })

        # Lab tests parsing
        lab_patterns = [
            (r"HbA1c\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(%)?", "HbA1c", "%", "4.0 - 5.6%"),
            (r"Fasting\s*(?:Blood\s*)?Glucose\s*[:=]?\s*(\d+)\s*(mg/dL)?", "Fasting Blood Glucose", "mg/dL", "70 - 100 mg/dL"),
            (r"Postprandial\s*(?:Glucose|Sugar)\s*[:=]?\s*(\d+)\s*(mg/dL)?", "Postprandial Glucose", "mg/dL", "< 140 mg/dL"),
            (r"Serum\s*Creatinine\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(mg/dL)?", "Serum Creatinine", "mg/dL", "0.7 - 1.2 mg/dL"),
            (r"Total\s*Cholesterol\s*[:=]?\s*(\d+)\s*(mg/dL)?", "Total Cholesterol", "mg/dL", "< 200 mg/dL"),
            (r"Hemoglobin\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(g/dL)?", "Hemoglobin", "g/dL", "13.0 - 17.0 g/dL"),
            (r"Troponin\s*I\s*[:=]?\s*(Positive|Negative|\d+(?:\.\d+)?\s*ng/mL)", "Troponin I", "ng/mL", "< 0.04 ng/mL")
        ]
        
        for pat, test_name, default_unit, ref_range in lab_patterns:
            m = re.search(pat, raw_text, re.IGNORECASE)
            if m:
                val = m.group(1)
                unit = m.group(2) if len(m.groups()) >= 2 and m.group(2) else default_unit
                flag = "NORMAL"
                try:
                    num_val = float(val)
                    if test_name == "HbA1c" and num_val > 7.0:
                        flag = "HIGH"
                    elif test_name == "Fasting Blood Glucose" and num_val > 126:
                        flag = "HIGH"
                    elif test_name == "Serum Creatinine" and num_val > 1.3:
                        flag = "HIGH"
                except ValueError:
                    if "positive" in str(val).lower():
                        flag = "CRITICAL"

                observations.append({
                    "test_name": test_name,
                    "test_value": str(val),
                    "unit": unit,
                    "reference_range": ref_range,
                    "flag": flag,
                    "confidence": 0.98,
                    "source_snippet": m.group(0),
                    "doctor_verified": False  # physician confirms via verify endpoint
                })

        # Diagnoses parsing
        diag_patterns = [
            r"(?:Diagnosis|Impression|History of)\s*[:=]?\s*([A-Za-z0-9\s,-]+)",
            r"(Type\s*2\s*Diabetes\s*Mellitus|Hypertension|Coronary\s*Artery\s*Disease|Bronchial\s*Asthma|Dyslipidemia)"
        ]
        for pat in diag_patterns:
            matches = re.finditer(pat, raw_text, re.IGNORECASE)
            for m in matches:
                diag = m.group(1).strip()
                if len(diag) > 3 and diag.lower() not in ["none", "nil"]:
                    diagnoses.append({
                        "name": diag,
                        "confidence": 0.92,
                        "source_snippet": m.group(0),
                        "doctor_verified": False  # OCR text is not a confirmed diagnosis
                    })

        # Surgeries and Allergies — recorded as raw mentions, unverified; the
        # exact wording is preserved in source_snippet instead of inventing
        # specific procedures/years the document may not state.
        for kw in ("stent", "angioplasty", "ptca"):
            if kw in raw_text.lower():
                snippet = next((ln for ln in raw_text.splitlines() if kw in ln.lower()), kw)
                surgeries.append({
                    "procedure_name": f"Document mentions '{kw}' (details need verification)",
                    "approximate_year": "",
                    "confidence": 0.62,
                    "doctor_verified": False,
                    "note": "Keyword mention in document - verify with physician records"
                })
                break

        if "penicillin" in raw_text.lower():
            allergies.append({
                "allergen": "Penicillin",
                "reaction": "Mentioned in document - reaction not extracted reliably",
                "severity": "UNSPECIFIED",
                "confidence": 0.9,
                "doctor_verified": False
            })

        # Patient name
        name_match = re.search(r"Patient\s*(?:Name)?\s*[:=]?\s*([A-Za-z\s]+)", raw_text, re.IGNORECASE)
        patient_name = {
            "name": name_match.group(1).strip() if name_match else "Patient Record",
            "confidence": 0.99 if name_match else 0.85
        }

        # Calculate overall confidence
        all_confs = [0.95]
        if medications:
            all_confs.extend([m["confidence"] for m in medications])
        if observations:
            all_confs.extend([o["confidence"] for o in observations])
        avg_conf = sum(all_confs) / len(all_confs)

        return ExtractedClinicalData(
            document_type=doc_type,
            raw_text=raw_text,
            overall_confidence=round(avg_conf, 2),
            patient_name=patient_name,
            medications=medications,
            observations=observations,
            diagnoses=diagnoses,
            allergies=allergies,
            surgeries=surgeries
        )

    def _extract_text_blocking(self, file_path: str, mime_type: str) -> str:
        # Honest extraction: returns ONLY text actually present in the file
        # (PDF text layer, OCR, or readable text content) — never synthetic
        # demo content. Empty string means "nothing could be read".
        if not os.path.exists(file_path):
            logger.warning(f"Document file missing at {file_path}; no text extracted.")
            return ""
            
        if "pdf" in mime_type.lower() or file_path.endswith(".pdf"):
            if pypdf:
                try:
                    reader = pypdf.PdfReader(file_path)
                    text = "".join([page.extract_text() or "" for page in reader.pages])
                    if text.strip():
                        return text
                except Exception as e:
                    logger.warning(f"Failed to read PDF with pypdf: {e}")

        # If it's an image, or text could not be extracted directly from PDF, perform PaddleOCR
        try:
            paddle_text = self.paddle_ocr.extract_text(file_path)
            if paddle_text and paddle_text.strip():
                return paddle_text
        except Exception as e:
            logger.info(f"PaddleOCR processing fallback ({e}); using clinical pipeline parser.")

        # Fallback to readable text if the file is text-based or has pre-extracted
        # metadata. Binary formats (images/PDFs/office) must NEVER be dumped as
        # text — binary garbage is not document content.
        if not file_path.lower().endswith((
            ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip", ".exe",
        )):
            try:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    if len(content.strip()) > 10:
                        return content
            except Exception:
                pass

        return ""
