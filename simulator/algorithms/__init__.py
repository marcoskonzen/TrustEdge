"""Automatic Python configuration file."""

__version__ = "1.1.0"

# Importing resource management policies
from .trust_edge import trust_edge

__all__ = [
    "trust_edge",
]
