"""Automatic Python configuration file."""

__version__ = "1.1.0"

# Importing resource management policies
from .trust_edge import trust_edge_v3
from .kubernetes_inspired import kubernetes_inspired
from .trust_edge import add_to_waiting_queue
from .First_Fit import first_fit_baseline

__all__ = [
    "trust_edge_v3",
    "kubernetes_inspired",
    "add_to_waiting_queue",
    "first_fit_baseline",
]