# Capability classification matrix (plan §12)

Current-state version, updated as work completes per plan rule: the agent
MUST keep `docs/capability-matrix.md` accurate as work completes and
downgrade any claim that is not actually delivered.

Classifications follow the plan: **OOTB** (working in the delivered
platform without customer-specific development), **Configuration**
(per-client tuning), **Custom Development** (adapter/mapping work),
**Third-Party Component** (external product), **Roadmap / Future**,
**Not Supported**.

| Capability | Classification | Current state |
|---|---|---|
| Strategy / OKRs, demand & idea management | OOTB | Delivered in Phase 1. |
| Portfolio / program / project / milestone / task / commitment management | OOTB | Delivered in Phase 1. |
| Governance workflows | OOTB engine · **Configuration** per client workflow | Workflow definitions are configuration. |
| Benefits realisation tracking | OOTB | KPI feeds from client systems are Configuration. |
| Enterprise Work Graph | OOTB | Relational graph; graph-DB migration is Roadmap if scale demands. |
| AI extraction from meetings/emails/documents | OOTB (with simulator) · **Configuration** for a live M365 tenant | Live Graph permissions and consent are tenant-specific. |
| Owner/due-date recommendation, classification | OOTB · Configuration (taxonomy) | |
| Duplicate/related detection and linking | OOTB · Third-Party (local embedding model) | Thresholds are Configuration. |
| LLM inference | **Third-Party Component** (Groq) | Provider swappable via `LLMClient`; data-residency decision required. |
| Speech-to-text for raw audio | Third-Party Component (Groq Whisper) | Graph VTT transcripts preferred. |
| Prioritisation scoring and override | OOTB · Configuration (criteria/weights) | |
| Resource & capacity management, what-if | OOTB | |
| Optimiser | OOTB · Third-Party (OR-Tools) | |
| Predictive risk (Monte Carlo, delay model) | OOTB · **Configuration** (calibration to client history) | Demo model v1 is linear logistic regression; GBDT/SHAP drivers, calibration wrapper, synthetic-history generator and real SHAP are Phase 7 T7.3 follow-ups. |
| Primavera P6 integration | Demo: simulator. Live: **Configuration/Custom Development** | Depends on client P6 version and API exposure. |
| Maintenance/EAM, ERP, HR integration | Demo: simulators. Live: **Custom Development** (adapter + mapping) | Connector SDK minimises effort. |
| Microsoft 365 (Teams/Outlook/SharePoint) | OOTB connector · Configuration (tenant, scopes, allow-lists) | Live adapter pending tenant registration (live adapters raise `NotImplementedError` by design — Phase 3 T3.4). |
| SSO / MFA | **Third-Party Component** (Keycloak / Entra ID) | Configuration. |
| RBAC, SoD, audit trail, data governance | OOTB · Configuration (roles, rules) | |
| Human-in-the-loop AI governance, prompt registry, evals | OOTB | |
| Executive dashboards, "Ask EIL", executive brief | OOTB | Dashboard (Phase 8 T8.2); executive brief service + `GET /executive/brief` endpoint (Phase 8 T8.4, 2026-11-22); "Ask EIL" v1 — chat UI at `/assistant` (Phase 8 T8.3). Streaming and conversation logging — T8.3 follow-ups. |
| Write-back to systems of record | Framework OOTB (off by default); per-system actions **Custom Development** | One reference write-back only. |
| Native Teams app/bot, Outlook add-in | **Roadmap** | |
| Mobile apps | **Roadmap** (responsive web in scope) | |
| Private/on-prem LLM hosting | **Roadmap** | Requires provider decision. |
| CDC / real-time streaming from ERP/EAM | **Roadmap** | Polling + webhooks in scope; webhook target endpoint not yet exposed by the API (Phase 3 T3.3 limitation). |
| Arabic UI and Arabic-language extraction | OOTB (UI/RTL) · Extraction quality validated on eval set | Arabic NER for PII is limited (documented). |
| Multi-tenant SaaS operation | **Not Supported** (single-tenant deployment) | |
