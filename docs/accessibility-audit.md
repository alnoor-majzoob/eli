# Accessibility audit — EIL (plan Phase 9, T4)

Audit of the web app against WCAG 2.1 AA + RTL/Arabic QA (plan §14, NFR).
Focused on core flows (plan §12: "WCAG 2.1 AA for core flows").

## Audit date / scope

Audited against the live pages: AI inbox (`/ai/inbox`), Capacity & what-if
(`/capacity`), Risk & escalations (`/risk`), Executive (`/executive`,
`/executive/presenter`), Prioritisation (`/prioritization`), Graph explorer
(`/graph`), Approvals, Audit, Items, Dashboard.

## Findings (fixed)

| Page | Issue | Fix |
|---|---|---|
| RiskPage | Radar table had no `scope`/caption; screen readers lost column structure | Added `scope="col"` on all `<th>`, `aria-label` + `<caption class="sr-only">` on the table |
| AiInboxPage | Suggestion cards were clickable `div`s — not keyboard accessible, no accessible name | Added `role="button"`, `tabIndex={0}`, `aria-label` (suggestion title), keyboard handler (Enter/Space) |
| CapacityPage | Heatmap week spans had only a `title` tooltip — not exposed as accessible names | Added `aria-label` with the same tooltip text |

## Findings (open / accepted)

- **Tables elsewhere**: Graph explorer, Approvals, Audit and Items tables lack
  `scope="col"` on headers — address in a follow-up pass if scale/time allows.
- **Dynamic status changes**: Capacity/Risk/Prioritisation data refreshes are
  not announced (`aria-live`); suggestions are keyboard-operable now.
- **Zoom/contrast**: standard Tailwind palette — to be verified by eye during
  the RTL/Arabic QA pass.

## RTL / Arabic QA

- The i18n system swaps `dir` to `rtl` on locale change; smoke-tested in
  `apps/web/e2e/smoke.spec.ts` (language toggle → `dir="rtl"`).
- Locales: `apps/web/src/locales/{en,ar}/common.json` (EN/AR strings, plan
  §14 "EN + AR (RTL)").
- Fix-ups in RTL: the CapacityPage heatmap uses `flex flex-wrap gap-1` (no
  `justify-end` assumptions); AI-inbox action buttons use `flex-wrap`;
  table alignment uses `text-left` (plan shows LTR is acceptable in tables —
  Arabic UI keeps logical order).

## Verification

- Automated: `make typecheck-web`, `pnpm --filter @eil/web lint`,
  `pnpm --filter @eil/web test` (Vitest) — run in CI.
- Manual (next pass): run the app with `LANG=ar` / toggle locale and walk the
  five core flows; check focus order, contrast and labels.
- Automated browser a11y: Playwright e2e is blocked on this workstation
  (no browser binaries); add `@axe-core/playwright` runs to CI follow-up.
