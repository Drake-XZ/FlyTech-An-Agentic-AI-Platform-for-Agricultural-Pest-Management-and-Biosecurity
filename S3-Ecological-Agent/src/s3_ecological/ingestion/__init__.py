"""Offline occurrence snapshot ingestion (Milestone 1.5).

Converts a locally-held GBIF, ALA, generic Darwin Core, or canonical JSON
occurrence export into the deterministic snapshot bundle consumed by
:mod:`s3_ecological.providers`. Contains no network access and no
dependency on the optional ``agent``/``api`` extras.
"""
