# System Architecture & Design

## High-Level Overview
GrowMate backend is an async FastAPI system that orchestrates three domain agents (Academic, Empathy, Strategy) plus a deterministic orchestration engine to choose the next tutoring action.

At runtime, there are two orchestration layers:

1. Pipeline orchestrator layer:
   Owns step execution, state merge, HITL gating, websocket broadcast, and async persistence.
2. Decision engine layer:
   Converts agent states into a normalized embedding, scores actions via deterministic utility rules, and computes uncertainty-based HITL escalation.

The API layer is stateless from HTTP perspective, while session learning state is maintained in process memory and periodically synchronized to Supabase.

## Core Components

1. API Ingress Layer
- Session endpoints:
  Session creation, session interaction, and session metadata updates.
- Orchestrator endpoint:
  Direct single-step orchestration API for explicit orchestration calls.
- Inspection endpoints:
  Expose Bayesian beliefs, particle summary, Q-values, and audit placeholders.
- Config endpoints:
  Config fetch/upload stubs protected by auth dependency.
- WebSockets:
  Behavior stream endpoint and dashboard stream endpoint (global and per session).

2. Runtime Orchestrator Factory
- Builds shared dependencies (state manager, LLM service).
- Builds per-session agent instances to reduce cross-session mutable leakage.
- Caches orchestrator instances by session id.

3. Pipeline Orchestrator
- Accepts session payload and builds a normalized agent input contract.
- Runs academic and empathy processing first, then strategy with merged state.
- Performs empathy payload compatibility checks and particle-filter fallback/reset when unstable.
- Merges all outputs into a single session state object.
- Calls deterministic decision engine and stores orchestration decision in strategy state.
- Applies self-monitor HITL checks.
- Resolves final action with precedence rules.
- Optionally calls LLM service for selected action types.
- Broadcasts dashboard payload and asynchronously schedules Supabase sync.

4. Decision Engine Modules
- State Aggregator:
  Builds embedding features across academic, empathy, and memory dimensions.
- Policy Engine:
  Deterministic utility scoring per action, then softmax action distribution.
- Monitoring Engine:
  Weighted uncertainty blend (academic entropy + empathy uncertainty) and threshold trigger.
- Decision Schema:
  Action, distribution, uncertainty, HITL payload, rationale, monitoring metrics.

5. Domain Agents
- Academic Agent:
  Bayesian belief updates from evidence; entropy used as uncertainty signal.
- Empathy Agent:
  Particle filter over confusion/fatigue with ESS-based uncertainty; derives recommended action and Q-state discretization.
- Strategy Agent:
  Q-learning with epsilon-greedy update, bounded reward shaping, episodic logging cadence, and Q-table upsert cadence.

6. State and Persistence
- Session State:
  Academic state, empathy state, strategy state, HITL pending flag, and step counter.
- In-memory store:
  Fast read/write session state for runtime loop.
- Supabase persistence:
  Learning sessions insert, episodic memory insert, Q-table upsert, and periodic agent-state upsert.
- Websocket dashboard output:
  Consolidated payload including orchestrator decision block.

7. Data Contracts
- Agent input contract:
  Session id, student id, question id, user response, behavior signals, current state.
- Agent output contract:
  Action, payload, confidence, metadata.
- Orchestrator contracts:
  Academic state, empathy state, memory state, aggregated embedding, and final decision.

## Key Architectural Decisions (ADRs)

1. ADR-01: Async-first execution
- Decision:
  Non-blocking request flow with background persistence tasks and websocket push.
- Rationale:
  Preserve low-latency interaction and avoid blocking on database I/O.
- MVP status:
  Implemented.

2. ADR-02: Stateless API, stateful in-process sessions
- Decision:
  Keep session learning context in memory, sync to Supabase periodically.
- Rationale:
  Faster iteration and lower MVP complexity.
- MVP status:
  Implemented with partial durability tradeoff.

3. ADR-03: Dual orchestration model
- Decision:
  Separate pipeline control (step orchestration) from decision logic (aggregator/policy/monitoring).
- Rationale:
  Cleaner modularity and easier future replacement of policy/calibration.
- MVP status:
  Implemented.

4. ADR-04: Deterministic utility policy as primary action selector
- Decision:
  Use rule-weighted deterministic scoring + softmax probability distribution.
- Rationale:
  Explainability and controllability for early-stage deployment.
- MVP status:
  Implemented; RL policy not yet primary final controller.

5. ADR-05: Threshold-based HITL escalation
- Decision:
  Trigger HITL from combined uncertainty and guardrail thresholds (entropy, fatigue, PF collapse, high uncertainty).
- Rationale:
  Safety-first intervention under uncertainty.
- MVP status:
  Implemented at trigger level, incomplete at queue/operational workflow level.

6. ADR-06: Fallback-first resilience
- Decision:
  Multiple fallback layers (legacy route fallback, PF fallback/reset, safe strategy action, LLM fallback output).
- Rationale:
  Keep session progression alive despite component instability.
- MVP status:
  Implemented.

7. ADR-07: Config-driven policy and thresholds
- Decision:
  Use YAML for action spaces, utility weights, and uncertainty thresholds.
- Rationale:
  Decouple tuning from code changes.
- MVP status:
  Implemented with several placeholders.

8. ADR-08: Session-scoped orchestrator instances with shared infra
- Decision:
  Session-specific agents, shared state manager and LLM service.
- Rationale:
  Balance isolation and resource reuse.
- MVP status:
  Implemented.

9. ADR-09: Transparent inspection endpoints
- Decision:
  Provide direct state introspection endpoints for beliefs, particles, and Q-values.
- Rationale:
  Auditability and debugging visibility.
- MVP status:
  Implemented.

10. ADR-10: Security dependency scaffolded with mock decoding
- Decision:
  Keep auth dependency in place but return mock user claims.
- Rationale:
  Unblock development before full JWT verification rollout.
- MVP status:
  Implemented as scaffold.

## Workflows & Data Flow (Include Mermaid.js syntax for complex flows)

### Primary Interaction Workflow
    flowchart TD
      A[Client POST interact or orchestrator step] --> B[Auth dependency resolves user]
      B --> C[Get session orchestrator instance]
      C --> D[Load or init SessionState]
      D --> E[Build AgentInput with current state and behavior signals]
      E --> F[Academic Agent process]
      E --> G[Empathy Agent process]
      G --> H{Empathy payload valid PF shape?}
      H -->|No| I[Run dedicated ParticleFilter fallback]
      H -->|Yes| J[Use empathy output]
      I --> K{PF unstable values?}
      J --> K
      K -->|Yes| L[Reset PF and reprocess]
      K -->|No| M[Merge academic and empathy into state]
      L --> M
      M --> N[Strategy Agent process with merged state]
      N --> O[Merge strategy output and increment step]
      O --> P[Decision Engine run_step]
      P --> Q[Aggregator builds embedding]
      Q --> R[Policy scores actions + softmax]
      R --> S[Monitoring computes total uncertainty]
      S --> T{HITL triggered by engine or guardrails?}
      T -->|Yes| U[Set hitl_pending]
      T -->|No| V[Continue]
      U --> W[Resolve action priority]
      V --> W
      W --> X{Action requires LLM text?}
      X -->|Yes| Y[LLM generate with fallback]
      X -->|No| Z[Empty action payload]
      Y --> AA[Format dashboard payload]
      Z --> AA
      AA --> AB[Broadcast dashboard websocket]
      AB --> AC[Schedule async Supabase sync]
      AC --> AD[Return interaction response]

### Session Creation Workflow
    flowchart LR
      A[POST create session] --> B[Generate session id]
      B --> C[Insert learning_sessions row]
      C --> D[Initialize in-memory session state]
      D --> E[Return session metadata]

### State Model Progression
1. Input state:
   SessionState carries academic_state, empathy_state, strategy_state, hitl_pending, step.
2. Agent update stage:
   Academic and empathy write domain estimates; strategy consumes merged state and writes policy artifacts.
3. Orchestration stage:
   Decision engine transforms to typed Academic/Empathy/Memory states, then AggregatedState embedding, then OrchestratorDecision.
4. Output stage:
   Final action + dashboard payload + optional LLM text + async persistence side effects.

## Known Limitations & Phase 2 Planning

1. HITL operational workflow is incomplete
- Current:
  HITL trigger function is still a stub and does not push to queue or notify operators.
- Phase 2:
  Implement durable HITL queue, timeout policies, and operator resolution endpoint with acknowledgment semantics.

2. LLM augmentation is scaffolded only
- Current:
  Prompt builder and fallback template methods return empty strings; LLM service currently returns a mocked fallback response.
- Phase 2:
  Add production LLM provider integration, prompt templates, timeout budgets, and action-specific generation policies.

3. Behavior websocket path is out of sync with particle filter API
- Current:
  Behavior stream handler calls incompatible particle filter methods/signatures, creating runtime risk if used.
- Phase 2:
  Align telemetry ingestion with current empathy agent interfaces and add websocket integration tests.

4. State durability is eventual and partial
- Current:
  Session state source of truth is in memory, with periodic async sync every three steps.
- Phase 2:
  Add durable state rehydration, stronger retry/backoff policies, and optional Redis/session store for horizontal scaling.

5. Persistence schema alignment gap
- Current:
  Runtime sync writes to an agent_state table, but schema definition set centers on learning_sessions, episodic_memory, q_table, and audit_logs.
- Phase 2:
  Add explicit migration for agent_state or refactor sync target to existing canonical tables.

6. Deterministic policy dominates final actioning
- Current:
  Q-learning updates and persistence run, but orchestrator policy remains deterministic utility-driven for final selection.
- Phase 2:
  Introduce RL-informed policy blending, offline evaluation guardrails, and policy gating strategy.

7. Confidence calibration remains threshold-based
- Current:
  Uncertainty and escalation are threshold/weight driven; no calibration model is used.
- Phase 2:
  Add calibration module (for example temperature scaling or isotonic mapping) and monitor calibration drift.

8. HTN execution remains mostly placeholder
- Current:
  Primitive handlers are stubs and planner traversal is minimal/mock-like.
- Phase 2:
  Implement real primitive integrations, richer method selection, and tighter coupling to question/hint services.

9. Security is mocked at identity-claim level
- Current:
  Auth dependency returns mock user payload rather than verified JWT claims.
- Phase 2:
  Integrate real token verification and role-based authorization for config and inspection writes.

10. API surface has compatibility duplication
- Current:
  Session router is mounted under multiple prefixes for compatibility.
- Phase 2:
  Consolidate route topology and version contracts to reduce ambiguity.