"""Beta-binomial smoothing of isotonic knot y-values."""
from __future__ import annotations


def smooth_isotonic_knots(
    x: list[float], y: list[float], n_per_knot: list[int],
    *, prior_alpha: float = 1.0, prior_beta: float = 1.0,
) -> list[float]:
    """Pull each knot's y toward the prior by effective sample size.

    Formula:  y_smooth = (n * y + alpha) / (n + alpha + beta)

    With Beta(alpha, beta) prior on the underlying Bernoulli, this is the
    posterior mean of the success probability given n trials and n*y successes.
    """
    if len(x) != len(y) or len(y) != len(n_per_knot):
        raise ValueError("x, y, n_per_knot must be same length")
    out: list[float] = []
    for yi, ni in zip(y, n_per_knot):
        numerator = ni * yi + prior_alpha
        denominator = ni + prior_alpha + prior_beta
        out.append(numerator / denominator)
    return out
