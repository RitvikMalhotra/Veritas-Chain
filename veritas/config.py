"""Configurable confidence defaults. Override any value with an env var, e.g. VERITAS_CONF_TEXT_PATTERN=0.8."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfidenceSettings(BaseSettings):
    """Ordinal trust weights in [0, 1], not calibrated probabilities. See schema.md section 4."""

    model_config = SettingsConfigDict(env_prefix="VERITAS_CONF_")

    # Edge defaults, keyed by ExtractionMethod value.
    structured: float = Field(1.0, ge=0.0, le=1.0)
    # Checked in Phase 3 and deliberately kept (approved): template text scored 170/170 and 73/78 with gold entities,
    # but that evidence is circular and the out-of-template probe fell to 3/4, so it can't justify higher trust.
    text_pattern: float = Field(0.7, ge=0.0, le=1.0)
    text_cooccurrence: float = Field(0.4, ge=0.0, le=1.0)

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


class AnalyticsSettings(BaseSettings):
    """Phase 4 thresholds. All are unvalidated analyst choices; override with env vars, e.g. VERITAS_ANALYTICS_SPIKE_MIN_RATIO=3."""

    model_config = SettingsConfigDict(env_prefix="VERITAS_ANALYTICS_")

    # Call-spike window. Deliberately NOT the generator's planted 48h-before / 12h-after window, to avoid a circular test.
    spike_hours_before: float = Field(72, gt=0)
    spike_hours_after: float = Field(24, ge=0)
    spike_min_calls: int = Field(5, ge=1)  # ignore tiny counts
    spike_min_ratio: float = Field(2.0, gt=1)  # observed / expected
    spike_max_p_value: float = Field(0.001, gt=0, lt=1)  # Poisson upper tail; strict because ~24 events are tested
    # Which calls count. named_phones = any call on a named person's phone (Phase 4 as committed);
    # among_named = only calls between two different named people (revision R1, adopted only if it passes on seed 11).
    spike_scope: Literal["named_phones", "among_named"] = "named_phones"

    # Circular money flow: a time-ordered loop with small deductions per hop (layering typology).
    cycle_min_length: int = Field(3, ge=3)  # 2-cycles are ordinary repayments
    cycle_max_length: int = Field(6, ge=3)
    cycle_max_hop_gap_days: float = Field(7, gt=0)
    cycle_min_amount_retention: float = Field(0.85, gt=0, le=1)  # each hop keeps at least 85% of the previous amount

    louvain_seed: int = 42  # Louvain is randomised; the seed makes runs repeatable
    louvain_resolution: float = Field(1.0, gt=0)
    # Revision R2: split a community again only if Louvain inside it reaches this modularity (Newman-Girvan rule of thumb).
    community_split_min_modularity: float = Field(0.3, gt=0, lt=1)
