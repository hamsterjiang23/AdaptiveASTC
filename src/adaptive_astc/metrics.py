"""Compatibility aliases for the original metric functions."""

from adaptive_astc.calibration.temperature import TemperatureCalibrator
from adaptive_astc.evaluation.metrics import ClassificationMetrics

probability_metrics = ClassificationMetrics.compute
fit_temperature = TemperatureCalibrator.fit
