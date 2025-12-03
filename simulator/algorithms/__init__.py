"""Automatic Python configuration file."""

__version__ = "1.1.0"

# Importing resource management policies
from .toy_algorithm import toy_algorithm
from .trust_edge_v1 import trust_edge_v1
from .trust_edge_v2 import trust_edge_v2
from .trust_edge_v3 import trust_edge_v3
from .trust_edge_original import trust_edge_original
from .kubernetes_inspired import kubernetes_inspired
from .trust_edge_v3 import add_to_waiting_queue

__all__ = [
    "toy_algorithm",
    "trust_edge_original",
    "trust_edge_v1",
    "trust_edge_v2",
    "trust_edge_v3",
    "kubernetes_inspired",
    "add_to_waiting_queue",
]