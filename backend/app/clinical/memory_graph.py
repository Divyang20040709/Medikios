from typing import List, Dict, Any
from backend.app.schemas.pydantic_models import GraphNode, GraphEdge, DoctorMemoryGraphResponse

class DoctorMemoryGraphBuilder:
    @staticmethod
    def build_graph(
        patient: Any,
        medications: List[Any],
        observations: List[Any],
        allergies: List[Any],
        surgeries: List[Any],
        encounters: List[Any],
        extracted_entities: List[Any]
    ) -> DoctorMemoryGraphResponse:
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        
        # Root Node: Patient
        patient_node_id = f"patient_{patient.id}"
        nodes.append(GraphNode(
            id=patient_node_id,
            type="PATIENT",
            label=f"{patient.name} ({patient.age}y / {patient.gender[0]})",
            details={
                "mrn": patient.mrn,
                "abha_id": patient.abha_id,
                "blood_group": patient.blood_group,
                "phone": patient.phone
            },
            confidence=1.0
        ))

        # Node Group: Chronic Conditions / Diagnoses
        seen_conditions = set()
        for doc_entity in extracted_entities:
            if getattr(doc_entity, "entity_type", "") == "DIAGNOSIS":
                c_name = getattr(doc_entity, "entity_name", "").strip()
                c_id = f"cond_{c_name.lower().replace(' ', '_')}"
                if c_id not in seen_conditions:
                    seen_conditions.add(c_id)
                    conf = getattr(doc_entity, "confidence", 0.95)
                    nodes.append(GraphNode(
                        id=c_id,
                        type="CONDITION",
                        label=c_name,
                        details={"provenance": "Extracted from historical records", "verified": getattr(doc_entity, "doctor_verified", False)},
                        confidence=conf
                    ))
                    edges.append(GraphEdge(
                        source=patient_node_id,
                        target=c_id,
                        relation="DIAGNOSED_WITH",
                        provenance="Medical Document / Intake"
                    ))

        # Node Group: Current & Historical Medications
        seen_meds = set()
        for med in medications:
            med_name = getattr(med, "name", "").strip()
            med_id = f"med_{med_name.lower().replace(' ', '_')}"
            if med_id not in seen_meds:
                seen_meds.add(med_id)
                nodes.append(GraphNode(
                    id=med_id,
                    type="MEDICATION",
                    label=f"{med_name} {getattr(med, 'dosage', '') or ''}".strip(),
                    details={
                        "dosage": getattr(med, "dosage", None),
                        "frequency": getattr(med, "frequency", None),
                        "is_active": getattr(med, "is_active", True)
                    },
                    confidence=0.96
                ))
                edges.append(GraphEdge(
                    source=patient_node_id,
                    target=med_id,
                    relation="PRESCRIBED",
                    provenance=getattr(med, "provenance", "Prescription OCR")
                ))

        # Node Group: Allergies
        for alg in allergies:
            alg_name = getattr(alg, "allergen", "").strip()
            alg_id = f"alg_{alg_name.lower().replace(' ', '_')}"
            nodes.append(GraphNode(
                id=alg_id,
                type="ALLERGY",
                label=f"Allergy: {alg_name}",
                details={"reaction": getattr(alg, "reaction", None), "severity": getattr(alg, "severity", "MODERATE")},
                confidence=1.0
            ))
            edges.append(GraphEdge(
                source=patient_node_id,
                target=alg_id,
                relation="ALLERGIC_TO",
                provenance=getattr(alg, "provenance", "Patient Reported")
            ))

        # Node Group: Past Surgeries
        for surg in surgeries:
            surg_name = getattr(surg, "procedure_name", "").strip()
            surg_id = f"surg_{surg_name.lower().replace(' ', '_')}"
            nodes.append(GraphNode(
                id=surg_id,
                type="SURGERY",
                label=f"Surgery: {surg_name}",
                details={"year": getattr(surg, "approximate_year", None), "notes": getattr(surg, "notes", None)},
                confidence=1.0
            ))
            edges.append(GraphEdge(
                source=patient_node_id,
                target=surg_id,
                relation="UNDERWENT",
                provenance=getattr(surg, "provenance", "Surgical History")
            ))

        # Node Group: Key Lab Observations
        for obs in observations:
            obs_name = getattr(obs, "test_name", "").strip()
            obs_val = getattr(obs, "test_value", "").strip()
            obs_unit = getattr(obs, "unit", "") or ""
            obs_id = f"obs_{obs_name.lower().replace(' ', '_')}"
            nodes.append(GraphNode(
                id=obs_id,
                type="OBSERVATION",
                label=f"{obs_name}: {obs_val} {obs_unit}".strip(),
                details={"flag": getattr(obs, "flag", "NORMAL"), "date": getattr(obs, "observed_date", None)},
                confidence=0.98
            ))
            edges.append(GraphEdge(
                source=patient_node_id,
                target=obs_id,
                relation="OBSERVED_TEST",
                provenance=getattr(obs, "provenance", "Lab Report")
            ))

        # Node Group: Encounters
        for enc in encounters:
            enc_id = f"enc_{enc.id}"
            nodes.append(GraphNode(
                id=enc_id,
                type="ENCOUNTER",
                label=f"Visit: {enc.token_number} ({enc.department})",
                details={"status": enc.status, "priority": enc.priority},
                confidence=1.0
            ))
            edges.append(GraphEdge(
                source=patient_node_id,
                target=enc_id,
                relation="VISITED",
                provenance="Hospital Intake System"
            ))

        return DoctorMemoryGraphResponse(
            patient_id=patient.id,
            nodes=nodes,
            edges=edges
        )
