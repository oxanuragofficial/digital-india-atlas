import json
from datetime import UTC, datetime, timedelta

import pytest

from app.admin_data.manifest import DatasetManifest, ManifestError, load_manifest

VALID = {
    "publisher": "Synthetic Test Publisher",
    "dataset_name": "Synthetic Dataset",
    "version_label": "synthetic-v1",
    "code_system": "TEST_SYSTEM",
    "source_date": "2020-01-31",
    "source_url": "https://example.test/dataset",
    "license_name": "Synthetic Test Licence",
    "license_url": "https://example.test/licence",
    "attribution_text": "Synthetic credit line",
}


def write(tmp_path, payload) -> str:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def test_valid_manifest_loads(tmp_path):
    m = load_manifest(write(tmp_path, VALID))
    assert m.publisher == "Synthetic Test Publisher"
    assert m.source_date.isoformat() == "2020-01-31"
    assert m.expected_sha256 is None


def test_optional_fields_may_be_omitted(tmp_path):
    minimal = {
        k: v for k, v in VALID.items() if k not in {"source_url", "license_url", "attribution_text"}
    }
    m = load_manifest(write(tmp_path, minimal))
    assert m.source_url is None and m.license_url is None and m.attribution_text is None


@pytest.mark.parametrize(
    "missing",
    ["publisher", "dataset_name", "version_label", "code_system", "source_date", "license_name"],
)
def test_required_fields_cannot_be_omitted(tmp_path, missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    with pytest.raises(ManifestError, match=missing):
        load_manifest(write(tmp_path, payload))


@pytest.mark.parametrize("field", ["publisher", "dataset_name", "version_label", "license_name"])
def test_blank_required_text_is_rejected(tmp_path, field):
    with pytest.raises(ManifestError):
        load_manifest(write(tmp_path, {**VALID, field: "   "}))


def test_licence_is_mandatory_so_unlicensed_data_cannot_be_imported(tmp_path):
    with pytest.raises(ManifestError, match="license_name"):
        load_manifest(write(tmp_path, {**VALID, "license_name": ""}))


def test_future_source_date_rejected(tmp_path):
    tomorrow = (datetime.now(UTC) + timedelta(days=2)).date().isoformat()
    with pytest.raises(ManifestError, match="future"):
        load_manifest(write(tmp_path, {**VALID, "source_date": tomorrow}))


@pytest.mark.parametrize("bad", ["2020-13-01", "31/01/2020", "yesterday", ""])
def test_invalid_source_date_rejected(tmp_path, bad):
    with pytest.raises(ManifestError, match="source_date"):
        load_manifest(write(tmp_path, {**VALID, "source_date": bad}))


@pytest.mark.parametrize("bad", ["test_system", "1TEST", "TEST SYSTEM", "TEST-SYSTEM", "X" * 33])
def test_code_system_must_be_upper_snake(tmp_path, bad):
    with pytest.raises(ManifestError, match="code_system"):
        load_manifest(write(tmp_path, {**VALID, "code_system": bad}))


@pytest.mark.parametrize("field", ["source_url", "license_url"])
@pytest.mark.parametrize("bad", ["ftp://example.test", "example.test", "javascript:alert(1)"])
def test_urls_must_be_http(tmp_path, field, bad):
    with pytest.raises(ManifestError, match=field):
        load_manifest(write(tmp_path, {**VALID, field: bad}))


def test_expected_sha256_must_be_hex_and_is_lowercased(tmp_path):
    m = load_manifest(write(tmp_path, {**VALID, "expected_sha256": "A" * 64}))
    assert m.expected_sha256 == "a" * 64
    for bad in ["abc", "g" * 64, "a" * 63]:
        with pytest.raises(ManifestError, match="expected_sha256"):
            load_manifest(write(tmp_path, {**VALID, "expected_sha256": bad}))


def test_unknown_fields_are_rejected_so_typos_are_not_silently_ignored(tmp_path):
    with pytest.raises(ManifestError, match="licence_name"):
        load_manifest(write(tmp_path, {**VALID, "licence_name": "typo"}))


def test_bad_files_give_readable_errors(tmp_path):
    with pytest.raises(ManifestError, match="not found"):
        load_manifest(tmp_path / "nope.json")
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        load_manifest(broken)
    listy = tmp_path / "list.json"
    listy.write_text("[]", encoding="utf-8")
    with pytest.raises(ManifestError, match="JSON object"):
        load_manifest(listy)


def test_utf8_bom_is_tolerated(tmp_path):
    path = tmp_path / "bom.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps(VALID).encode())
    assert isinstance(load_manifest(path), DatasetManifest)
