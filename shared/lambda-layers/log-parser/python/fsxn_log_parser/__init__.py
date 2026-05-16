"""FSx ONTAP Log Parser Lambda Layer.

Provides utilities for parsing FSx for NetApp ONTAP audit logs
in both EVTX and JSON formats.
"""

__version__ = "0.1.0"

from .parser import parse_evtx, parse_json_log, normalize_event
