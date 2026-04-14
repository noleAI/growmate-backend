import json
from pathlib import Path

from core.data_packages import DataPackagesService


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_data_packages_service_loads_default_files() -> None:
    service = DataPackagesService.from_default_paths()

    assert service.load() is True
    assert service.is_ready() is True

    assert service.get_risk_band(0.22) == "low"
    assert service.get_risk_band(0.55) == "medium"
    assert service.get_risk_band(0.82) == "high"

    assert service.get_confidence_band(0.39) == "low"
    assert service.get_confidence_band(0.6) == "medium"
    assert service.get_confidence_band(0.93) == "high"

    assert service.should_trigger_hitl(0.82, 0.52) is True
    assert service.should_trigger_hitl(0.22, 0.93) is False


def test_data_packages_service_rejects_unknown_intervention_reference(
    tmp_path: Path,
) -> None:
    diagnosis_path = tmp_path / "diagnosis.json"
    interventions_path = tmp_path / "interventions.json"
    runtime_path = tmp_path / "runtime.json"

    diagnosis_payload = [
        {
            "diagnosisId": "DIAG_1",
            "title": "normal",
            "gapAnalysis": "ok",
            "diagnosisReason": "ok",
            "strengths": ["s"],
            "needsReview": ["n"],
            "confidence": 0.7,
            "riskLevel": "medium",
            "mode": "recovery",
            "requiresHITL": False,
            "nextSuggestedTopic": "derivative",
            "interventionPlan": ["INTV_UNKNOWN"],
        }
    ]

    interventions_payload = {
        "interventions": [
            {
                "interventionId": "INTV_KNOWN",
                "type": "recovery",
                "title": "known",
                "description": "known",
                "duration": 5,
                "intensity": "low",
                "applicableRiskLevels": ["low", "medium"],
                "tags": ["tag"],
            }
        ]
    }

    runtime_payload = {
        "version": "v1",
        "created_at": "2026-04-14T00:00:00Z",
        "thresholds": {
            "riskThresholds": {
                "low": {"minUncertainty": 0.0, "maxUncertainty": 0.39},
                "medium": {"minUncertainty": 0.4, "maxUncertainty": 0.69},
                "high": {"minUncertainty": 0.7, "maxUncertainty": 1.0},
            },
            "confidenceThresholds": {
                "low": {"min": 0.0, "max": 0.44},
                "medium": {"min": 0.45, "max": 0.79},
                "high": {"min": 0.8, "max": 1.0},
            },
        },
        "fallbackRules": {
            "normal": "INTV_KNOWN",
            "recovery": "INTV_KNOWN",
            "hitl_pending": "INTV_KNOWN",
            "missingInterventionPlan": "INTV_KNOWN",
        },
        "hitlConditions": {
            "mode": "hitl_pending",
            "requiresHITL": True,
            "uncertaintyHitlThreshold": 0.7,
            "confidenceHitlThreshold": 0.4,
            "idleTimeHighSeconds": 45,
            "allowAutoRecoveryWhenHitlUnavailable": True,
        },
    }

    _write_json(diagnosis_path, diagnosis_payload)
    _write_json(interventions_path, interventions_payload)
    _write_json(runtime_path, runtime_payload)

    service = DataPackagesService(
        diagnosis_path=diagnosis_path,
        intervention_path=interventions_path,
        runtime_config_path=runtime_path,
    )

    assert service.load() is False
    assert service.is_ready() is False


def test_data_packages_service_tolerates_non_dict_diagnosis_items(
    tmp_path: Path,
) -> None:
    """Non-dict items in the diagnosis array must not raise AttributeError."""
    diagnosis_path = tmp_path / "diagnosis.json"
    interventions_path = tmp_path / "interventions.json"
    runtime_path = tmp_path / "runtime.json"

    # Mix a valid dict scenario with a plain string (non-dict) to trigger the guard.
    diagnosis_payload = [
        "not-a-dict",
        {
            "diagnosisId": "DIAG_GOOD",
            "title": "ok",
            "gapAnalysis": "ok",
            "diagnosisReason": "ok",
            "strengths": ["s"],
            "needsReview": ["n"],
            "confidence": 0.8,
            "riskLevel": "low",
            "mode": "normal",
            "requiresHITL": False,
            "nextSuggestedTopic": "topic",
            "interventionPlan": ["INTV_A"],
        },
    ]

    interventions_payload = {
        "interventions": [
            {
                "interventionId": "INTV_A",
                "type": "review",
                "title": "a",
                "description": "a",
                "duration": 5,
                "intensity": "low",
                "applicableRiskLevels": ["low"],
                "tags": [],
            }
        ]
    }

    runtime_payload = {
        "version": "v1",
        "created_at": "2026-04-14T00:00:00Z",
        "thresholds": {
            "riskThresholds": {
                "low": {"minUncertainty": 0.0, "maxUncertainty": 0.39},
                "medium": {"minUncertainty": 0.4, "maxUncertainty": 0.69},
                "high": {"minUncertainty": 0.7, "maxUncertainty": 1.0},
            },
            "confidenceThresholds": {
                "low": {"min": 0.0, "max": 0.44},
                "medium": {"min": 0.45, "max": 0.79},
                "high": {"min": 0.8, "max": 1.0},
            },
        },
        "fallbackRules": {
            "normal": "INTV_A",
            "recovery": "INTV_A",
            "hitl_pending": "INTV_A",
            "missingInterventionPlan": "INTV_A",
        },
        "hitlConditions": {
            "uncertaintyHitlThreshold": 0.7,
            "confidenceHitlThreshold": 0.4,
        },
    }

    _write_json(diagnosis_path, diagnosis_payload)
    _write_json(interventions_path, interventions_payload)
    _write_json(runtime_path, runtime_payload)

    service = DataPackagesService(
        diagnosis_path=diagnosis_path,
        intervention_path=interventions_path,
        runtime_config_path=runtime_path,
    )

    # Validation should flag the non-dict item but NOT raise AttributeError.
    assert service.load() is False
    assert service.is_ready() is False


def test_data_packages_service_resolves_diagnosis_and_interventions() -> None:
    service = DataPackagesService.from_default_paths()
    assert service.load() is True

    diagnosis = service.resolve_diagnosis(mode="normal", risk_level="low")
    assert diagnosis is not None
    assert diagnosis["diagnosisId"] == "MATH_DERIV_DIAG_NORMAL_SUCCESS"

    interventions = service.resolve_interventions(diagnosis["interventionPlan"])
    assert interventions
    assert interventions[0]["interventionId"] == "INTV_REVIEW_DERIV_RULES"

    fallback_id = service.get_fallback_intervention_id(mode="recovery", missing_plan=True)
    assert fallback_id == "INTV_RECOVERY_LIGHT_RESTART"
