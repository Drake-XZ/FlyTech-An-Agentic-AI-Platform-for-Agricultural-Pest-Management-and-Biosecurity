"""Protocol interfaces for every replaceable S3 boundary: taxonomy, occurrence,
geographic priors, environmental suitability, risk policy, and the optional
LLM provider. Concrete adapters live in ``providers/`` and the deterministic
domain packages; nothing outside this package should import a concrete
provider class directly when a Protocol is available.
"""
