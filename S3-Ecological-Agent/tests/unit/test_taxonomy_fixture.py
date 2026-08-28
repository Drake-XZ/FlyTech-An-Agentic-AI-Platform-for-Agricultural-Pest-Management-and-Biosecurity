"""Unit tests for the fixture-backed taxonomy provider and resolver."""

from __future__ import annotations

from s3_ecological.interfaces.taxonomy import TaxonomyQuery
from s3_ecological.providers.taxonomy_fixture import FixtureTaxonomyProvider
from s3_ecological.schemas.enums import IssueCode, ToolStatus
from s3_ecological.taxonomy.resolve import resolve_candidate_names

PROVIDER = FixtureTaxonomyProvider()


def test_direct_match_resolves_successfully():
    result = PROVIDER.resolve(TaxonomyQuery(name="Bactrocera"))
    assert result.status == ToolStatus.SUCCESS
    assert result.data is not None
    assert result.data.resolved_taxon is not None
    assert result.data.resolved_taxon.scientific_name == "Bactrocera"
    assert result.data.resolved_taxon.ambiguous is False


def test_match_is_case_insensitive():
    result = PROVIDER.resolve(TaxonomyQuery(name="bactrocera"))
    assert result.status == ToolStatus.SUCCESS
    assert result.data is not None
    assert result.data.resolved_taxon is not None
    assert result.data.resolved_taxon.scientific_name == "Bactrocera"


def test_synonym_resolves_to_accepted_name_with_synonym_of_set():
    result = PROVIDER.resolve(TaxonomyQuery(name="Dacus"))
    assert result.status == ToolStatus.SUCCESS
    assert result.data is not None
    assert result.data.resolved_taxon is not None
    assert result.data.resolved_taxon.scientific_name == "Bactrocera"
    assert result.data.resolved_taxon.synonym_of == "Dacus"


def test_ambiguous_match_returns_partial_status_with_candidate_matches():
    result = PROVIDER.resolve(TaxonomyQuery(name="Anastrepha sp."))
    assert result.status == ToolStatus.PARTIAL
    assert result.data is not None
    assert result.data.resolved_taxon is not None
    assert result.data.resolved_taxon.ambiguous is True
    assert result.data.candidate_matches == ["Anastrepha"]


def test_unknown_name_returns_partial_status_with_no_resolved_taxon_and_warning():
    result = PROVIDER.resolve(TaxonomyQuery(name="Nonexistent genus"))
    assert result.status == ToolStatus.PARTIAL
    assert result.data is not None
    assert result.data.resolved_taxon is None
    assert result.warnings[0].code == IssueCode.TAXON_NOT_FOUND
    assert result.warnings[0].retryable is False


def test_unknown_name_never_invents_a_resolution_via_partial_string_match():
    result = PROVIDER.resolve(TaxonomyQuery(name="Bactro"))
    assert result.data is not None
    assert result.data.resolved_taxon is None


def test_resolve_candidate_names_resolves_each_distinct_name_once():
    results = resolve_candidate_names(["Bactrocera", "Ceratitis", "Bactrocera"], PROVIDER)
    assert set(results.keys()) == {"Bactrocera", "Ceratitis"}
    bactrocera_data = results["Bactrocera"].data
    assert bactrocera_data is not None
    assert bactrocera_data.resolved_taxon is not None
    assert bactrocera_data.resolved_taxon.scientific_name == "Bactrocera"


def test_resolve_candidate_names_preserves_first_seen_order():
    results = resolve_candidate_names(["Rhagoletis", "Anastrepha", "Rhagoletis"], PROVIDER)
    assert list(results.keys()) == ["Rhagoletis", "Anastrepha"]
