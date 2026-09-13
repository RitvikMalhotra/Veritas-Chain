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

    # Mention defaults, keyed by "mention_" + MentionMethod value.
    mention_regex: float = Field(0.95, ge=0.0, le=1.0)  # deterministic pattern match, not planned for measurement
    mention_spacy_ner: float = Field(0.6, ge=0.0, le=1.0)  # TODO: unvalidated prior, measure against Phase 1 ground truth

    def edge_default(self, method: str) -> float:
        return getattr(self, method)

    def mention_default(self, method: str) -> float:
        return getattr(self, f"mention_{method}")


@lru_cache
def get_confidence_settings() -> ConfidenceSettings:
    # Cached: env vars are read once per process (tests call cache_clear()).
    return ConfidenceSettings()
