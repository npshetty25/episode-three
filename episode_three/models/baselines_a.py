"""The three Model A baselines. Plain functions; the only class used is scikit-learn's LinearRegression.

B1  "the finale equals the episode-3 score"      needs no fitting
B2  "everything gets the training-set mean"      fitted on the TRAIN labels only
B3  linear regression of the label on ep3_score  fitted on TRAIN only

Every model built later must beat these on validation, on exactly the same footing.
"""
import numpy as np
from sklearn.linear_model import LinearRegression


def b1_predict(frame):
    """B1: predict the episode-3 score itself."""
    return frame["ep3_score"].to_numpy(dtype=float)


def b2_fit(train_frame):
    """B2: the mean of the TRAIN labels. It takes the train frame and nothing else, so no other label can reach it."""
    return float(train_frame["y"].mean())


def b2_predict(train_mean, frame):
    return np.full(len(frame), train_mean, dtype=float)


def b3_fit(train_frame):
    """B3: y = intercept + coef * ep3_score, fitted on the train frame only."""
    return LinearRegression().fit(train_frame[["ep3_score"]].to_numpy(dtype=float), train_frame["y"].to_numpy(dtype=float))


def b3_predict(model, frame):
    return model.predict(frame[["ep3_score"]].to_numpy(dtype=float))


def run_baselines(train_frame, validation_frame):
    """Fit B2 and B3 on train; return {name: {split: predictions}} and the fitted pieces."""
    train_mean, b3 = b2_fit(train_frame), b3_fit(train_frame)
    predictions = {
        "B1": {"train": b1_predict(train_frame), "validation": b1_predict(validation_frame)},
        "B2": {"train": b2_predict(train_mean, train_frame), "validation": b2_predict(train_mean, validation_frame)},
        "B3": {"train": b3_predict(b3, train_frame), "validation": b3_predict(b3, validation_frame)},
    }
    return predictions, {"train_mean": train_mean, "coefficient": float(b3.coef_[0]), "intercept": float(b3.intercept_)}
