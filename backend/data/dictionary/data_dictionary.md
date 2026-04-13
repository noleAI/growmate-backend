# Package 5 - Data Dictionary (v1.0)

Nguon du lieu doi chieu:
- Package 2: `backend/data/diagnosis/diagnosis_scenarios.json`
- Package 3: `backend/data/interventions/intervention_catalog.json`
- Package 4: `backend/configs/runtime/runtime_decision_config.json`

## Package 2 - Diagnosis Scenarios

| Field | Field description | Data type | Enum values | Required | Example value |
|---|---|---|---|---|---|
| package2[] | Danh sach scenario diagnosis | array<object> | N/A | Required | `[ {...}, {...} ]` |
| package2[].diagnosisId | Ma dinh danh diagnosis duy nhat | string | N/A | Required | `MATH_DERIV_DIAG_NORMAL_SUCCESS` |
| package2[].title | Tieu de scenario hien thi cho UI | string | N/A | Required | `Tien trien on dinh` |
| package2[].gapAnalysis | Tom tat khoang trong hoc tap | string | N/A | Required | `Hoc sinh nam chac...` |
| package2[].diagnosisReason | Ly do he thong dua ra diagnosis | string | N/A | Required | `Cac luot tra loi gan day...` |
| package2[].strengths[] | Danh sach diem manh cua hoc sinh | array<string> | N/A | Required | `["Nhan dien dung dang bai..."]` |
| package2[].needsReview[] | Danh sach muc can on lai | array<string> | N/A | Required | `["On dinh ky hieu..."]` |
| package2[].confidence | Do tin cay diagnosis | number | 0.0..1.0 | Required | `0.93` |
| package2[].riskLevel | Muc rui ro | string | `low`, `medium`, `high` | Required | `low` |
| package2[].mode | Che do runtime | string | `normal`, `recovery`, `hitl_pending` | Required | `normal` |
| package2[].requiresHITL | Co can Human-in-the-loop hay khong | boolean | `true`, `false` | Required | `false` |
| package2[].nextSuggestedTopic | Topic de xuat tiep theo | string | N/A | Required | `derivative` |
| package2[].interventionPlan[] | Danh sach `interventionId` duoc de xuat | array<string> | Tham chieu Package 3 | Required | `["INTV_REVIEW_DERIV_RULES","INTV_PRACTICE_TIMED_DERIV"]` |

## Package 3 - Intervention Catalog

| Field | Field description | Data type | Enum values | Required | Example value |
|---|---|---|---|---|---|
| package3.interventions | Danh sach intervention canonical | array<object> | N/A | Required | `[ {...}, {...} ]` |
| package3.interventions[].interventionId | Ma intervention duy nhat | string | N/A | Required | `INTV_REVIEW_DERIV_RULES` |
| package3.interventions[].type | Nhom intervention | string | `review`, `practice`, `recovery`, `breath`, `grounding` | Required | `review` |
| package3.interventions[].title | Tieu de intervention | string | N/A | Required | `On nhanh derivative rules` |
| package3.interventions[].description | Mo ta intervention de render UI | string | N/A | Required | `On lai cac quy tac dao ham...` |
| package3.interventions[].duration | Thoi luong khuyen nghi (phut) | number | integer > 0 | Required | `8` |
| package3.interventions[].intensity | Cuong do intervention | string | `low`, `medium` | Required | `low` |
| package3.interventions[].applicableRiskLevels[] | Muc risk co the ap dung | array<string> | `low`, `medium`, `high` | Required | `["low","medium"]` |
| package3.interventions[].tags[] | Nhan de phan loai/noi suy | array<string> | N/A | Required | `["derivative","review","rules"]` |

## Package 4 - Runtime Config

| Field | Field description | Data type | Enum values | Required | Example value |
|---|---|---|---|---|---|
| package4.version | Version config runtime | string | N/A | Required | `v1.0` |
| package4.created_at | Thoi diem tao config | string | ISO 8601 UTC | Required | `2026-04-13T09:00:00Z` |
| package4.thresholds | Nhom threshold rule | object | N/A | Required | `{...}` |
| package4.thresholds.riskThresholds | Mapping uncertainty -> risk band | object | N/A | Required | `{ low:{...}, medium:{...}, high:{...} }` |
| package4.thresholds.riskThresholds.low | Rule cho risk `low` | object | N/A | Required | `{ "minUncertainty":0.0, "maxUncertainty":0.39 }` |
| package4.thresholds.riskThresholds.low.minUncertainty | Can duoi uncertainty risk low | number | 0.0..1.0 | Required | `0.0` |
| package4.thresholds.riskThresholds.low.maxUncertainty | Can tren uncertainty risk low | number | 0.0..1.0 | Required | `0.39` |
| package4.thresholds.riskThresholds.medium | Rule cho risk `medium` | object | N/A | Required | `{ "minUncertainty":0.4, "maxUncertainty":0.69 }` |
| package4.thresholds.riskThresholds.medium.minUncertainty | Can duoi uncertainty risk medium | number | 0.0..1.0 | Required | `0.4` |
| package4.thresholds.riskThresholds.medium.maxUncertainty | Can tren uncertainty risk medium | number | 0.0..1.0 | Required | `0.69` |
| package4.thresholds.riskThresholds.high | Rule cho risk `high` | object | N/A | Required | `{ "minUncertainty":0.7, "maxUncertainty":1.0 }` |
| package4.thresholds.riskThresholds.high.minUncertainty | Can duoi uncertainty risk high | number | 0.0..1.0 | Required | `0.7` |
| package4.thresholds.riskThresholds.high.maxUncertainty | Can tren uncertainty risk high | number | 0.0..1.0 | Required | `1.0` |
| package4.thresholds.confidenceThresholds | Mapping confidence -> confidence band | object | N/A | Required | `{ low:{...}, medium:{...}, high:{...} }` |
| package4.thresholds.confidenceThresholds.low | Rule confidence `low` | object | N/A | Required | `{ "min":0.0, "max":0.44 }` |
| package4.thresholds.confidenceThresholds.low.min | Can duoi confidence low | number | 0.0..1.0 | Required | `0.0` |
| package4.thresholds.confidenceThresholds.low.max | Can tren confidence low | number | 0.0..1.0 | Required | `0.44` |
| package4.thresholds.confidenceThresholds.medium | Rule confidence `medium` | object | N/A | Required | `{ "min":0.45, "max":0.79 }` |
| package4.thresholds.confidenceThresholds.medium.min | Can duoi confidence medium | number | 0.0..1.0 | Required | `0.45` |
| package4.thresholds.confidenceThresholds.medium.max | Can tren confidence medium | number | 0.0..1.0 | Required | `0.79` |
| package4.thresholds.confidenceThresholds.high | Rule confidence `high` | object | N/A | Required | `{ "min":0.8, "max":1.0 }` |
| package4.thresholds.confidenceThresholds.high.min | Can duoi confidence high | number | 0.0..1.0 | Required | `0.8` |
| package4.thresholds.confidenceThresholds.high.max | Can tren confidence high | number | 0.0..1.0 | Required | `1.0` |
| package4.fallbackRules | Rule fallback theo mode/condition | object | N/A | Required | `{...}` |
| package4.fallbackRules.normal | Fallback intervention cho mode normal | string | interventionId (Package 3) | Required | `INTV_REVIEW_DERIV_RULES` |
| package4.fallbackRules.recovery | Fallback intervention cho mode recovery | string | interventionId (Package 3) | Required | `INTV_RECOVERY_LIGHT_RESTART` |
| package4.fallbackRules.hitl_pending | Fallback intervention cho mode hitl_pending | string | interventionId (Package 3) | Required | `INTV_BREATH_BOX_60S` |
| package4.fallbackRules.missingInterventionPlan | Fallback khi intervention plan bi thieu | string | interventionId (Package 3) | Required | `INTV_RECOVERY_LIGHT_RESTART` |
| package4.hitlConditions | Dieu kien kich hoat HITL | object | N/A | Required | `{...}` |
| package4.hitlConditions.mode | Mode duoc dat khi trigger HITL | string | `hitl_pending` | Required | `hitl_pending` |
| package4.hitlConditions.requiresHITL | Co bat buoc requiresHITL hay khong | boolean | `true` | Required | `true` |
| package4.hitlConditions.uncertaintyHitlThreshold | Nguong uncertainty trigger HITL | number | 0.0..1.0 | Required | `0.7` |
| package4.hitlConditions.confidenceHitlThreshold | Nguong confidence trigger HITL | number | 0.0..1.0 | Required | `0.4` |
| package4.hitlConditions.idleTimeHighSeconds | Nguong idle time cao (giay) | number | integer > 0 | Required | `45` |
| package4.hitlConditions.allowAutoRecoveryWhenHitlUnavailable | Co cho phep auto recovery khi HITL khong kha dung | boolean | `true`, `false` | Required | `true` |

## Ghi chu enum dong bo

- `riskLevel`: `low`, `medium`, `high`
- `mode`: `normal`, `recovery`, `hitl_pending`
- `intervention.type`: `review`, `practice`, `recovery`, `breath`, `grounding`
- Tat ca `interventionId` trong Package 2 phai ton tai trong Package 3.
