"""Automatic Python configuration file."""

__version__ = "1.1.0"

# Importing simulator extensions
from .base_failure_model import BaseFailureGroupModel
from .edge_server_extensions import edge_server_step, failure_history
from .application_extensions import application_step, availability_status

__all__ = [
    "BaseFailureGroupModel",
    "edge_server_step",
    "failure_history",
    "application_step",
    "availability_status",
]
