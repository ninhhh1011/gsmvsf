"""Train route-ranking weights on controlled synthetic choices (offline only)."""

import json
import math
from pathlib import Path
import random


SEED = 26015
REQUESTS = 400
PRIOR = [0.80, 0.10, 0.10]
LATENT_WEIGHTS = [0.68, 0.20, 0.12]
BETA = 8.0
L2 = 0.05
LEARNING_RATE = 0.2
MAX_EPOCHS = 250
CONVERGENCE_TOLERANCE = 1e-8
CONVERGENCE_PATIENCE = 10
WEIGHT_FLOOR = 0.01


def confidence(count):
    assert count >= 0
    return count / (count + 3) if count else 0.0


def generate_data(seed=SEED):
    rng = random.Random(seed)
    assert confidence(0) == 0.0
    requests = []
    for request_id in range(REQUESTS):
        candidates = []
        for index in range(rng.randint(3, 4)):
            if index == 0:
                ratio = 1.0
                personal_f = rng.uniform(0.05, 0.45)
                community_f = rng.uniform(0.05, 0.45)
                personal_n = rng.randint(8, 15)
                community_n = rng.randint(8, 15)
            else:
                ratio = rng.uniform(1.03, 1.20)
                personal_f = rng.uniform(0.55, 0.98)
                community_f = rng.uniform(0.55, 0.98)
                personal_n = rng.randint(3, 15)
                community_n = rng.randint(3, 15)
            personal_c = confidence(personal_n)
            community_c = confidence(community_n)
            candidates.append({
                "ratio": ratio,
                "personal_familiarity": personal_f,
                "community_familiarity": community_f,
                "personal_history_trips": personal_n,
                "community_drivers": community_n,
                "personal_confidence": personal_c,
                "community_confidence": community_c,
                "features": [ratio, (1 - personal_f) * personal_c,
                             (1 - community_f) * community_c],
            })

        # Choices come from a separate latent policy; the training prior is not used.
        noisy_costs = [sum(w * x for w, x in zip(LATENT_WEIGHTS, candidate["features"]))
                       + rng.gauss(0, 0.035) for candidate in candidates]
        requests.append({"request_id": request_id, "candidates": candidates,
                         "chosen_idx": min(range(len(candidates)), key=noisy_costs.__getitem__)})

    order = list(range(len(requests)))
    rng.shuffle(order)
    for request in requests:
        t_min_s = rng.uniform(900, 3600)
        for candidate in request["candidates"]:
            candidate["T_min_s"] = t_min_s
            candidate["total_time_s"] = t_min_s * candidate["ratio"]

    train_ids, held_out_ids = set(order[:320]), set(order[320:])
    assert train_ids.isdisjoint(held_out_ids)
    train = [row for row in requests if row["request_id"] in train_ids]
    held_out = [row for row in requests if row["request_id"] in held_out_ids]
    assert (len(train), len(held_out)) == (320, 80)
    assert train_ids.isdisjoint({row["request_id"] for row in held_out})
    assert all(3 <= len(row["candidates"]) <= 4 for row in requests)
    assert all(candidate["ratio"] == 1.0 if index == 0
               else 1.03 <= candidate["ratio"] <= 1.20
               for row in requests for index, candidate in enumerate(row["candidates"]))
    assert all(candidate["personal_confidence"] == confidence(candidate["personal_history_trips"])
               and candidate["community_confidence"] == confidence(candidate["community_drivers"])
               for row in requests for candidate in row["candidates"])
    assert all(0 <= candidate["personal_familiarity"] <= 1
               and 0 <= candidate["community_familiarity"] <= 1
               and math.isclose(candidate["total_time_s"] / candidate["T_min_s"],
                                candidate["ratio"], abs_tol=1e-12)
               for row in requests for candidate in row["candidates"])
    return train, held_out


def project_weights(values):
    """Project onto sum(w)=1 with the required per-weight floor."""
    mass = 1 - 3 * WEIGHT_FLOOR
    shifted = [value - WEIGHT_FLOOR for value in values]
    ordered = sorted(shifted, reverse=True)
    cumulative = 0.0
    threshold = None
    for index, value in enumerate(ordered, 1):
        cumulative += value
        candidate_threshold = (cumulative - mass) / index
        if value > candidate_threshold:
            threshold = candidate_threshold
    assert threshold is not None
    projected = [max(value - threshold, 0.0) + WEIGHT_FLOOR for value in shifted]
    assert all(math.isfinite(weight) and weight >= WEIGHT_FLOOR - 1e-12 for weight in projected)
    assert math.isclose(sum(projected), 1.0, abs_tol=1e-10)
    return projected


def scores_for(request, weights):
    return [sum(weight * feature for weight, feature in zip(weights, candidate["features"]))
            for candidate in request["candidates"]]


def probabilities_for(scores):
    logits = [-BETA * score for score in scores]
    largest = max(logits)
    exponentials = [math.exp(value - largest) for value in logits]
    total = sum(exponentials)
    probabilities = [value / total for value in exponentials]
    assert all(math.isfinite(value) and value >= 0 for value in probabilities)
    assert math.isclose(sum(probabilities), 1.0, abs_tol=1e-12)
    return probabilities, logits, largest, total


def loss_and_gradient(requests, weights):
    gradient = [0.0, 0.0, 0.0]
    cross_entropy = 0.0
    for request in requests:
        scores = scores_for(request, weights)
        probabilities, logits, largest, total = probabilities_for(scores)
        chosen = request["chosen_idx"]
        cross_entropy += largest + math.log(total) - logits[chosen]
        for dimension in range(3):
            expected = sum(probability * candidate["features"][dimension]
                           for probability, candidate in zip(probabilities, request["candidates"]))
            gradient[dimension] += BETA * (request["candidates"][chosen]["features"][dimension] - expected)

    cross_entropy /= len(requests)
    gradient = [value / len(requests) + 2 * L2 * (weight - prior)
                for value, weight, prior in zip(gradient, weights, PRIOR)]
    loss = cross_entropy + L2 * sum((weight - prior) ** 2
                                    for weight, prior in zip(weights, PRIOR))
    assert math.isfinite(loss) and all(math.isfinite(value) for value in gradient)
    return loss, gradient


def accuracy(requests, weights):
    return sum(min(range(len(request["candidates"])),
                   key=scores_for(request, weights).__getitem__) == request["chosen_idx"]
               for request in requests) / len(requests)


def train(requests):
    weights = PRIOR.copy()
    loss, _ = loss_and_gradient(requests, weights)
    log = [{"epoch": 0, "weights": weights.copy(), "loss": loss,
            "top1_accuracy": accuracy(requests, weights)}]
    stable_epochs = 0
    converged = False
    for epoch in range(1, MAX_EPOCHS + 1):
        _, gradient = loss_and_gradient(requests, weights)
        updated = project_weights([weight - LEARNING_RATE * change
                                   for weight, change in zip(weights, gradient)])
        change = math.sqrt(sum((new - old) ** 2 for new, old in zip(updated, weights)))
        weights = updated
        loss, _ = loss_and_gradient(requests, weights)
        log.append({"epoch": epoch, "weights": weights.copy(), "loss": loss,
                    "top1_accuracy": accuracy(requests, weights)})
        stable_epochs = stable_epochs + 1 if change < CONVERGENCE_TOLERANCE else 0
        if stable_epochs >= CONVERGENCE_PATIENCE:
            converged = True
            break
    return weights, log, converged


def evaluate(requests, weights):
    choices = [min(range(len(request["candidates"])),
                   key=scores_for(request, weights).__getitem__) for request in requests]
    accuracy_value = sum(chosen == request["chosen_idx"]
                         for chosen, request in zip(choices, requests)) / len(requests)
    mean_time = sum(request["candidates"][choice]["ratio"]
                    for choice, request in zip(choices, requests)) / len(requests)
    return {"top1_accuracy": accuracy_value,
            "simulated_abandonment_rate": 1 - accuracy_value,
            "mean_recommended_T_over_T_min": mean_time}


def print_training_log(log):
    print("Training log: epoch | weights [w1, w2, w3] | loss | top-1 accuracy")
    for row in log:
        weights = ", ".join(f"{value:.4f}" for value in row["weights"])
        print(f"{row['epoch']:>3} | [{weights}] | {row['loss']:.6f} | "
              f"{row['top1_accuracy'] * 100:6.2f}%")


def main():
    train_requests, held_out = generate_data()
    weights, log, converged = train(train_requests)
    before = evaluate(held_out, PRIOR)
    after = evaluate(held_out, weights)
    print_training_log(log)
    print("\nHeld-out comparison (80 requests)")
    print("Policy       Weights [w1, w2, w3]       Top-1 accuracy   Simulated abandonment   Mean T/T_min")
    for name, policy_weights, metrics in (("Prior", PRIOR, before), ("Optimized", weights, after)):
        weight_text = ", ".join(f"{value:.4f}" for value in policy_weights)
        print(f"{name:<12} [{weight_text}]   {metrics['top1_accuracy'] * 100:>7.2f}%"
              f"             {metrics['simulated_abandonment_rate'] * 100:>7.2f}%"
              f"                 {metrics['mean_recommended_T_over_T_min']:.4f}")

    report = {
        "experiment": "controlled_synthetic_route_weight_calibration",
        "seed": SEED,
        "data": {"request_count": REQUESTS, "train_requests": len(train_requests),
                 "held_out_requests": len(held_out), "candidates_per_request": [3, 4],
                 "time_feature": "total_time_s / per_request_T_min_s",
                 "latent_choice_weights": LATENT_WEIGHTS,
                 "gaussian_score_noise_stddev": 0.035},
        "optimizer": {"method": "projected_gradient_descent",
                      "beta": BETA, "l2_lambda": L2,
                      "learning_rate": LEARNING_RATE, "max_epochs": MAX_EPOCHS,
                      "epochs_run": len(log) - 1, "converged": converged,
                      "convergence_tolerance": CONVERGENCE_TOLERANCE,
                      "convergence_patience": CONVERGENCE_PATIENCE,
                      "weight_floor": WEIGHT_FLOOR},
        "initial_weights": PRIOR,
        "optimized_weights": weights,
        "training_log": log,
        "held_out_evaluation": {"prior": before, "optimized": after,
                                "accuracy_change": after["top1_accuracy"] - before["top1_accuracy"],
                                "abandonment_rate_change": after["simulated_abandonment_rate"]
                                - before["simulated_abandonment_rate"],
                                "mean_T_over_T_min_change": after["mean_recommended_T_over_T_min"]
                                - before["mean_recommended_T_over_T_min"]},
        "metric_definitions": {
            "simulated_abandonment_rate": "fraction of held-out top recommendations that differ from chosen_idx",
            "mean_recommended_T_over_T_min": "mean normalized journey time for held-out top recommendations",
        },
        "limitation": "Controlled synthetic choices encode a known latent preference; these metrics do not establish real-driver behavior or justify runtime policy changes.",
    }
    output = Path(__file__).resolve().parents[1] / "weights_calibration_report.json"
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"\nReport saved to {output}")


if __name__ == "__main__":
    main()
