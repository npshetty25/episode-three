"""Regression metrics for Model A (points on the 0-100 scale). Pure functions, numpy only."""
import numpy as np


def _arrays(y_true, y_pred):
    y_true, y_pred = np.asarray(y_true, dtype=float), np.asarray(y_pred, dtype=float)
    if y_true.shape != y_pred.shape or y_true.ndim != 1 or y_true.size == 0:
        raise ValueError("y_true and y_pred must be non-empty 1-D arrays of the same length")
    return y_true, y_pred


def mae(y_true, y_pred):
    """Mean absolute error: the average miss, in score points. The primary metric."""
    y_true, y_pred = _arrays(y_true, y_pred)
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    """Root mean squared error: like MAE but punishes big misses more."""
    y_true, y_pred = _arrays(y_true, y_pred)
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def pct_within(y_true, y_pred, k=3):
    """Share of predictions within +-k points of the truth, as a percentage (a miss of exactly k counts)."""
    y_true, y_pred = _arrays(y_true, y_pred)
    return float(100 * np.mean(np.abs(y_true - y_pred) <= k))


def bootstrap_ci(metric, y_true, y_pred, n=1000, seed=42, level=95):
    """Percentile bootstrap confidence interval for a metric.

    Resamples the SHOWS (row pairs) with replacement n times, recomputes the metric each time, and returns
    (low, high) = the middle `level` percent of those values. Seeded, numpy only, so it is reproducible.
    """
    y_true, y_pred = _arrays(y_true, y_pred)
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(y_true), size=(n, len(y_true)))
    values = np.array([metric(y_true[i], y_pred[i]) for i in indices])
    tail = (100 - level) / 2
    low, high = np.percentile(values, [tail, 100 - tail])
    return float(low), float(high)
