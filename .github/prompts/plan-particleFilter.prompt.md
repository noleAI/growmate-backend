## Plan: Implement Empathy Particle Filter End-to-End

Implement a production-ready Particle Filter for the empathy agent using the PF guideline, then wire it into orchestrator state flow, dashboard payload shaping, and tests. The recommended path is to land PF core first, then integration and verification in phases so each phase is independently testable and low-risk.

**Steps**
1. Phase 1: Align dependencies and configuration contract.
2. Update /home/pbkhang404/Documents/growmate-backend/backend/requirements.txt and /home/pbkhang404/Documents/growmate-backend/backend/pyproject.toml to include NumPy and YAML dependency support used by PF implementation and config loading.
3. Normalize empathy PF configuration in /home/pbkhang404/Documents/growmate-backend/backend/configs/agents.yaml to include n_particles, process_noise, jitter_sigma, ess_threshold_ratio, state_dimensions, state_bounds, and keep resampling_strategy. This step blocks PF class initialization consistency.
4. Phase 2: Implement PF core and likelihood template.
5. Rewrite /home/pbkhang404/Documents/growmate-backend/backend/agents/empathy_agent/particle_filter.py with a vectorized NumPy implementation: PFState model, predict, update with log-weight stabilization, should_resample, systematic resample with jitter, get_state, discretize_for_q, reset, and robust fallback handling with structured logging. This is foundational and blocks later steps.
6. Add /home/pbkhang404/Documents/growmate-backend/backend/agents/empathy_agent/likelihood.py with a simple placeholder Gaussian log-likelihood based on behavior signals, designed as a replaceable function for future domain rules.
7. Export PF symbols from /home/pbkhang404/Documents/growmate-backend/backend/agents/empathy_agent/__init__.py for clean imports.
8. Phase 3: Integrate PF into runtime pipeline.
9. Integrate PF lifecycle into /home/pbkhang404/Documents/growmate-backend/backend/agents/orchestrator.py: instantiate PF from config in constructor, run predict-update-resample each session step, push PFState into state.empathy_state, provide discretized key for strategy usage, and add self-monitor ESS collapse detection tied to configured threshold.
10. Extend /home/pbkhang404/Documents/growmate-backend/backend/core/payload_formatter.py to produce PF-ready empathy payload fields (estimation, particle_cloud, weights, ess, step) while preserving existing dashboard envelope.
11. Update /home/pbkhang404/Documents/growmate-backend/backend/core/state_manager.py sync payload mapping to persist full PF fields (particle_cloud, weights, ess, uncertainty) instead of particles-only shape so runtime and persistence stay consistent. Depends on steps 5 and 9.
12. Phase 4: Test coverage and validation.
13. Add /home/pbkhang404/Documents/growmate-backend/backend/tests/test_empathy/test_particle_filter.py covering initialization bounds, predict clipping, weighted update behavior, ESS trigger, resampling stability, discretization logic, NaN/fallback behavior, and reset behavior.
14. Add or extend orchestrator-focused async tests under /home/pbkhang404/Documents/growmate-backend/backend/tests to verify PF integration path updates empathy_state and self-monitor behavior without external I/O. Parallel with step 13 after step 9.
15. Run focused tests first, then broader suite and lint checks; tune thresholds/assertions for determinism with seeded randomness.

**Relevant files**
- /home/pbkhang404/Documents/growmate-backend/backend/agents/empathy_agent/particle_filter.py - Replace current stub implementation with full PF algorithm and agent-compatible process flow.
- /home/pbkhang404/Documents/growmate-backend/backend/agents/empathy_agent/likelihood.py - Add default Gaussian log-likelihood placeholder.
- /home/pbkhang404/Documents/growmate-backend/backend/agents/empathy_agent/__init__.py - Export ParticleFilter and PFState.
- /home/pbkhang404/Documents/growmate-backend/backend/configs/agents.yaml - Finalize PF config keys and defaults.
- /home/pbkhang404/Documents/growmate-backend/backend/agents/orchestrator.py - Wire PF cycle into run_session_step and self-monitor.
- /home/pbkhang404/Documents/growmate-backend/backend/core/payload_formatter.py - Add PF-specific dashboard formatting helper.
- /home/pbkhang404/Documents/growmate-backend/backend/core/state_manager.py - Persist full PF state shape.
- /home/pbkhang404/Documents/growmate-backend/backend/requirements.txt - Add runtime deps.
- /home/pbkhang404/Documents/growmate-backend/backend/pyproject.toml - Add dev dependency alignment.
- /home/pbkhang404/Documents/growmate-backend/backend/tests/test_empathy/test_particle_filter.py - New PF unit tests.
- /home/pbkhang404/Documents/growmate-backend/backend/tests - Add PF-orchestrator integration tests in existing structure.

**Verification**
1. Run targeted PF tests: pytest backend/tests/test_empathy/test_particle_filter.py -q.
2. Run orchestrator-related tests: pytest backend/tests -k "orchestrator or empathy or particle" -q.
3. Run full backend tests: pytest backend/tests -q.
4. Run lint: ruff check backend.
5. Manual sanity check with one synthetic session step to confirm empathy_state contains confusion, fatigue, uncertainty, ess, particle_cloud, and weights, and dashboard payload includes these fields.

**Decisions**
- Approved scope is full integration, not PF module only.
- Likelihood implementation will start with a simple placeholder Gaussian and remain replaceable.
- Supabase/state sync should move to full PF fields, not particles-only.
- Included scope: empathy PF core, orchestrator runtime wiring, payload formatting, state persistence mapping, and tests.
- Excluded scope: rewriting legacy API route business flow in backend/api/routes/session.py unless PF integration explicitly requires endpoint-level rerouting.

**Further Considerations**
1. For deterministic tests, seed NumPy RNG inside test fixtures and avoid brittle exact-value assertions.
2. Keep numerical stability guardrails strict in update: max-shifted log weights, epsilon floor, uniform fallback.
3. Maintain backward-compatible empathy_state keys only if existing consumers are found during implementation; otherwise keep PF schema clean and explicit.