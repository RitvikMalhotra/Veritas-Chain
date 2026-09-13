"""Configurable confidence defaults. Override any value with an env var, e.g. VERITAS_CONF_TEXT_PATTERN=0.8."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfidenceSettings(BaseSettings):
    """Ordinal trust weights in [0, 1], not calibrated probabilities. See schema.md section 4."""

    model_config = SettingsConfigDict(env_prefix="VERITAS_CONF_")

    # Edge defaults, keyed by ExtractionMethod value.
    structured: float = Field(1.0, ge=0.0, le=1.0)
    text_pattern: float = Field(0.7, ge=0.0, le=1.0)  # TODO: unvalidated prior, measure against Phase 1 ground truth
    text_cooccurrence: float = Field(0.4, ge=0.0, le=1.0)  # TODO: unvalidated prior, measure against Phase 1 ground truth

    # Mention defaults. Regex has one value; spaCy NER has one per label.
    mention_regex: float = Field(0.95, ge=0.0, le=1.0)  # deterministic pattern match, not planned for measurement
    # Measured in Phase 2: en_core_web_md lenient precision pooled over seeds 42 and 7. Upper bounds (clean templated text).
    mention_spacy_ner_person: float = Field(0.92, ge=0.0, le=1.0)  # 146/159
    mention_spacy_ner_location: float = Field(0.97, ge=0.0, le=1.0)  # 65/67
    mention_spacy_ner_organization: float = Field(0.29, ge=0.0, le=1.0)  # 34/116

    def edge_default(self, method: str) -> float:
        return getattr(self, method)

    def mention_default(self, method: str, node_type: str) -> float:
        # These values were measured for en_core_web_md; a different model would need re-measuring.
        name = "mention_regex" if method == "regex" else f"mention_{method}_{node_type.lower()}"
        return getattr(self, name)


@lru_cache
def get_confidence_settings() -> ConfidenceSettings:
    # Cached: env vars are read once per process (tests call cache_clear()).
    return ConfidenceSettings()
