# Offline Route Weight Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and run a reproducible offline Python experiment that estimates route-ranking weights from controlled synthetic choices and writes a held-out evaluation report.

**Architecture:** Keep the experiment in one standalone script using only Python's standard library. It generates and splits route-choice requests, trains weights with projected gradient descent, prints the epoch log, evaluates the prior and learned weights on held-out requests, and writes a root-level JSON report. Runtime ranking and backend configuration remain untouched.

**Tech Stack:** Python standard library (`random`, `math`, `json`, `pathlib`).

**Spec:** `docs/superpowers/specs/2026-10-15-route-weight-calibration-design.md`

## Global Constraints

- Generate exactly 400 requests, each with three or four valid candidates, using a fixed seed.
- Each request has one fastest candidate at `T/T_min = 1`; slower candidates have ratios in `[1.03, 1.20]`.
- Personal and community confidence are `n / (n + 3)`, with zero confidence when `n = 0`.
- Candidate features are `[T/T_min, (1-F_personal)C_personal, (1-F_community)C_community]`.
- Synthetic labels use latent weights `[0.60, 0.27, 0.13]` and seeded Gaussian score noise, independently of prior `[0.80, 0.10, 0.10]`.
- A small deterministic subset of slower alternatives has zero evidence for one familiarity signal and positive evidence for the other; the fastest candidate retains 8–15 counts for both signals.
- Split whole requests 80/20 and fit only on the training split.
- Train listwise softmin cross-entropy with `beta = 8`, `lambda = 0.05`, and projected gradient descent.
- Enforce `sum(w) = 1` and `w_i >= 0.01` after every update.
- Do not read evaluation labels, access runtime services, modify `dataset_v1/`, or activate learned weights.
- Add no dependencies and no separate test suite; execute the requested script and its embedded assertions.

## Review Focus

- A candidate with zero personal or community history must have confidence exactly zero; check generated feature values and confidence at generation time.
- A projected weight vector must retain the 0.01 floor and sum to one within floating point tolerance; assert this after every optimizer step.
- Softmin probabilities must remain finite for large score magnitudes; max-shift before exponentiation and assert normalized probabilities.
- Train and held-out sets must contain disjoint whole requests; assert request IDs do not overlap after the split.
- “Simulated abandonment” must use the held-out `chosen_idx` definition; report it as a mismatched top recommendation and label it synthetic.

---

### Task 1: Build, run, and report the offline calibration

**Files:**
- Create: `scripts/train_route_weights.py`
- Create by running the script: `weights_calibration_report.json`

**Interfaces:**
- CLI: `python scripts/train_route_weights.py` from the repository root; no required arguments or external services.
- Internal candidate record: feature triple, `chosen_idx` at request level, and stable request ID for split checks.
- Report JSON: generator and optimizer parameters, split sizes, initial and learned weights, epoch log, held-out before/after metrics, and synthetic-data limitation.

- [x] **Step 1: Generate deterministic candidate lists and labels.** Use one `random.Random(seed)` instance. Generate 400 requests; make candidate 0 the unique fastest route and sample the remaining time ratios from `[1.03, 1.20]`. Bias the fastest candidate's familiarity lower than slower alternatives. Sample separate personal-trip and community-driver counts, with a small deterministic zero-evidence subset among slower alternatives; calculate `C = n / (n + 3)` and assert zero-count confidence and feature terms are zero. Choose `chosen_idx` by minimizing latent weighted cost plus seeded Gaussian noise. Shuffle request IDs once and split 320 train / 80 held-out; assert split disjointness and feature/count bounds.

- [x] **Step 2: Implement stable loss, gradient, and constrained projection.** Compute each request's softmin cross-entropy at `beta = 8`; use max-shifted exponentials. Average the data gradient and add `2 * lambda * (w - w0)` for `lambda = 0.05`. Project the update onto the simplex with coordinate floor `0.01` by projecting `w - 0.01` onto a simplex of mass `0.97`, then adding the floor. Assert finite probabilities, sum tolerance, and floor after every projection.

- [x] **Step 3: Train from the exact prior and print every epoch.** Start at `[0.80, 0.10, 0.10]`, use learning rate `0.2`, cap training at 250 updates, and stop after the weight-vector change stays below `1e-8` for 10 consecutive updates. The rate and cap were increased after fixed-seed probes showed `0.02` had not converged at its 200-update cap while `0.2` converged to the same solution as `0.05` in 169 updates. Print epoch 0 and each subsequent epoch with weights, regularized training loss, and training top-1 accuracy.

- [x] **Step 4: Evaluate and write the report.** On held-out requests, calculate top-1 accuracy, mismatch-based simulated abandonment rate, and mean `T/T_min` of the recommended candidate for both prior and learned weights. Serialize the epoch log, final weights, parameters, metrics, and synthetic limitation to `weights_calibration_report.json`; print before/after values and explicit deltas with documented sign conventions.

- [x] **Step 5: Execute and inspect the requested artifact.** Run `python scripts/train_route_weights.py` from the worktree root. Parse the JSON with Python's standard library; assert the report has 400 requests, an 80-request held-out set, finite metrics, matching prior/learned weights and simplex constraints, and printed/logged evaluation values agree. Confirm `git status` shows only the script and generated report beyond the already committed design/plan documents.

---
