"""Deferred live occurrence adapters (GBIF, ALA).

EarlyDesign.md section 6.4 requires the provider interfaces to exist now
while forbidding a hard dependency on live network access. These classes
implement :class:`OccurrenceProvider` structurally but always answer
``provider_not_configured`` - selecting one never crashes startup, and it
never silently falls back to fixture data either.

When the project owner supplies an approved endpoint and credentials, the
integration task is limited to: reading the API key from the environment
variable named in :class:`~s3_ecological.settings.S3Settings` (never from a
committed file), issuing a bounded, retried HTTP request, and mapping the
response into :class:`RawOccurrenceRecord` - the domain layers above this
adapter do not change.
"""

from __future__ import annotations

from s3_ecological.interfaces.occurrence import (
    OccurrenceProvider,
    OccurrenceQuery,
    RawOccurrenceRecord,
)
from s3_ecological.schemas.common import Issue, ToolResult
from s3_ecological.schemas.enums import IssueCode, ToolStatus


class _DeferredLiveOccurrenceProvider(OccurrenceProvider):
    """Shared behavior for not-yet-implemented live occurrence adapters."""

    source_name: str = "unconfigured"

    def __init__(self, base_url: str | None = None, api_key_env_var: str | None = None):
        self.base_url = base_url
        self.api_key_env_var = api_key_env_var

    def query(self, query: OccurrenceQuery) -> ToolResult[list[RawOccurrenceRecord]]:
        return ToolResult(
            status=ToolStatus.PROVIDER_NOT_CONFIGURED,
            data=None,
            errors=[
                Issue(
                    code=IssueCode.PROVIDER_NOT_CONFIGURED,
                    message=(
                        f"{self.source_name} live occurrence adapter is a deferred "
                        "integration; no endpoint or credentials are configured"
                    ),
                    component="occurrence",
                    retryable=False,
                )
            ],
        )


class LiveGbifOccurrenceProvider(_DeferredLiveOccurrenceProvider):
    source_name = "GBIF"


class LiveAlaOccurrenceProvider(_DeferredLiveOccurrenceProvider):
    source_name = "ALA"
