# Agentic Incident Fallback Runbook

## Scope
Use this runbook when agentic reasoning causes degraded behavior, elevated latency, or error spikes.

## Trigger Conditions
- Elevated 5xx rate on orchestrator step endpoint.
- Reasoning timeout errors spike.
- Unexpected action quality regression after deployment.
- External dependency instability (LLM provider or vector retrieval path).

## Immediate Mitigation
1. Disable agentic reasoning at runtime:
   - Set environment variable `USE_LLM_REASONING=false`.
2. Roll restart backend instances so the setting is effective.
3. Verify new requests return `reasoning_mode=adaptive`.

## Verification Checklist
1. Send a canary request to orchestrator step endpoint.
2. Confirm response includes normal action payload and no agentic-only dependency failures.
3. Confirm fallback/adaptive path remains healthy in logs.
4. Confirm error rate and p95 return to baseline.

## Suggested Validation Commands
- Health check from backend root:
  - `python -m pytest tests/test_orchestrator/test_phase3_behaviors.py tests/test_orchestrator/test_data_driven_payload.py`
- Agentic fallback checks:
  - `python -m pytest tests/test_orchestrator/test_agentic_mode.py`

## Roll Forward Procedure
1. Investigate logs for timeout/tool errors.
2. Fix and deploy to staging.
3. Re-enable with controlled rollout by cohort/percentage.
4. Monitor `reasoning_mode`, `llm_steps`, `tool_count`, and `fallback_used` metrics.

## Ownership
- Primary: Backend on-call engineer.
- Secondary: Platform/infra owner for deployment and environment config.
