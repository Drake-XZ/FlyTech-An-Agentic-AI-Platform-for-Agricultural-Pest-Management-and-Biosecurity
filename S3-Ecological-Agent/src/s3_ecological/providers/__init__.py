"""Concrete adapters for the taxonomy and occurrence Protocols.

Every adapter here implements a Protocol from ``interfaces/`` and is
interchangeable through ``providers.factory``. Live network adapters
(``occurrence_live_deferred.py``) are explicitly marked deferred and never
required to run the offline prototype.
"""
