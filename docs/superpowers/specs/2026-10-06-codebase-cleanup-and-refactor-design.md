# Codebase Cleanup, Architecture Consolidation & Knowledge Graph Design

- **Date**: 2026-10-06
- **Status**: Approved
- **Author**: Antigravity Pair Programming

---

## 1. Executive Summary

This specification outlines the comprehensive restructuring, bloat elimination, test suite stabilization, and knowledge graph generation for the `build6week` repository. Over successive development iterations, numerous prompt transcripts, intermediate plans, PowerPoint presentations, duplicate audit snapshot trees, test failure traces, and replay dumps accumulated across the codebase. These unnecessary files inflate token consumption for AI agents and introduce search noise.

This design establishes a clean, production-grade layout where:
1. All junk, prompts, duplicate backend code snapshots, presentation files, and runtime test dumps are eliminated.
2. The core backend services, demo UI, data pipelines, and canonical dataset remain intact and fully functional.
3. All unit and integration tests are brought to 100% green status.
4. `.gitignore` is updated to prevent future pollution.
5. Graphify is executed on the purified codebase to build a navigable, persistent knowledge graph (`graphify-out/`).

---

## 2. Inventory & Deletion Scope

### 2.1 Files & Folders Marked for Total Removal
- **Prompt Files**:
  - `add_top5_badges_prompt.md`
  - `auto_recommend_panel_prompt.md`
  - `debug_replay_stop_prompt.md`
  - `fix_rate_limit_bug_prompt.md`
  - `h3_overlay_prompt.md`
  - `h3_route_similarity_prompt.md`
  - `docs/SLIDE_PROMPT.md`
- **Obsolete Plan & Fix Docs**:
  - `PLAN.md`
  - `PLAN_DEMO_FIX.md`
  - `PLAN_DEMO_FIXES.md`
  - `docs/PLAN_TO_9_5.md`
  - `docs/BAYESIAN_PENALTY_PLAN.md`
  - `docs/superpowers/plans/*`
- **Presentation Decks & Presentation Scripts**:
  - `EV_Architecture_Mentor.pptx`
  - `EV_Arch_Mentor_v2.pptx`
  - `EV_Arch_Mentor_v3.pptx`
  - `EV_Arch_Mentor_v4.pptx`
  - `EV_Charging_Architecture.pptx`
  - `EV_Charging_Recommendation_VinFast.pptx`
  - `EV_Charging_Technical_Architecture.pptx`
  - `NGUYEN_VAN_NINH_S_AI_20K_Ke_hoach_nghiem_thu_6_tuan.xlsx`
  - `docs/GSMVSF_Presentation_Final.pptx`
  - `docs/GSMVSF_System_Architecture_Slides.pptx`
  - `docs/GSMVSF_System_Presentation.pptx`
  - `docs/GSMVSF_Tech_Architecture.pptx`
  - `scripts/create_presentation.py`
  - `scripts/generate_native_presentation.py`
  - `scripts/generate_presentation.py`
  - `scripts/generate_tech_presentation.py`
- **Duplicate Snapshot Trees (Major Token Hogs)**:
  - `audit_review/` (contains redundant copies of backend & docs)
  - `fixpack_review/` (contains redundant copies of backend & docs)
  - `claude_week1_skills/` (historical redundant skills)
  - `.claude/skills/open-map-stack/` (unrelated embedded repository)
- **Runtime Dumps, Test Results & Binaries**:
  - `runtime/week5/replay-*` (temporary replay test run outputs)
  - `test-results/` (Playwright screenshot traces)
  - `tools/cloudflared.exe` (55 MB binary executable)
- **Nested Accidental Clones & Obsolete Reports**:
  - `data/external/vinfast_stations/scripts/data/` (nested accidental clone)
  - `EVALUATION_REPORT.md` (superseded by `docs/WEEK_5_5_DEMO_REPORT.md`)
  - `FINAL_9_5_REPORT.md` (superseded by `docs/WEEK_5_5_DEMO_REPORT.md`)
  - `docs/DAILY_REPORT_*.md`

### 2.2 Preserved Canonical & Critical Assets
- `dataset_v1/`: Read-only canonical dataset. Untouched. Must preserve 152/152 PASS and 22/22 scenarios on `scripts/validate_frozen_dataset.py`.
- `backend/app/`: Core FastAPI app (routers, core config, database, redis, domain models, services, static demo).
- `backend/tests/`: Pytest suite.
- `frontend/`: Dockerfile, nginx.conf, test specs for demo UI.
- `scripts/`: Essential scripts (verification, validation, benchmarks, data loading).
- `docs/`: Core architectural documentation (`ARCHITECTURE.md`, `DATA_CONTRACT.md`, `PROJECT_SCOPE.md`, `DECISIONS.md`, `ACCEPTANCE_CRITERIA.md`, `OPERATIONS.md`, `WEEK_5_5_DEMO_REPORT.md`).
- `docker-compose.yml`, `Makefile`, `README.md`, `AGENTS.md`.

---

## 3. Architecture & Target Directory Layout

```
build6week/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers & endpoints (v1)
│   │   ├── core/         # Settings, database, redis, logging
│   │   ├── models/       # Domain schemas (candidate, demand, vehicle, etc.)
│   │   ├── services/     # Core algorithms (matching, ranking, candidate, routing)
│   │   └── static/demo/  # Browser demo UI assets (HTML, CSS, JS)
│   └── tests/            # Pytest suite
├── data/
│   └── external/         # External GPS and VinFast station datasets
├── dataset_v1/           # Canonical ground-truth dataset (Read-only)
├── docs/                 # Architectural specifications and standards
├── frontend/             # Nginx reverse proxy configuration & container definition
├── scripts/              # Operational & evaluation CLI tools
├── graphify-out/         # Persistent knowledge graph (graph.html, graph.json, GRAPH_REPORT.md)
├── .gitignore            # Git exclusion rules
├── AGENTS.md             # Developer & agent guidelines
├── Makefile              # Project automation tasks
├── README.md             # Repository documentation
└── docker-compose.yml    # Service orchestration
```

---

## 4. Code Formatting & Test Stabilization

### 4.1 Test Stabilization
1. **Bayesian Penalty Tests** (`backend/tests/services/test_bayesian_familiarity.py`, `backend/tests/services/test_familiarity.py`):
   - Align test assertion values with the updated Bayesian formula parameters (`max_penalty=0.1`, `confidence` curve, `bayesian_reduction`).
2. **Load Tests** (`backend/tests/load/test_load.py`):
   - Ensure `aiohttp.ClientSession` is initialized within an active asyncio event loop, resolving Python 3.14 compatibility errors.

### 4.2 Formatting & PEP 8 Standardization
- Format all Python files under `backend/` and `scripts/` using PEP 8 formatting standards.
- Remove dead imports, unused temporary variables, and dangling `__pycache__` artifacts.

---

## 5. Knowledge Graph Generation (Graphify)

Once the repository is purged of junk files:
1. Execute `graphify . --mode deep` (or standard extraction) on the cleaned repository.
2. AST extraction processes clean code files deterministically.
3. Cluster communities and score cohesion.
4. Export:
   - `graphify-out/graph.html` (interactive architecture visualizer)
   - `graphify-out/graph.json` (machine-readable knowledge graph for AI tools)
   - `graphify-out/GRAPH_REPORT.md` (god nodes, surprises, community summaries)

---

## 6. Verification & Quality Gates

1. **Dataset Integrity**: Run `python scripts/validate_frozen_dataset.py` -> Must report 152 PASS / 0 FAIL / 22 Scenarios.
2. **Unit & Integration Tests**: Run `pytest backend/tests` -> Must report 100% green tests with 0 failures and 0 errors.
3. **Graphify Output**: Verify `graphify-out/graph.json` and `graphify-out/GRAPH_REPORT.md` are generated and valid.
4. **Git Cleanliness**: Run `git status` -> Confirm no dangling junk files or untracked clutter.
