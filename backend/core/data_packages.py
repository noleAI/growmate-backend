import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("core.data_packages")

ALLOWED_RISK_LEVELS = {"low", "medium", "high"}
ALLOWED_MODES = {"normal", "recovery", "hitl_pending"}
ALLOWED_INTERVENTION_TYPES = {
    "review",
    "practice",
    "recovery",
    "breath",
    "grounding",
}

REQUIRED_DIAGNOSIS_FIELDS = {
    "diagnosisId",
    "title",
    "gapAnalysis",
    "diagnosisReason",
    "strengths",
    "needsReview",
    "confidence",
    "riskLevel",
    "mode",
    "requiresHITL",
    "nextSuggestedTopic",
    "interventionPlan",
}

REQUIRED_INTERVENTION_FIELDS = {
    "interventionId",
    "type",
    "title",
    "description",
    "duration",
    "intensity",
    "applicableRiskLevels",
    "tags",
}

REQUIRED_RUNTIME_ROOT_FIELDS = {
    "version",
    "created_at",
    "thresholds",
    "fallbackRules",
    "hitlConditions",
}


@dataclass
class DataPackagesBundle:
    diagnosis_scenarios: List[Dict[str, Any]]
    interventions_by_id: Dict[str, Dict[str, Any]]
    runtime_config: Dict[str, Any]


class DataPackagesService:
    def __init__(
        self,
        diagnosis_path: Path,
        intervention_path: Path,
        runtime_config_path: Path,
    ):
        self.diagnosis_path = diagnosis_path
        self.intervention_path = intervention_path
        self.runtime_config_path = runtime_config_path
        self.bundle: Optional[DataPackagesBundle] = None

    @classmethod
    def from_default_paths(cls) -> "DataPackagesService":
        backend_root = Path(__file__).resolve().parents[1]
        return cls(
            diagnosis_path=backend_root / "data" / "diagnosis" / "diagnosis_scenarios.json",
            intervention_path=backend_root / "data" / "interventions" / "intervention_catalog.json",
            runtime_config_path=backend_root
            / "configs"
            / "runtime"
            / "runtime_decision_config.json",
        )

    def is_ready(self) -> bool:
        return self.bundle is not None

    def load(self) -> bool:
        try:
            diagnosis = self._read_json(self.diagnosis_path)
            interventions_root = self._read_json(self.intervention_path)
            runtime_config = self._read_json(self.runtime_config_path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load data packages: %s", exc)
            self.bundle = None
            return False

        interventions = interventions_root.get("interventions", [])
        issues = self._validate_payloads(diagnosis, interventions, runtime_config)

        if issues:
            for issue in issues:
                logger.warning("[data-packages] %s", issue)
            self.bundle = None
            return False

        interventions_by_id = {
            str(item["interventionId"]): dict(item) for item in interventions
        }

        self.bundle = DataPackagesBundle(
            diagnosis_scenarios=[dict(item) for item in diagnosis],
            interventions_by_id=interventions_by_id,
            runtime_config=dict(runtime_config),
        )
        logger.info("Data packages loaded successfully")
        return True

    def get_risk_band(self, uncertainty: float) -> str:
        if not self.bundle:
            return "medium"

        thresholds = (
            self.bundle.runtime_config.get("thresholds", {})
            .get("riskThresholds", {})
        )
        value = float(uncertainty)

        for band in ("low", "medium", "high"):
            rule = thresholds.get(band, {})
            min_value = float(rule.get("minUncertainty", 0.0))
            max_value = float(rule.get("maxUncertainty", 1.0))
            if min_value <= value <= max_value:
                return band

        return "high" if value > 1.0 else "medium"

    def get_confidence_band(self, confidence: float) -> str:
        if not self.bundle:
            return "medium"

        thresholds = (
            self.bundle.runtime_config.get("thresholds", {})
            .get("confidenceThresholds", {})
        )
        value = float(confidence)

        for band in ("low", "medium", "high"):
            rule = thresholds.get(band, {})
            min_value = float(rule.get("min", 0.0))
            max_value = float(rule.get("max", 1.0))
            if min_value <= value <= max_value:
                return band

        return "low" if value < 0.0 else "high"

    def should_trigger_hitl(self, uncertainty: float, confidence: float) -> bool:
        if not self.bundle:
            return False

        hitl_conditions = self.bundle.runtime_config.get("hitlConditions", {})
        uncertainty_threshold = float(hitl_conditions.get("uncertaintyHitlThreshold", 1.0))
        confidence_threshold = float(hitl_conditions.get("confidenceHitlThreshold", 0.0))

        return float(uncertainty) >= uncertainty_threshold or float(confidence) <= confidence_threshold

    def resolve_diagnosis(
        self,
        mode: str,
        risk_level: str,
        prefer_fallback_safe: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not self.bundle:
            return None

        scenarios = self.bundle.diagnosis_scenarios

        if prefer_fallback_safe:
            for item in scenarios:
                diagnosis_id = str(item.get("diagnosisId", "")).upper()
                if "FALLBACK_SAFE" in diagnosis_id:
                    return dict(item)

        mode_candidates = [item for item in scenarios if item.get("mode") == mode]
        if not mode_candidates:
            return None

        exact = [item for item in mode_candidates if item.get("riskLevel") == risk_level]
        if exact:
            return dict(exact[0])

        return dict(mode_candidates[0])

    def resolve_interventions(self, intervention_ids: List[str]) -> List[Dict[str, Any]]:
        if not self.bundle:
            return []

        resolved: List[Dict[str, Any]] = []
        for intervention_id in intervention_ids:
            item = self.bundle.interventions_by_id.get(str(intervention_id))
            if item:
                resolved.append(dict(item))
        return resolved

    def get_fallback_intervention_id(self, mode: str, missing_plan: bool = False) -> Optional[str]:
        if not self.bundle:
            return None

        fallback_rules = self.bundle.runtime_config.get("fallbackRules", {})
        key = "missingInterventionPlan" if missing_plan else mode
        fallback_id = fallback_rules.get(key)
        if isinstance(fallback_id, str) and fallback_id:
            return fallback_id
        return None

    def _read_json(self, path: Path) -> Any:
        if not path.exists():
            raise FileNotFoundError(f"Missing data package file: {path}")

        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream)

    def _validate_payloads(
        self,
        diagnosis: Any,
        interventions: Any,
        runtime_config: Any,
    ) -> List[str]:
        issues: List[str] = []

        if not isinstance(diagnosis, list) or not diagnosis:
            issues.append("Package2 must be a non-empty JSON array")
            diagnosis = []

        if not isinstance(interventions, list) or not interventions:
            issues.append("Package3.interventions must be a non-empty array")
            interventions = []

        if not isinstance(runtime_config, dict):
            issues.append("Package4 must be a JSON object")
            runtime_config = {}

        intervention_ids: List[str] = []

        for item in diagnosis:
            if not isinstance(item, dict):
                issues.append("Package2 contains a non-object scenario")
                continue

            missing = REQUIRED_DIAGNOSIS_FIELDS - set(item.keys())
            if missing:
                issues.append(
                    f"Package2 missing fields in {item.get('diagnosisId', '<unknown>')}: {sorted(missing)}"
                )

            confidence = float(item.get("confidence", -1.0))
            if confidence < 0.0 or confidence > 1.0:
                issues.append(
                    f"Package2 confidence out of range in {item.get('diagnosisId', '<unknown>')}"
                )

            if item.get("riskLevel") not in ALLOWED_RISK_LEVELS:
                issues.append(
                    f"Package2 invalid riskLevel in {item.get('diagnosisId', '<unknown>')}"
                )

            if item.get("mode") not in ALLOWED_MODES:
                issues.append(
                    f"Package2 invalid mode in {item.get('diagnosisId', '<unknown>')}"
                )

        for item in interventions:
            if not isinstance(item, dict):
                issues.append("Package3 contains a non-object intervention")
                continue

            missing = REQUIRED_INTERVENTION_FIELDS - set(item.keys())
            if missing:
                issues.append(
                    f"Package3 missing fields in {item.get('interventionId', '<unknown>')}: {sorted(missing)}"
                )

            intervention_id = str(item.get("interventionId", ""))
            if intervention_id:
                intervention_ids.append(intervention_id)

            intervention_type = item.get("type")
            if intervention_type not in ALLOWED_INTERVENTION_TYPES:
                issues.append(
                    f"Package3 invalid type in {item.get('interventionId', '<unknown>')}"
                )

            for risk in item.get("applicableRiskLevels", []):
                if risk not in ALLOWED_RISK_LEVELS:
                    issues.append(
                        f"Package3 invalid applicableRiskLevels='{risk}' in {item.get('interventionId', '<unknown>')}"
                    )

        duplicates = [
            item for item, count in self._count_values(intervention_ids).items() if count > 1
        ]
        if duplicates:
            issues.append(f"Package3 duplicate interventionId: {sorted(duplicates)}")

        missing_root = REQUIRED_RUNTIME_ROOT_FIELDS - set(runtime_config.keys())
        if missing_root:
            issues.append(f"Package4 missing root fields: {sorted(missing_root)}")

        for mode in ("normal", "recovery", "hitl_pending", "missingInterventionPlan"):
            intervention_id = runtime_config.get("fallbackRules", {}).get(mode)
            if intervention_id and intervention_id not in intervention_ids:
                issues.append(
                    f"Package4 fallbackRules.{mode} references unknown interventionId='{intervention_id}'"
                )

        for item in diagnosis:
            for intervention_id in item.get("interventionPlan", []):
                if intervention_id not in intervention_ids:
                    issues.append(
                        f"Package2 interventionPlan references unknown interventionId='{intervention_id}'"
                    )

        return issues

    def _count_values(self, values: List[str]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return counts
