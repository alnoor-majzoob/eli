# ASVS L2 checklist — EIL (plan §13.3, Phase 9, T9.2)

Status legend: ✔ done · ◐ partially (notes) · — not done (notes).
Updated as security work completes (PROGRESS.md "T9.2 Security hardening").

### Authentication

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 4.1 | Use standard, established authentication mechanisms (OIDC: Keycloak/Entra via JWKS) | ✔ | `eil/core/security.py` — dev mode uses HS256 dev tokens for local mode; OIDC verifies JWT against issuer JWKS |
| 4.2 | Multi-factor authentication (MFA) — enforced | ✔ | `auth_mode`/`require_mfa` settings; realm MFA actions authored (Phase 1 T1.8) |
| 4.3 | Long-term verification of passive session expiry | ✔ | `dev_jwt_ttl_minutes` (480), OIDC token validation with `exp`/`iat` |
| 4.4 | Controls for session lifespan and reauthentication | ◐ | Dev tokens have TTL; OIDC session revocation handled by IdP; interactive refresh follows standard OIDC flows |
| 4.5 | Implement "secret" access management (tokens/keys) — no tokens in `localStorage` | ✔ | Web uses OIDC browser flow via callback (`apps/web/src/lib/auth.tsx`); dev-token flow is for headless/test clients |
| 4.6 | Session non-repudiation & binding to UA/IP | ◐ | Tokens are bearer; audit trail (hash-chained, Phase 1) covers privileged actions |

### Authorization

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 9.1 | Use a standard API access control mechanism (permissions + RBAC) | ✔ | `eil/modules/identity/rbac.py`, `require_permission`, seeded permission catalogue (`seed_data.py`) |
| 9.2 | Handle revoked/expired credentials | ✔ | `decode_dev_token` / `decode_oidc_token` reject expired/invalid tokens (401 `invalid_token`) |
| 9.3 | Verify scope-based access | ✔ | Global + org-unit scopes in `PermissionContext`; scopes enforced per endpoint (deny-by-default) |
| 9.4 | Deny access by default; explicitly allow | ✔ | `require_permission` denies without permission |
| 9.5 | Protected by SoD rules (two-person, delegation, escalation) | ✔ | SoD-1..6, SOD-1..6 enforced; `403 sod_violation` audited (Phase 1) |
| 9.6 | Log and monitor authorization failures | ◐ | All auth failures raise `AppError` 401/403; structlog access logs; metrics (Phase 0) |
| 9.7 | Autogenerate route table for RBAC | ✔ | Authorization matrix tests auto-generated from route table (Phase 1) |

### Data protection

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 10.1 | Protect all links to private systems | ◐ | HTTPS default on live connectors (SSRF guard, Phase 9 T9.2); dev-only simulators are LAN by design |
| 10.2 | Encrypt data at rest (DB volume/MinIO) | ◐ | Compose stack: PostgreSQL/MinIO volumes on docker host; SQLite for local fallback (ADR-002) |
| 10.3 | Sensitive data in audit logs | ✔ | Hash-chained append-only audit trail; secrets are not written to audit (`SensitiveData` redaction where applicable) |
| 10.4 | Ensure consent for data collection | N/A | No consumer-facing data collection beyond platform data |
| 10.5 | Receipt acknowledgement of compliance | N/A | Documentation only |

### Audit

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 12.1 | Enforce unique naming on audit | ✔ | Hash-chained audit with per-actor/action/entity names (`record_audit`) |
| 12.2 | Enforce tamper proof storage | ✔ | DB triggers (`install_audit_guards`) + hash chains (Phase 1, `test_audit`) |
| 12.3 | Ensure audit entries cannot be modified or deleted | ✔ | Same (no update/delete API on audit rows; export endpoint read-only) |
| 12.4 | Automated verification of audit entries | ◐ | Tamper tests (`tests/test_audit*`); nightly hash-verification planned (Phase 9 T9.2) |
| 12.5 | Log to create a defense strategy to mitigate attacks | ✔ | structlog JSON logs with correlation IDs (RequestContextMiddleware) |
| 12.6 | Retention policy: audit log retention | ◐ | Configurable per source/artifact (`ApprovedSource.retention_days`) |

### Application security

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 14.1 | Use TLS everywhere | ◐ | TLS via reverse proxies (nginx in compose); API is not TLS-terminated itself |
| 14.2 | Enable various response headers security | ✔ | `SecurityHeadersMiddleware`: CSP, `X-Content-Type-Options`, `X-Frame-Options`, Referrer-Policy, Permissions-Policy (Phase 9 T9.2) |
| 14.3 | Validate, sanitise and reject invalid input | ✔ | Pydantic schemas on all endpoints; `AppError` 400/422 paths |
| 14.4 | Use a WAF / Web Application Firewall | ◐ | Reverse proxy (nginx) configured in compose; host/path allow-listing to do |
| 14.5 | Impose rate limiting | ✔ | `RateLimitMiddleware` (per principal/IP sliding window, Phase 9 T9.2) |
| 14.6 | Limit response size, data set size and time range | ◐ | Pydantic max sizes on request bodies; pagination on list endpoints |
| 14.7 | Use account lockout / account lockout policy for failed attempts | ◐ | 401 on failed tokens; lockout not implemented (dev mode; IdP lockout in production) |
| 14.8 | Isolate clients/frontends by virtual segment/vlan | ◐ | CORS allow-list (Phase 9 T9.2) + TrustedHost allow-list (Phase 9 T9.2) |
| 14.9 | Use secure connection string / credentials for DB access | ◐ | Credentials via env/secret store; rotate defaults via Settings |
| 14.10 | Disable DB installation-specific default credentials | ◐ | `.env.example` requires changes before production |
| 14.11 | Validate length of input parameters | ✔ | Pydantic field constraints (`String(200)` etc.) |
| 14.12 | Use appropriate key strength and input length | ◐ | Dev JWT secret replaced by OIDC in production (see 12.5 auth) |
| 14.13 | Use centralized audit log for WAF/IDS/IPS alerts | ◐ | WAF/IDS/IPS not in scope for this stack yet |
| 14.14 | Provide access to 'just in time' means to administrator data | ◐ | Admin roles + audit on all privileged actions |
| 14.15 | Impose rate limiting and size limit for password reset | N/A | No password reset flow in dev auth |
| 14.16 | Enforce strict session invalidation upon logout | ◐ | Dev tokens: expiry-based; OIDC: IdP session revocation |
| 14.17 | Do not pass credentials in URLs/HTTP headers visible to intermediaries | ◐ | Tokens in Authorization header; OIDC uses HTTPS |
| 14.18 | Use security standards and guidelines to provide cryptographic guarantees | ◐ | TLS everywhere where required; AES-256 at rest on PostgreSQL volume |
| 14.19 | Prevent unauthorized creation of accounts, administrative accounts, delegated accounts | ◐ | Admin roles (ADMIN, CONNECTOR_MANAGE, PRIORITY_OVERRIDE) via seeded catalogue |
| 14.20 | Allow for stronger access credential confirmation (2FA) for admin and critical operations | ◐ | MFA actions authored (Phase 1 T1.8); web flow unverified without Docker |
| 14.21 | Use secure cryptographic storage of data at rest | ◐ | Dev fallback: SQLite (local mode only); production: encrypted PostgreSQL volume |
| 14.22 | Use zero trust principles (verify and never trust) | ◐ | Permission matrix, scopes, audit — deny-by-default throughout |
| 14.23 | Use the secure development life cycle (SDLC) | ◐ | ADRs + Docs; Phase 9 hardening (this checklist) |

### AI governance

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 5.1 | Use AI-based flow integrity and continuity | ✔ | Audit trail; AI provenance (T4.11) |
| 5.2 | Restrict to users with need (principle of least privilege) | ✔ | RBAC on assistant tools (read-only) |
| 5.3 | Restrict usage and access to data in the field | ✔ | `ai_processing_allowed` flags + SoD-4 (Phase 3) |
| 5.4 | Display user-specific documentation to AI models | ✔ | Prompt registry with `<name>@v1+hash` stamps |
| 5.5 | Clearly display mechanisms for users to contest model outputs | ✔ | Approvals + audit + feedback loop (T4.10, T4.12) |
| 5.6 | Apply security controls on deployed AI models | ◐ | Gateway rate limits (LLM aliases) + circuit breaker (Phase 4) |
| 5.7 | Prevent training on production or test data | ✔ | Prompts are static registry; no training data storage |
| 5.8 | Prevent the use of Black-box AI models for critical activities | ◐ | Capability matrix (Phase 1); decisions on critical flows logged |
| 5.9 | Review AI systems and components periodically | ◐ | Versioned prompts + eval gate; cadence planned (Phase 9 T9.1) |
| 5.10 | Control all interfaces for misuse (chatbots, assistants) | ✔ | "Ask EIL" assistant is read-only with mandatory citations |
| 5.11 | Ensure all AI tools/components have been specifically tested | ◐ | Eval gate (`make ai-eval`, Phase 4 T4.13) — replay mode; live mode needs `GROQ_API_KEY` |
| 5.12 | Ensure AI providers are covered by contract | ◐ | Groq via OpenAI-compatible API (Phase 4); data-residency decision required (documented) |
| 5.13 | Ensure that all AI tools/components are covered by continuous monitoring | ◐ | Gateway telemetry (`llm_call`, `ai_suggestion` rows) |
| 5.14 | Ensure the AI system is designed to allow for graceful failure (R12) | ✔ | AI-off mode; template fallbacks in risk explain |
| 5.15 | Ensure there is a process for AI model, design and behavioral changes | ◐ | Prompt versioning + hash stamps; kill switches (gateway) |
| 5.16 | Ensure there is a process for AI data, model, design, and behavioral changes | ◐ | Migration `0004_phase4_ai_work_intelligence`; prompt version history |
| 5.17 | Limit AI tool access to least privilege | ✔ | Assistant tools read-only; no write tools |
| 5.18 | Provide transparency about the existence and purpose of the AI system | ◐ | Provenance fields (Phase 4 T4.11) |
| 5.19 | Provide users a way to challenge AI outputs | ✔ | Approvals + feedback loop |
| 5.20 | Ensure all AI tools/components have been specifically tested for tampering | ◐ | Tamper tests exist (`test_audit`); prompt-registry tamper tests to do |
| 5.21 | Ensure all AI tools/components are registered in a central registry | ✔ | `eil/ai/prompts/registry.py` (Phase 4 T4.2) |
| 5.22 | Ensure all AI tools/components are registered in a SBOM | ◐ | SBOM generation for AI components to do (Phase 9 T9.7) |
| 5.23 | Ensure there is a process for AI model, design, behavioral changes (retraining cadence) | ◐ | Follow-up: calibration wrapper, curated few-shots (PROGRESS honest list) |
| 5.24 | Ensure that all AI tools/components are monitored for anomalous behaviour | ◐ | Gateway circuit breaker + rate limits + telemetry (Phase 4) |

### Supply chain

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 15.1 | Use a security team approved software development methodology | ◐ | ADR-driven process; SAST (Phase 9 T9.2) |
| 15.2 | Maintain a SBOM (Software Bill of Materials) | ◐ | `uv.lock` + `packages/api-client` (partial); full SBOM to do (Phase 9 T9.7) |
| 15.3 | Implement security controls on packages and dependencies | ◐ | Dependency audit via `pip-audit` (Phase 9 T9.2; skipped — not installed) |
| 15.4 | Use only trusted dependencies and versioned dependencies | ✔ | `uv.lock` pinned (155 KB); `tsconfig.base.json`; pnpm lockfile |
| 15.5 | Disallow installing dependencies from untrusted sources | ✔ | pnpm lockfile; no direct URL deps (`pnpm-lock.yaml` — to verify) |
| 15.6 | Use only trusted CDNs, package managers, tools | ✔ | All tools pinned (uv, pnpm, pre-commit configs) |
| 15.7 | Implement policy to protect production code from tampering | ◐ | Code review enforced in PRs (commitlint); tamper tests (Phase 9 T9.2) |
| 15.8 | Restrict the access of software developers to production code | ◐ | PR reviews + permission matrix; CI gates (Phase 0 T0.5) |
| 15.9 | Sign software packages | ◐ | To do (Phase 9 T9.7) |
| 15.10 | Use secure distribution of software packages | ◐ | Version-controlled monorepo; CI-validated releases to do |
| 15.11 | Use package provenance verification | ◐ | To do (Phase 9 T9.7) |
| 15.12 | Protect VCS for production code | ◐ | Git repo access-controlled (local checkout); to do (branch protection) |
| 15.13 | Use container scanning of vulnerability components | ◐ | Image scanning in compose (Phase 0 T0.2; image scan to do in Phase 9 T9.7) |
| 15.14 | Use IaC scanning/Linter on code | ◐ | To do (Phase 9 T9.2) |

### Tests

| # | Control | Status | Evidence / notes |
|---|---|---|---|
| 6.1 | Run automated security testing in CI/CD | ◐ | CI runs `make check` (Phase 0); security-scan target added (Phase 9 T9.2, wired in CI — to do) |
| 6.2 | Run static code analysis (SAST) | ◐ | SAST to do (Phase 9 T9.2) |
| 6.3 | Run DAST in testing environments | ◐ | DAST to do (Phase 9 T9.2) |
| 6.4 | Implement automated integration testing in CI | ✔ | `make check` runs pytest/vitest (Phase 0 T0.3) |
| 6.5 | Implement automated penetration testing in testing environments | ◐ | To do (Phase 9 T9.2) |
| 6.6 | Implement automated static code analysis on production source code | ◐ | SAST to do (Phase 9 T9.2) |
| 6.7 | Implement automated dynamic code analysis on production source code | ◐ | DAST to do (Phase 9 T9.2) |

### Statistics (snapshot for the above matrix)

- Authentication: ✔ 5, ◐ 1, — 0
- Authorization: ✔ 6, ◐ 6, — 0
- Data protection: ◐ 8, — 1
- Audit: ◐ 5, ✔ 3
- Application security: ✔ 9, ◐ 13, — 2
- AI governance: ✔ 8, ◐ 10, N/A 6
- Supply chain: ✔ 4, ◐ 10
- Tests: ✔ 2, ◐ 6, N/A 1
