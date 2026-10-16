export const meta = {
  name: 'phase-0-3-production-shape',
  description: 'Raise quality from 6.8 to ~9.0: Phase 0 hygiene, Phase 1 DI/async, Phase 2 security/metrics, Phase 3 frontend refactor',
  phases: [
    { title: 'Phase 0 + 1a: Hygiene + Backend Core DI' },
    { title: 'Phase 1b: ranking.py + segment_resolver async' },
    { title: 'Phase 2: Security/Metrics/Compose' },
    { title: 'Phase 3: Frontend refactor' },
    { title: 'Phase E: CI pipeline' },
    { title: 'Verify + Finalize' },
  ],
};

const BRANCH = 'fix/phase-0-3-production-shape';
const REPO = 'E:/build6week';

function scriptFor(label, instructions) {
  return `You are agent "${label}" working on repo ${REPO}, branch ${BRANCH}.
WORKING DIRECTORY: ${REPO}

${instructions}

RULES:
- Do NOT modify dataset_v1/.
- Do NOT change ranking/eligibility semantics.
- Commit per sub-task with descriptive messages.
- Return a JSON object: { "done": [...], "blocked": [...], "notes": "..." }
- Each item in "done" must be a concrete file changed or action taken.
- If something is genuinely blocked (not just inconvenient), list it in "blocked".
- End every work session with git add + git commit on the branch.` ;
}

// ─────────────────────────────────────────────
// PHASE 0: Hygiene + Docs (A)
// PHASE 1a: Backend Core DI (B) — first slice
// These two agents run in parallel independently.
// ─────────────────────────────────────────────
phase('Phase 0 + 1a: Hygiene + Backend Core DI');

const [hygieneResult, backendCoreResult] = await parallel([
  () => agent(scriptFor('Agent-A:Hygiene', `
TASK: Phase 0 hygiene + docs cleanup for repo ${REPO}, branch ${BRANCH}.

WORK ITEMS (do all of these):

1. .gitignore
   - Add /graphify-out/ (entire directory)
   - Add /tests/security/checklist.py (delete the file entirely)
   - Remove graphify-out/ from git: git rm -r --cached graphify-out/ 2>/dev/null || true
   - Ensure graphify-out/ is in .gitignore

2. Delete graphify-out/ directory if it exists (rm -rf ${REPO}/graphify-out)

3. Vendor h3 locally:
   - Download https://unpkg.com/h3-js@4.3.1/dist/h3.js
   - Save to backend/app/static/demo/js/vendor/h3.js
   - Remove unpkg h3 from index.html and any HTML that loads it from CDN
   - If backend/app/requirements*.txt or pyproject.toml lists h3 as a Python dependency, REMOVE it

4. docs/ cleanup:
   - Check every link in README.md and docs/*.md that points to another .md file
   - For each link, verify the target file exists (ls ${REPO}/<path>)
   - If a link is broken (file missing), either restore the file OR remove the link
   - Do NOT create new docs — only fix broken links or delete dangling references
   - Check these specific files for broken links:
     * docs/ARCHITECTURE.md
     * docs/OPERATIONS.md
     * README.md
   - Remove references to k8s/, kubectl apply, multi-AZ, zero-downtime (replace with honest single-node description)
   - Remove or fix references to kubectl apply -f k8s/ patterns

5. AGENTS.md: add PHASE_TRACKER.md to the list of files agents must read

6. LICENSE: ensure it exists (Apache 2.0 or similar)

7. .env.example: ensure it exists with all required env vars documented (DB_HOST, REDIS_HOST, GRAPHHOPPER_URL, etc.)

8. Remove pytest.ini or setup.cfg "filterwarnings = ignore::DeprecationWarning" — stop suppressing utcnow deprecation

COMMIT each logical group separately:
- "chore: remove graphify-out from repo"
- "chore: vendor h3-js locally, remove Python h3 dependency"
- "chore: fix broken doc links, add honest descriptions"
- "chore: add .env.example and LICENSE"
- "chore: stop suppressing DeprecationWarning in pytest"

Return done/blocked/notes as JSON.
`), { label: 'A:Hygiene', schema: { type: 'object', properties: { done: { type: 'array', items: { type: 'string' } }, blocked: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['done', 'blocked', 'notes'] } }),
  () => agent(scriptFor('Agent-B:BackendCore', `
TASK: Phase 1 core DI + async foundation for repo ${REPO}, branch ${BRANCH}.

FIRST: Read ${REPO}/backend/app/main.py and ${REPO}/backend/app/dependencies.py to understand current state.

WORK ITEMS:

1. LIFESPAN refactor:
   - Convert lifespan to async context manager in main.py
   - Move all startup/shutdown logic into lifespan
   - App state should hold: db_pool, redis_client, routing_engine, candidate_service, demand_service
   - All services receive their dependencies via constructor (not global singletons)
   - Remove module-level singletons: _candidate_service_instance, _global_service, _global_resolver, _global_store
   - Verify: grep -r "_candidate_service_instance\|_global_service\|_global_resolver\|_global_store" backend/app/ should return nothing

2. DEPENDENCIES refactor:
   - Create or update backend/app/dependencies.py
   - All getters (get_candidate_service, get_demand_service, get_routing_engine, etc.) read from request.app.state
   - No getter should construct a GraphHopper adapter as fallback — if state key is missing, raise HTTPException(500)
   - /recommend should use get_demand_service() from dependencies (not a module global)

3. HEALTH endpoint:
   - /ready should call dependencies_ready(request) using the request to access the DB pool
   - Test 200 when all deps ready, 503 when DB pool unavailable
   - Add /health for liveness (always 200 if app is running)

4. REALTIME state.py:
   - Make async where it calls asyncpg or Redis
   - All public functions should be async def
   - No sync psycopg2 in backend/app/realtime/

5. MAP_MATCH getters:
   - All getters (get_map_match_service, etc.) should read from app.state only
   - Remove any global singleton patterns

6. Import cleanup:
   - backend/app/ should have NO "import psycopg2" (that's for segment_resolver, handled separately)
   - Ensure all imports in backend/app/main.py, dependencies.py are async-compatible

COMMIT each logical group:
- "refactor: convert lifespan to async context manager"
- "refactor: replace singletons with app.state DI"
- "refactor: health endpoint uses pool-aware dependency check"
- "refactor: make realtime state async"

Return done/blocked/notes as JSON.
`), { label: 'B:BackendCore', schema: { type: 'object', properties: { done: { type: 'array', items: { type: 'string' } }, blocked: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['done', 'blocked', 'notes'] } }),
]);

log(`A (Hygiene): ${JSON.stringify(hygieneResult)}`);
log(`B (BackendCore): ${JSON.stringify(backendCoreResult)}`);

// ─────────────────────────────────────────────
// PHASE 1b: ranking.py + segment_resolver
// ─────────────────────────────────────────────
phase('Phase 1b: ranking.py + segment_resolver async');

const backendSecondResult = await agent(scriptFor('Agent-B2:BackendSecond', `
TASK: Phase 1b — ranking.py + segment_resolver async for repo ${REPO}, branch ${BRANCH}.

FIRST: Read these files to understand current state:
- ${REPO}/backend/app/services/ranking.py
- ${REPO}/backend/app/services/segment_resolver.py
- ${REPO}/backend/app/services/capability.py
- ${REPO}/backend/app/dependencies.py (after Agent-B may have modified it)

WORK ITEMS:

1. segment_resolver.py:
   - Replace sync psycopg2 with asyncpg
   - Get connection from the app's db_pool (passed in via constructor or from app.state)
   - All public functions become async def
   - The pool should be created in lifespan and stored in app.state
   - No new global singletons
   - Verify: grep -r "import psycopg2" backend/app/ should return nothing

2. capability.py:
   - Make async if it calls the database
   - Update all callers to use await

3. ranking.py:
   - Make sure it reads from app.state via dependencies
   - ranking.py is needed by Agent-C (security/metrics) — keep the interface stable
   - Do NOT change the ranking algorithm or eligibility logic
   - Only refactor for DI consistency

4. candidate/demand service constructors:
   - These should receive their dependencies (routing_engine, db_pool, redis_client) via constructor
   - No create_*_service() functions that instantiate engine adapters inside

5. Wire up the full chain in main.py lifespan:
   - Create db_pool with asyncpg (with init extension for PostGIS)
   - Create redis_client with aioredis/redis.asyncio
   - Create routing_engine (GraphHopper adapter)
   - Create candidate_service(demand_service=...)
   - Create demand_service(routing_engine=...)
   - Store all in app.state

COMMIT:
- "refactor: segment_resolver uses asyncpg from pool"
- "refactor: wire full DI chain in lifespan"

Return done/blocked/notes as JSON.
`), { label: 'B2:BackendSecond', schema: { type: 'object', properties: { done: { type: 'array', items: { type: 'string' } }, blocked: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['done', 'blocked', 'notes'] } });

log(`B2 (BackendSecond): ${JSON.stringify(backendSecondResult)}`);

// ─────────────────────────────────────────────
// PHASE 2: Security / Metrics / Compose
// ─────────────────────────────────────────────
phase('Phase 2: Security/Metrics/Compose');

const securityResult = await agent(scriptFor('Agent-C:Security', `
TASK: Phase 2 — Security, Metrics, Docker Compose for repo ${REPO}, branch ${BRANCH}.

FIRST: Read these files:
- ${REPO}/backend/app/main.py
- ${REPO}/backend/app/middleware.py (if exists)
- ${REPO}/backend/app/core/metrics.py
- ${REPO}/backend/docker-compose.yml
- ${REPO}/backend/Dockerfile

WORK ITEMS:

1. simulate-tick authentication:
   - POST /api/v1/snapshots/simulate-tick must require authorize_ingestion header/credential
   - Add middleware or endpoint-level auth check
   - Return 401 if not authorized

2. Rate limiter fix:
   - Do NOT exempt /api/v1/drivers/ from rate limiting
   - Rate limit should apply to all /api/v1/ endpoints
   - When Redis is available, use it for rate limiting
   - Return Retry-After header when rate limited (HTTP 429)
   - Add test: verify /drivers/ endpoints ARE rate limited

3. Docker Compose security:
   - Change all port bindings from "5432:5432" to "127.0.0.1:5432:5432"
   - Change Redis port to 127.0.0.1:6379:6379
   - Document the security reason (bind to localhost only)

4. Dockerfile:
   - Use "pip install -e ." or "pip install ." from pyproject.toml
   - Do NOT pip install from requirements.txt directly (it's auto-generated)
   - Verify: Dockerfile should not have redundant pip install lines

5. Metrics wiring (core/metrics.py):
   - Find ALL call sites: grep -r "record_request\|observe_recommendation\|observe_route_call\|record_candidate_conflict\|record_db_fallback" backend/
   - Each counter must be incremented at the actual call site
   - The metrics object should come from app.state
   - Add new metrics: request_latency_seconds, db_pool_available, redis_available
   - Add tests/test_metrics.py that verifies counter increments

6. new tests/test_security.py:
   - Test simulate-tick returns 401 without auth
   - Test simulate-tick returns 200 with valid auth
   - Test rate limiter applies to /drivers/
   - Test 429 includes Retry-After header

COMMIT:
- "security: add auth to simulate-tick endpoint"
- "security: rate limit /drivers/ endpoints"
- "security: bind compose ports to 127.0.0.1"
- "metrics: wire all counter call sites from app.state"
- "test: add test_security.py and test_metrics.py"

Return done/blocked/notes as JSON.
`), { label: 'C:Security', schema: { type: 'object', properties: { done: { type: 'array', items: { type: 'string' } }, blocked: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['done', 'blocked', 'notes'] } });

log(`C (Security): ${JSON.stringify(securityResult)}`);

// ─────────────────────────────────────────────
// PHASE 3: Frontend
// ─────────────────────────────────────────────
phase('Phase 3: Frontend refactor');

const frontendResult = await agent(scriptFor('Agent-D:Frontend', `
TASK: Phase 3 — Frontend refactor for repo ${REPO}, branch ${BRANCH}.

FIRST:
- Read ${REPO}/backend/app/static/demo/js/driver_mode.js
- Read ${REPO}/backend/app/main.py to find the GET /api/v1/vehicles/catalog endpoint (or implement it if missing)
- Read ${REPO}/tests/frontend/*.mjs

WORK ITEMS:

1. vehicle catalog endpoint:
   - GET /api/v1/vehicles/catalog must return a JSON array of vehicle definitions
   - Schema: { id, name, battery_kwh, efficiency_kwh_per_km, supported_services[] }
   - This is the SINGLE source of truth for the frontend vehicle catalog
   - Update or create the endpoint in main.py or a vehicles.py router

2. driver_mode.js refactor (target: <= 400 lines):
   - Read it carefully — identify which code is:
    a) Pure domain logic (calculations, state machines, data transformation)
    b) DOM manipulation (document.getElementById, innerHTML, classList, etc.)
    c) UI orchestration (wiring domain to DOM)
   - Extract pure domain logic into: ${REPO}/backend/app/static/demo/js/domain/soc-calculator.js
   - Extract pure domain logic into: ${REPO}/backend/app/static/demo/js/domain/route-display.js
   - Keep DOM-only code in driver_mode.js (<= 400 lines)
   - Domain modules must NOT reference document, window, or DOM APIs
   - The catalog fetch: GET /api/v1/vehicles/catalog → domain module, not DOM code

3. driver_mode.js DOM safety:
   - Replace all innerHTML += ... where you insert user data (ids, names) with:
     * document.createElement + textContent + appendChild
     * Or template literals with explicit escaping
   - innerHTML is OK for static HTML strings with no user data interpolation
   - This is the #1 XSS surface — audit every innerHTML usage

4. HTML in ui/ directory:
   - Move driver_mode.html to ${REPO}/backend/app/static/demo/ui/
   - Move any other HTML files to ui/
   - index.html stays in static/demo/ (entry point)

5. Frontend tests:
   - Read existing tests/frontend/*.mjs
   - Ensure tests still pass after refactor: node --test tests/frontend/*.mjs
   - Add test for catalog fetch (mock the /catalog endpoint)
   - Domain modules should have unit tests with no DOM

6. Node frontend tests must pass:
   - Run: node --test tests/frontend/*.mjs
   - Fix any failures before declaring done

COMMIT:
- "feat: add GET /api/v1/vehicles/catalog endpoint"
- "refactor: extract domain logic from driver_mode.js"
- "security: replace innerHTML with textContent for user data"
- "refactor: move HTML to ui/ directory"
- "test: update frontend tests for domain modules"

Return done/blocked/notes as JSON.
`), { label: 'D:Frontend', schema: { type: 'object', properties: { done: { type: 'array', items: { type: 'string' } }, blocked: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['done', 'blocked', 'notes'] } });

log(`D (Frontend): ${JSON.stringify(frontendResult)}`);

// ─────────────────────────────────────────────
// PHASE E: CI
// ─────────────────────────────────────────────
phase('Phase E: CI pipeline');

const ciResult = await agent(scriptFor('Agent-E:CI', `
TASK: Phase E — CI pipeline for repo ${REPO}, branch ${BRANCH}.

WORK ITEMS:

1. Create .github/workflows/ci.yml:
   - Trigger on: push to main, pull_request
   - Jobs:
     * lint: run ruff check backend/
     * test-backend: pytest backend/tests -q
     * test-frontend: node --test tests/frontend/*.mjs
     * validate-data: python scripts/validate_frozen_dataset.py
   - Python version: 3.11
   - Cache: pip cache, node_modules
   - Fail-fast: false (all jobs run regardless)
   - Each job must pass for the overall run to pass

2. Update Makefile:
   - Add test target: pytest backend/tests -q
   - Add lint target: ruff check backend/
   - Add test-frontend target: node --test tests/frontend/*.mjs
   - Add validate target: python scripts/validate_frozen_dataset.py
   - Add ci-check target that runs lint + test-backend + test-frontend + validate

3. Add ruff configuration if not present:
   - pyproject.toml should have [tool.ruff] section
   - Line length: 88
   - Target Python: 3.11

4. Verify ruff passes:
   - Run: ruff check backend/ 2>&1
   - Fix ALL errors (not warnings) — or document why a warning is suppressed

COMMIT:
- "ci: add GitHub Actions workflow"
- "ci: add lint and test targets to Makefile"
- "ci: configure ruff in pyproject.toml"

Return done/blocked/notes as JSON.
`), { label: 'E:CI', schema: { type: 'object', properties: { done: { type: 'array', items: { type: 'string' } }, blocked: { type: 'array', items: { type: 'string' } }, notes: { type: 'string' } }, required: ['done', 'blocked', 'notes'] } });

log(`E (CI): ${JSON.stringify(ciResult)}`);

// ─────────────────────────────────────────────
// VERIFY + FINALIZE
// ─────────────────────────────────────────────
phase('Verify + Finalize');

const verifyResult = await agent(scriptFor('Agent-Verify:Verify', `
TASK: Verify all phases for repo ${REPO}, branch ${BRANCH}.

Run these exact commands and report output:

1. Singleton check (must be zero):
   rg "utcnow|psycopg2|_candidate_service_instance|_global_service|_global_resolver|_global_store" backend/app || echo "SINGLES_OK"

2. driver_mode.js line count (must be <= 400):
   wc -l backend/app/static/demo/js/driver_mode.js

3. Backend tests:
   cd ${REPO}/backend && pytest tests -q 2>&1 | tail -5

4. Frontend tests:
   cd ${REPO} && node --test tests/frontend/*.mjs 2>&1 | tail -5

5. Ruff lint:
   cd ${REPO} && ruff check backend/ 2>&1 | tail -5

6. Doc links:
   - For each .md file in docs/, extract all [text](path) links where path ends in .md
   - Verify each target exists: test -f ${REPO}/<path> && echo "OK: <path>" || echo "BROKEN: <path>"

7. git status:
   git status --short

8. Docker compose ports:
   grep -n "127.0.0.1" ${REPO}/backend/docker-compose.yml

9. h3 vendor check:
   test -f ${REPO}/backend/app/static/demo/js/vendor/h3.js && echo "h3_vendored" || echo "h3_NOT_vendored"

10. graphify-out deleted:
    test -d ${REPO}/graphify-out && echo "graphify-out_EXISTS" || echo "graphify-out_deleted"

11. segment_resolver uses asyncpg:
    grep "import psycopg2" ${REPO}/backend/app/services/segment_resolver.py && echo "STILL_HAS_PSYCOPG2" || echo "asyncpg_ok"

Return ALL output for each command. Return as JSON: { "results": {...}, "all_passed": true/false, "remaining_debts": [...] }.
`), { label: 'Verify', schema: { type: 'object', properties: { results: { type: 'object' }, all_passed: { type: 'boolean' }, remaining_debts: { type: 'array', items: { type: 'string' } } }, required: ['results', 'all_passed', 'remaining_debts'] } });

log(`Verify: ${JSON.stringify(verifyResult)}`);

// Now fill PHASE_TRACKER.md with results
log('\n=== FINAL REPORT ===');
log(`Hygiene (A): ${hygieneResult.notes}`);
log(`BackendCore (B): ${backendCoreResult.notes}`);
log(`BackendSecond (B2): ${backendSecondResult.notes}`);
log(`Security (C): ${securityResult.notes}`);
log(`Frontend (D): ${frontendResult.notes}`);
log(`CI (E): ${ciResult.notes}`);
log(`Verify all_passed: ${verifyResult.all_passed}`);
log(`Remaining debts: ${JSON.stringify(verifyResult.remaining_debts)}`);

return {
  hygiene: hygieneResult,
  backendCore: backendCoreResult,
  backendSecond: backendSecondResult,
  security: securityResult,
  frontend: frontendResult,
  ci: ciResult,
  verify: verifyResult,
  all_passed: verifyResult.all_passed,
  remaining_debts: verifyResult.remaining_debts,
};
