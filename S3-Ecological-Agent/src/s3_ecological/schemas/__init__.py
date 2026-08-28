"""Pydantic v2 schemas: the canonical S3 request, response, and tool contracts.

Every public model here is exported as JSON Schema by
``scripts/export_json_schemas.py`` and must remain framework-neutral - no
PydanticAI, FastAPI, or provider-SDK types may appear in this package.
"""
