"""CLI behaviour that needs no database."""

import json

import pytest

from app.admin_data.cli import main
from app.admin_data.validation import CSV_COLUMNS
from app.config import get_settings
from app.db.session import get_engine

HEADER = ",".join(CSV_COLUMNS)
GOOD = HEADER + "\nstate_ut,01,Synthetic State A,,\ndistrict,001,Synthetic District,state_ut,01\n"
BAD = HEADER + "\nstate_ut,1.0,Synthetic State A,,\n"

MANIFEST = {
    "publisher": "Synthetic Test Publisher",
    "dataset_name": "Synthetic Dataset",
    "version_label": "synthetic-v1",
    "code_system": "TEST_SYSTEM",
    "source_date": "2020-01-01",
    "license_name": "Synthetic Test Licence",
}


@pytest.fixture
def no_database(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    get_settings.cache_clear()
    get_engine.cache_clear()
    yield
    get_settings.cache_clear()
    get_engine.cache_clear()


def test_validate_good_file_exits_zero(tmp_path, capsys):
    f = tmp_path / "units.csv"
    f.write_text(GOOD, encoding="utf-8")
    assert main(["validate", str(f)]) == 0
    assert "VALID" in capsys.readouterr().out


def test_validate_bad_file_exits_one_and_lists_the_problem(tmp_path, capsys):
    f = tmp_path / "units.csv"
    f.write_text(BAD, encoding="utf-8")
    assert main(["validate", str(f)]) == 1
    out = capsys.readouterr().out
    assert "REJECTED" in out and "code.format" in out and "line 2" in out


def test_validate_can_write_a_json_report(tmp_path):
    f = tmp_path / "units.csv"
    f.write_text(BAD, encoding="utf-8")
    report = tmp_path / "report.json"
    main(["validate", str(f), "--report-file", str(report)])
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["ok"] is False and data["issues"][0]["rule"] == "code.format"


def test_validate_honours_fixed_width_rules(tmp_path):
    f = tmp_path / "units.csv"
    f.write_text(HEADER + "\nstate_ut,1,Synthetic State,,\n", encoding="utf-8")
    assert main(["validate", str(f)]) == 0
    assert main(["validate", str(f), "--code-width", "state_ut=2"]) == 1


def test_validate_missing_file_is_a_usage_error(tmp_path):
    assert main(["validate", str(tmp_path / "nope.csv")]) == 2


def test_import_without_database_url_explains_and_exits_two(tmp_path, capsys, no_database):
    f = tmp_path / "units.csv"
    f.write_text(GOOD, encoding="utf-8")
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps(MANIFEST), encoding="utf-8")
    assert main(["import", str(f), "--manifest", str(m)]) == 2
    assert "DATABASE_URL is not set" in capsys.readouterr().err


def test_import_with_invalid_manifest_is_refused_before_touching_anything(tmp_path, capsys):
    f = tmp_path / "units.csv"
    f.write_text(GOOD, encoding="utf-8")
    m = tmp_path / "manifest.json"
    m.write_text(json.dumps({**MANIFEST, "license_name": ""}), encoding="utf-8")
    assert main(["import", str(f), "--manifest", str(m)]) == 2
    assert "Manifest problem" in capsys.readouterr().err


def test_status_without_database_url_exits_two(capsys, no_database):
    assert main(["status"]) == 2


def test_approve_requires_a_reviewer_argument():
    with pytest.raises(SystemExit):
        main(["approve", "1"])


def test_malformed_code_width_argument_is_rejected(tmp_path):
    f = tmp_path / "units.csv"
    f.write_text(GOOD, encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["validate", str(f), "--code-width", "state_ut"])
