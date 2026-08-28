# models/

Reserved for future environmental-suitability model artifacts (e.g. a
trained SDM/niche model backing `suitability/`). Milestone 0/1 ships only
`suitability/null_model.py`, which returns `suitability=None` for every
candidate with a `component_unavailable` warning and never reads from this
directory — no model artifact is required for the current prototype.

Any future model file added here must document its training data,
provenance, and version in a versioned config field consumed by
`interfaces/suitability.py`'s `SuitabilityModel` Protocol, per
EarlyDesign.md's provenance requirements. No model artifact is committed in
this prototype.
