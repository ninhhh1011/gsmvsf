# Offline Route Weight Calibration Design

**Status:** Design for review  
**Scope:** Offline, reproducible experiment only. It does not change runtime ranking or the 80/10/10 policy recorded in ADR-025.

## Goal

Create and run `scripts/train_route_weights.py` to demonstrate how listwise ranking weights can be estimated from controlled synthetic route choices. The script prints an epoch log and writes `weights_calibration_report.json` at the repository root. The report is an experiment artifact, not a backend configuration file.

## Existing behavior and boundary

The project already has route-familiarity history, ranking services, and a synthetic journey seeder whose behavioral choice cost is independent of the runtime policy. It has no mock request dataset containing all of this experiment's time, familiarity, and evidence-count inputs, and no weight-training flow. The new script will generate its own controlled observations with Python's standard library. It will not read Dataset V1 labels, access runtime services, ingest histories, modify `dataset_v1/`, or activate the learned weights.

## Synthetic observations

- Generate 400 requests with three or four valid route candidates each, using a fixed seed.
- Each request has one fastest candidate with normalized journey time `T/T_min = 1`. Other candidates have ratios in `[1.03, 1.20]`.
- Generate personal and community familiarity in `[0, 1]`; alternatives are biased toward higher familiarity and usable evidence counts. Draw personal history trips and community driver counts as nonnegative integers, and calculate each confidence as `n / (n + 3)` (zero when `n = 0`).
- Build each candidate's three features as `[T/T_min, (1-F_personal)C_personal, (1-F_community)C_community]`.
- Produce `chosen_idx` from a latent preference `[0.60, 0.27, 0.13]` and seeded Gaussian score noise. This latent preference is independent of the prior `[0.80, 0.10, 0.10]`; the observed choice labels are then fixed before training.
- In a small deterministic subset of slower alternatives, set one evidence count to zero while retaining positive evidence on the other signal. Keep the fastest candidate's personal and community counts in `[8, 15]`; assert zero confidence and a zero corresponding feature term.
- Split whole requests 80/20 into train and held-out evaluation sets with the seeded generator. Fit only on training requests. Report final before/after metrics on held-out requests; epoch accuracy is on the training requests.

The selected synthetic route represents the route the driver completes. A recommendation counts as a simulated abandonment when its top-ranked candidate differs from `chosen_idx`. This is a controlled label definition, not an estimate of real-world abandonment.

## Training

Start at exactly `[0.80, 0.10, 0.10]`. Minimize mean listwise softmin cross-entropy with `beta = 8` and L2 penalty `lambda = 0.05` toward that prior. Use projected gradient descent, a fixed learning rate and a bounded epoch count, recording epoch 0 and each update. Stop early only after a documented convergence tolerance is met.

After every update, project onto the constrained simplex: each coordinate is at least `0.01` and all three sum to `1`. Use a small standard-library projection routine and assert its constraints after each projection. Softmax is computed with max-shifting for numerical stability. Training loss includes the regularizer; accuracy is the fraction whose lowest-score route matches `chosen_idx`.

## Output and evaluation

The terminal log contains epoch/step, all three weights, training loss, and training top-1 accuracy. The before/after held-out comparison contains top-1 accuracy, simulated abandonment rate, and mean recommended `T/T_min`, followed by explicit accuracy, abandonment-reduction, and normalized-time deltas. The JSON report also records seed, generator/training parameters, split sizes, prior and learned weights, metric definitions, and the explicit limitation that controlled synthetic results do not establish field behavior.

## Files and verification

- Add only `scripts/train_route_weights.py` and the generated root-level `weights_calibration_report.json` on the feature branch.
- Do not change runtime ranking code, backend configuration, ADR-025, or Dataset V1.
- Run the script directly from the repository root and inspect that the report parses, weights satisfy the simplex floor/sum constraints, and the printed metrics agree with the report. Do not add a test suite for this standalone experiment.

## Known limit

The synthetic choice model deliberately encodes known preferences, so learned weights demonstrate recovery under controlled assumptions. The report must not present its accuracy or abandonment rate as observed driver performance or a production recommendation.
