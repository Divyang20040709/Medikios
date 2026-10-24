# Clinical Triage Review — QA-09 & QA-10

**Status:** review complete · **no clinical rule was changed** · **routing decisions are open pending clinician sign-off**
**Scope:** the two open clinical findings from `QA_REPORT.md` §5, reviewed against the current code
**Not in scope:** model retraining, lexicon edits that alter escalation, department-mapping changes

> **Standing safety statement.** The triage classifier is an **advisory intake aid**. Its output is
> **not a clinical disposition, not a diagnosis and not a triage decision**. Nothing in this document
> authorises a patient to be routed, de-prioritised or discharged on model output alone. Every
> EMERGENCY/URGENT result must be confirmed in person by a clinician. The UI now states this
> explicitly on every high-priority result (see §5).

---

## 1. What the pipeline actually does

`POST /api/admin/models/triage-test` → `RedFlagEngine.classify_complaint_ml()`
(`backend/app/clinical/red_flags.py:59`).

It runs **four independent steps** and then stitches the results together:

| Step | Code | Produces |
|---|---|---|
| 1. Lexicon grounding | `red_flags.py:82-93` | `matched_concepts[]` by substring match against `model/indic_clinical_lexicon.json` |
| 2. Department model | `red_flags.py:101` (`dept_pipeline.predict`) | `pred_dept` — one of 7 OPD labels |
| 3. Priority model | `red_flags.py:102-106` (`prio_pipeline.predict` / `predict_proba`) | `pred_prio` + `confidence` |
| 4. Lexicon override | `red_flags.py:112-121` | forces `EMERGENCY`/`URGENT`, then `confidence = max(confidence, 0.95 \| 0.90)` |

**The structural problem:** steps 2 and 3 are two *different* classifiers with no shared state.
`department` and `priority` are therefore free to contradict each other, and nothing in the code
compares them. `confidence` describes **only** step 3; it says nothing about the department.

Held-out evaluation (`model/clinical_triage_evaluation.json`):

| Model | Accuracy | Weighted F1 |
|---|---|---|
| Department classifier (7 classes) | **65.8 %** | 0.643 |
| Priority classifier (3 classes) | 82.1 % | 0.806 |

A ~2-in-3 department accuracy is **not** a routing grade. That number alone is the reason the
department must stay a suggestion, not an assignment.

---

## 2. QA-09 — department / priority disagreement

### 2.1 Observed behaviour (reproduced)

`& $py scratch\qa_triage_samples.py` against the running backend:

| Input | Department | Priority | Confidence | Rule-raised | Routing review |
|---|---|---|---|---|---|
| "Severe crushing chest pain radiating to left jaw with cold sweating" | Cardiology / Acute Medicine | EMERGENCY | 0.95 | yes | no |
| Hindi chest pain + breathlessness | Cardiology / Acute Medicine | EMERGENCY | 0.95 | yes | no |
| **Gujarati chest pain + breathlessness** | **AYUSH / Kayachikitsa OPD** | **EMERGENCY** | 0.95 | yes | **yes** |
| "Routine general checkup" (41-year-old) | **Pediatrics OPD** | ROUTINE | 0.65 | no | no |
| "My 6 year old child has wheezing and shortness of breath" | Pediatrics OPD | EMERGENCY | 0.41 | no | no |

### 2.2 Affected code paths

| Concern | Location | Detail |
|---|---|---|
| Two models, no consistency check | `red_flags.py:96-121` | `pred_dept` and `pred_prio` computed independently; no reconciliation step exists |
| Emergency + traditional-medicine stream is representable | `red_flags.py:169-181` return dict | no guard at construction time |
| Stream classification of a department string | `backend/app/clinical/streams.py:39-45` (`stream_for`), `:30-36` (`_AYUSH_MARKERS`), `:21` (`AYUSH_DEPARTMENT`) | substring markers: `ayush`, `ayurved`, `kayachikitsa`, `panchakarma`, `traditional` |
| Age is not an input to the model | `admin_router.py:368-372` | the endpoint passes a **hardcoded `age=45`** to the duration model; the triage classifier never sees age at all |
| Where a patient's department is actually stored | `backend/app/api/intake_router.py:264` → `department_for_stream(requested, …)` | **the patient's own stream choice**, not the model |
| Unused classify endpoint | `intake_router.py:41-47` (`POST /api/intake/classify-complaint`) | returns model output; **no auth dependency**; **not called by the frontend** (verified by grep — 0 call sites) |

### 2.3 Blast radius, stated precisely

- **Does not reach a patient record today.** `Encounter.department` is written from the patient's
  kiosk stream choice (`intake_router.py:264`). The department classifier's label is displayed in the
  admin console and returned by the unused classify endpoint. This is why QA-09 is **P2
  (display/safety-adjacent)**, not P1 (wrong-care-delivered).
- **Risk if wired up later.** If anyone connects `classify-complaint` to the intake flow, a 65.8 %-accurate
  label would start writing "AYUSH / Kayachikitsa OPD" onto an emergency encounter. That must not
  happen without the guards in §4.
- **Already mitigated in presentation.** An EMERGENCY result that lands on an AYUSH stream is flagged
  `routing_review_required` and the UI tells staff the destination must be confirmed (`HospitalCommandCenter.tsx:732`).

### 2.4 Why it was not "fixed" here

Blocking AYUSH on EMERGENCY, or adding an age prior, changes **clinical routing policy**. Two of the
three proposed fixes silently overrule a clinician's judgement, and the third changes what the model
is allowed to output. Those need an owner who can be accountable for the rule — not a code guess.

---

## 3. QA-10 — false grounding concept

### 3.1 Observed behaviour

"Severe crushing chest pain radiating to left jaw with **cold** sweating" →
`matched_concepts` = `chest_pain`, breathlessness, **`fever_cough`**.

### 3.2 Root cause (confirmed in the lexicon file)

`red_flags.py:87` matches with a plain substring test:

```python
if any(t.lower() in cleaned_lower for t in all_terms):
```

`model/indic_clinical_lexicon.json` → `lexicon.fever_cough.en` contains the bare term **`"cold"`**.
`"cold sweating"` contains the substring `cold`, so a cardiogenic symptom is grounded as
"fever/cough". The same weakness exists in other entries:

| Concept | Short/ambiguous term | False-positive example |
|---|---|---|
| `fever_cough` | `"cold"` | "cold sweating", "cold extremities" |
| `chest_pain` (gu) | `"છાતીમાં"` ("in the chest") | "છાતીમાં બળતરા" is matched regardless of the symptom word |
| `chest_pain` (hi) | `"सीने"`, `"भारी दर्द"` | any heavy pain anywhere in the body |

### 3.3 Why this is not cosmetic

The same `matched_concepts` list drives the escalation rule at `red_flags.py:112-121`. A false match on a
concept carrying `priority: EMERGENCY` **raises** an encounter to EMERGENCY at 0.95 confidence; a
missed match **fails to raise** one. So QA-10 trades in both over-triage and under-triage, and the
inflated confidence it produces is indistinguishable from model certainty unless labelled (it now is).

---

## 4. Proposed fixes (all require approval before implementation)

Each is scoped, testable, and changes no clinician's authority.

### P-09-A · Surface the disagreement, change nothing *(recommended first step)*

Add a `department_priority_consistent` boolean (already adjacent to the round-2 `routing_review_required`
flag) and show it on the triage result instead of a bare destination. No routing change.
**Risk:** none clinical. **Effort:** ~1 h. **Owner:** engineering.

### P-09-B · Block EMERGENCY → AYUSH routing *(needs clinical approval — CD-1)*

If approved as **hard block**: an EMERGENCY priority forces the destination to an emergency-capable
modern-medicine department, and the original prediction is preserved in the payload for audit.
If approved as **soft block**: keep the prediction, require an explicit staff confirmation before the
token is issued to that department.
**Risk:** silently overriding an AYUSH clinician's scope; a hard block could also *under*-route patients
who genuinely present at an AYUSH OPD. **This is a policy decision, not an engineering one.**

### P-09-C · Age prior for age-banded departments *(needs clinical approval — CD-2)*

`Pediatrics OPD` must not be the top prediction for a patient aged ≥ 18. Requires age to be an input
(the classifier currently never receives it) plus a post-hoc constraint. **Risk:** paediatrics
adolescent-transfer boundaries are a clinic rule (16? 18?), not a typing decision.

### P-10-A · Word-boundary, minimum-length matching *(safe, engineering-owned)*

Replace substring matching with token-boundary matching, reject single-token Latin terms shorter than
4 characters, and require the longest matching term to win. `"cold sweating"` would then not match
`"cold"`. Add a unit test per ambiguity in §3.2.
**Risk:** **may turn off currently-working emergency matches** (e.g. `"सीने"`), i.e. it can cause
*under*-triage. Must be validated against the escalation test set before shipping. **Owner:**
engineering + clinical validation of the regression set.

### P-10-B · Lexicon curation *(needs clinical approval — CD-3)*

Remove or qualify the ambiguous short terms (`cold`, `सीने`, `છાતીમાં`, `भारी दर्द`) and add
disambiguated phrases. This edits clinical vocabulary; a clinician must sign the list.

### P-10-C · Confidence provenance *(done in round 2)*

`confidence_adjusted_by_rule` now travels with the result and the UI prints
"— raised by red-flag rule, not the model" (`HospitalCommandCenter.tsx:689`). No further work.

---

## 5. Safety controls currently in force (visible, not hidden)

| Control | Code | Effect |
|---|---|---|
| `requires_in_person_triage` | `red_flags.py:143` | true for every EMERGENCY/URGENT result |
| `routing_review_required` | `red_flags.py:144-146` | true when `priority == EMERGENCY and stream_for(department) == AYUSH` |
| `safety_notice` | `red_flags.py:147-167` | "Advisory only — not a clinical disposition…" plus the rule-raised and destination caveats |
| Red banner | `HospitalCommandCenter.tsx:716-725` | `role="alert"`, "**Not a clinical disposition.**" on every high-priority result |
| Amber banner | `HospitalCommandCenter.tsx:727-737` | `role="alert"`, "**Routing needs staff verification.**" on EMERGENCY + AYUSH |
| Confidence provenance | `HospitalCommandCenter.tsx:689` | rule-raised numbers are labelled as such |
| Truthful fallback | `red_flags.py:185-210` | if the model cannot load, `is_red_flag` now matches the returned priority instead of a hardcoded `False` |

Verified in the browser on 24 Oct 2026: Gujarati chest pain renders both banners; "Routine general
checkup" renders neither. Screenshot: `scratch/qa_grammar_fix_result_panel.png`.

---

## 6. Tests to add once a decision is made

| ID | Test | Asserts |
|---|---|---|
| T-09-1 | `test_emergency_never_routes_to_ayush` | for every emergency-rated sample, `stream_for(department) != AYUSH` **or** `routing_review_required is True` (whichever rule is approved) |
| T-09-2 | `test_adult_never_routed_to_pediatrics` | age ≥ 18 ⇒ `department != "Pediatrics OPD"` (only if CD-2 is approved) |
| T-09-3 | `test_priority_confidence_is_not_rule_inflated` | `confidence_adjusted_by_rule is False` ⇒ confidence equals the model's `predict_proba` value |
| T-10-1 | `test_cold_sweating_does_not_ground_fever_cough` | the cardiac sample's `matched_concepts` excludes `fever_cough` |
| T-10-2 | `test_chest_pain_grounds_chest_pain` | genuine chest-pain phrasing still produces `SNOMED-29857009` (regression guard for P-10-A) |
| T-10-3 | `test_grounding_requires_whole_token` | negative matrix for `cold` / `सीने` / `છાતીમાં` used outside a chest-pain phrase |
| T-ALL-1 | `test_high_priority_always_carries_safety_notice` | every emergency/urgent result has a non-empty `safety_notice` |

None of these are written yet: they encode a rule that does not exist, and a test that bakes in an
unapproved clinical rule is worse than no test.

---

## 7. Decisions requiring clinician approval

| ID | Decision | Options | Blocks |
|---|---|---|---|
| **CD-1** | Emergency complaint predicted into an AYUSH stream | (a) hard block to modern department · (b) allow + require explicit staff confirmation · (c) display only, as today | P-09-B, T-09-1 |
| **CD-2** | Age boundary for paediatrics | paediatric ≤ 16 / ≤ 18 · adolescent transfer rule · no age prior | P-09-C, T-09-2 |
| **CD-3** | Ambiguous lexicon terms | delete · restrict to disambiguated phrases · keep as-is | P-10-B |
| **CD-4** | Is a rule-driven escalation allowed to overwrite model priority at all? | yes (today) · no, expose as a separate advisory flag | T-09-3 |
| **CD-5** | Should `POST /api/intake/classify-complaint` exist at all? | remove it · keep but require auth · keep and document as advisory-only | new finding QA-16 |

Until CD-1…CD-5 are answered, the system keeps its current, documented behaviour: **the prediction is
shown unchanged and flagged for a human**, and no automated routing decision is taken from it.

---

## 8. Newly found while reviewing (reported, not changed)

**QA-16 — `POST /api/intake/classify-complaint` has no authentication and no caller.**
`backend/app/api/intake_router.py:41-47` exposes the classifier to anyone who can reach the backend,
with no `Depends(...)` guard, while no frontend code calls it (grep: 0 hits). An unauthenticated
compute endpoint is a cheap denial-of-service lever on the kiosk host. Recommended: add an auth
dependency, or remove the route. Not actioned here because removing a public route is a product
decision and adding auth has to be checked against any external caller.
