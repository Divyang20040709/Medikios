"""Consultation-stream mapping between patients and physicians.

MediKiosk runs two parallel OPD streams on one kiosk:

* ``MODERN`` — General & Modern Medicine (allopathic OPD)
* ``AYUSH``  — Traditional Medicine / AYUSH (Kayachikitsa / Panchakarma)

The patient picks the stream at kiosk Step 4 and it is persisted on
``Encounter.department``. Each DOCTOR account carries its own stream in
``User.department``. ``stream_for`` normalises both sides so routing never
depends on an exact string match (existing data already contains values such
as "Cardiology / Internal Medicine" or "AYUSH / Kayachikitsa OPD").
"""

from typing import Optional

MODERN = "MODERN"
AYUSH = "AYUSH"

# Canonical department values written by the kiosk once the stream is chosen.
AYUSH_DEPARTMENT = "AYUSH / Kayachikitsa OPD"
MODERN_DEPARTMENT = "General Medicine"

# Staff account departments (seeded in scripts/seed.py).
AYUSH_DOCTOR_DEPARTMENT = "Traditional Medicine / AYUSH"
MODERN_DOCTOR_DEPARTMENT = "General & Modern Medicine"

# Substrings that identify the traditional stream in either a patient's
# encounter department or a physician's own department.
_AYUSH_MARKERS = (
    "ayush",
    "ayurved",
    "kayachikitsa",
    "panchakarma",
    "traditional",
)


def stream_for(department: Optional[str]) -> str:
    """Return ``AYUSH`` or ``MODERN`` for an encounter/physician department."""
    if department:
        lowered = department.lower()
        if any(marker in lowered for marker in _AYUSH_MARKERS):
            return AYUSH
    return MODERN


def department_for_stream(stream: str, previous: Optional[str] = None) -> str:
    """Department to store on an encounter for the chosen patient stream.

    AYUSH always maps to the AYUSH OPD. MODERN keeps the already-recorded
    allopathic department (e.g. "Cardiology / Internal Medicine") when it is
    not an AYUSH value, so no clinical routing detail is lost when a patient
    toggles the card back to General & Modern Medicine.
    """
    if stream_for(stream) == AYUSH:
        return AYUSH_DEPARTMENT
    if previous and stream_for(previous) == MODERN:
        return previous
    return MODERN_DEPARTMENT
