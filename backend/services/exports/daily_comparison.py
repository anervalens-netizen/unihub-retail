"""Daily-comparison configuration boundary; rendering remains worker-owned."""
from .catalog import COMPARISON_LEVELS, DAILY_EVOLUTION_METRICS


def comparison_level_config(levels: list[str]) -> dict[str, dict[str, object]]:
    return {level: {"label": str(COMPARISON_LEVELS[level]["label"]), "sheet": str(COMPARISON_LEVELS[level]["sheet"]), "dimensions": list(COMPARISON_LEVELS[level]["dimensions"])} for level in levels}


def metric_labels(metrics: list[str]) -> dict[str, str]:
    return {metric: DAILY_EVOLUTION_METRICS[metric].label for metric in metrics}
