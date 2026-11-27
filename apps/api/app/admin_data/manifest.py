"""Provenance manifest that must accompany every dataset file.

The manifest is a small JSON file written by the person importing the data. It records where the
data came from and under which licence. Nothing is guessed or defaulted: a missing licence or
source date means the import is refused.

Example (placeholders only; use the real values from the publisher's page):

    {
      "publisher": "<organisation that published the dataset>",
      "dataset_name": "<dataset title>",
      "version_label": "<version or release label>",
      "code_system": "<UPPER_SNAKE name of the identifier scheme>",
      "source_date": "YYYY-MM-DD",
      "source_url": "https://...",
      "license_name": "<licence name>",
      "license_url": "https://...",
      "attribution_text": "<credit line the licence requires, if any>",
      "expected_sha256": "<optional 64 hex chars published by the source>"
    }
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.admin_data.models import CODE_SYSTEM_REGEX

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_URL = re.compile(r"^https?://\S+$")


class ManifestError(ValueError):
    """The manifest file is missing, unreadable or invalid."""


class DatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    publisher: str = Field(min_length=1)
    dataset_name: str = Field(min_length=1)
    version_label: str = Field(min_length=1)
    code_system: str = Field(min_length=1, max_length=32, pattern=CODE_SYSTEM_REGEX)
    source_date: date
    source_url: str | None = None
    license_name: str = Field(min_length=1)
    license_url: str | None = None
    attribution_text: str | None = None
    expected_sha256: str | None = None

    @field_validator("source_date")
    @classmethod
    def _not_in_the_future(cls, value: date) -> date:
        if value > datetime.now(UTC).date():
            raise ValueError("source_date cannot be in the future")
        return value

    @field_validator("source_url", "license_url")
    @classmethod
    def _http_url(cls, value: str | None) -> str | None:
        if value is not None and not _URL.match(value):
            raise ValueError("must be an http(s) URL")
        return value

    @field_validator("expected_sha256")
    @classmethod
    def _sha256_hex(cls, value: str | None) -> str | None:
        if value is not None:
            value = value.lower()
            if not _SHA256.match(value):
                raise ValueError("must be 64 hexadecimal characters")
        return value

    @field_validator("attribution_text")
    @classmethod
    def _blank_to_none(cls, value: str | None) -> str | None:
        return value or None


def load_manifest(path: str | Path) -> DatasetManifest:
    """Read and validate a manifest file; raise ManifestError with a readable message."""
    try:
        raw: Any = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ManifestError("manifest must be a JSON object")
    try:
        return DatasetManifest.model_validate(raw)
    except ValueError as exc:  # pydantic.ValidationError subclasses ValueError
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'manifest'}: {e['msg']}"
            for e in getattr(exc, "errors", lambda: [])()
        )
        raise ManifestError(problems or str(exc)) from exc
