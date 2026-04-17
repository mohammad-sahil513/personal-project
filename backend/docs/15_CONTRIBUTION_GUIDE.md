# 15 - Contribution Guide

This guide defines how to contribute safely and consistently to the backend.

---

## 1) Branching and PR Flow

- Create feature/fix branches from your main development branch.
- Keep PRs scoped to one logical change.
- Include documentation updates when behavior or API changes.
- Add or update tests for changed behavior.

Recommended branch naming:
- `feature/<short-description>`
- `fix/<short-description>`
- `docs/<short-description>`

---

## 2) Coding Standards

- Keep layer boundaries clear:
  - routes are thin (no business logic)
  - orchestration in application services
  - persistence through repositories
  - cloud SDK calls through infrastructure adapters
- Prefer explicit DTO/contract usage between layers.
- Use clear error classes from `core/exceptions.py`.
- Keep logging structured and include request/workflow IDs when available.

---

## 3) Testing Expectations

For any non-trivial change:

1. Add/update unit tests near changed logic.
2. Add/update integration tests when flow behavior changes.
3. Verify no regressions in related module test suites.

Reference:
- `09_TESTS_DOCUMENTATION.md`

---

## 4) Documentation Expectations

Update docs when changing:

- API endpoints/contracts
- workflow stages or order
- module boundaries
- configuration keys or operational behavior
- prompts used in generation/template flows

Minimum required update targets:
- `05_STAGE_AND_API_REFERENCE.md`
- `13_API_EXAMPLES.md` (if API payloads changed)
- related module/file catalog docs

---

## 5) Prompt and Model Changes

When modifying prompt files:

- document intent and expected output change
- keep fallback/default prompt behavior stable
- validate with relevant integration tests
- mention prompt file names in PR description

Reference:
- `10_PROMPTS_DOCUMENTATION.md`

---

## 6) Configuration and Secrets Policy

- Never commit real secrets.
- Keep `.env.example` aligned with required settings.
- Validate config changes against readiness endpoint.
- Document new settings in `12_CONFIG_AND_PRICING_REFERENCE.md`.

---

## 7) API Change Policy

Before changing endpoint behavior:

- evaluate backward compatibility impact
- update schemas and examples
- update route docs and stage mapping docs
- include migration guidance for consumers if breaking

---

## 8) Suggested PR Checklist

- [ ] Code follows layer boundaries.
- [ ] Unit/integration tests updated and passing.
- [ ] Logs and error handling included.
- [ ] Docs updated for behavior/API/config changes.
- [ ] No secrets or environment-specific artifacts committed.
- [ ] PR description includes "what changed" and "why".

---

## 9) Review Focus Areas

Reviewers should prioritize:

- behavioral correctness
- stage/state transition safety
- API contract stability
- error propagation and observability quality
- test sufficiency around changed logic
