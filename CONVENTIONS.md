# Coding Conventions — Intelligent Analyst

**Date**: 2026-03-21

---

## Python (Backend: ia-api, ia-worker)

### Style
- Python 3.11+
- Formatter: `black` (line length 100)
- Linter: `ruff`
- Type checker: `mypy` (strict mode)
- All functions must have type annotations (parameters and return types)
- All public functions must have docstrings (Google style)

### Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/methods: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`

### Imports
- Standard library first, then third-party, then local
- No wildcard imports (`from x import *`)
- No circular imports

### Error Handling
- All exceptions must be caught at the appropriate boundary (route handler, middleware, or worker entry point)
- Never catch bare `Exception` without re-raising or logging
- Business logic errors: raise custom exceptions (defined in `exceptions.py` per module)
- Custom exceptions carry structured context (error_code, message, details)
- Log errors with correlation_id and tenant_id

### Async
- All I/O operations must be async (`async def`, `await`)
- No blocking calls in async contexts (use `asyncio.to_thread` for CPU-bound work)
- Database clients: use async Firestore client

---

## TypeScript (Frontend: ia-web)

### Style
- TypeScript strict mode
- Formatter: `prettier`
- Linter: `eslint` with recommended rules
- React: functional components with hooks (no class components)

### Naming
- Files: `kebab-case.tsx` for components, `camelCase.ts` for utilities
- Components: `PascalCase`
- Functions/hooks: `camelCase`
- Constants: `UPPER_SNAKE_CASE`
- Types/interfaces: `PascalCase`

---

## Terraform (Infrastructure)

### Style
- Terraform 1.5+
- One `.tf` file per resource group
- Variables in `variables.tf`, outputs in `outputs.tf`
- Use modules for repeated patterns
- State stored in GCS with locking

### Naming
- Resources: `snake_case`
- Variables: `snake_case`
- Modules: `kebab-case` directories

---

## Git Workflow

### Branches
- `main`: Production-ready code. Protected. Requires PR with review.
- `feature/*`: New features. Branch from main, merge to main via PR.
- `fix/*`: Bug fixes. Same flow as features.
- `hotfix/*`: Emergency production fixes. Fast-tracked review.

### Commits
- Format: `<type>(<scope>): <description>`
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`
- Scope: service name or module (`api`, `web`, `worker`, `infra`, `shared`)
- Examples:
  - `feat(api): add batch resolution endpoint`
  - `fix(worker): handle export timeout correctly`
  - `test(shared): add evidence chain serialization tests`
  - `ci: add container image scanning step`

### PR Requirements
- At least 1 approval from a reviewer who is not the author
- All CI checks pass
- PR description explains what and why
- PR template checklist completed (invariants, forbidden patterns)

---

## Logging Standards

### Log Levels
- `ERROR`: Something failed and requires attention. Include correlation_id.
- `WARNING`: Something unexpected but handled. Circuit breaker opened, fallback activated.
- `INFO`: Normal operations worth recording. Resolution completed, review decision made, export generated.
- `DEBUG`: Detailed information for troubleshooting. Not enabled in production by default.

### Required Fields
Every log entry must include:
- `correlation_id`: Trace ID from request header or Pub/Sub message
- `tenant_id`: Tenant context (from auth token or job context)
- `service`: Service name (ia-api, ia-web, ia-worker)
- `timestamp`: ISO 8601
- `level`: Log level

### Log Classification
- **Public**: No sensitive data. Safe for general log aggregation.
- **Internal**: Operational data. Safe for internal tools but not customer-facing.
- **Sensitive**: Contains references to tenant data. Requires access controls on log storage.
- **Restricted**: Contains PII/PHI. MUST NOT EXIST — if this classification is needed, the data should have been scrubbed first.

### PII Scrubbing Rules
- ALL log entries pass through the PII scrubber before output
- PII categories scrubbed: names, SSN, email, phone, DOB, MRN, credit card, address, IP, driver's license
- Scrubbed format: `[CATEGORY_REDACTED]` (e.g., `[SSN_REDACTED]`, `[EMAIL_REDACTED]`)
- PHI NEVER appears in logs at ANY level (HIPAA requirement)
- Document content NEVER appears in logs (too risky, even scrubbed)

---

## Review Expectations

### Code Review Checklist
- [ ] No architecture invariant violations (INV-001 through INV-012)
- [ ] No forbidden patterns (FP-001 through FP-012)
- [ ] Type annotations on all functions
- [ ] Error handling follows conventions
- [ ] Logging includes required fields
- [ ] PII scrubbing verified (if handling user data)
- [ ] Tenant isolation maintained (if touching data access)
- [ ] Tests cover the change
- [ ] No hardcoded thresholds or magic numbers
