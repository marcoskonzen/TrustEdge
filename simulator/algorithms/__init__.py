"""Automatic Python configuration file."""

__version__ = "1.1.0"

# Importing resource management policies
from .toy_algorithm import toy_algorithm
from .trust_edge import trust_edge
from .trust_edge_original import trust_edge_original

__all__ = [
    "toy_algorithm",
    "trust_edge",
    "trust_edge_original",
]
