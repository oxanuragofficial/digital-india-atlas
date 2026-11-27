"""Import validation rules. All identifiers and names are SYNTHETIC."""

from __future__ import annotations

import pytest

from app.admin_data.validation import (
    CSV_COLUMNS,
    ParsedUnit,
    ValidationReport,
    normalise_name,
    validate_units_csv,
)

HEADER = ",".join(CSV_COLUMNS)

VALID_ROWS = [
    "state_ut,01,Synthetic State A,,",
    "district,001,Synthetic District A1,state_ut,01",
    "subdistrict,00001,Synthetic Subdistrict A1a,district,001",
    "locality,000001,Synthetic Locality A1a-i,subdistrict,00001",
]


def csv_text(*rows: str, header: str = HEADER) -> bytes:
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


def check(*rows: str, header: str = HEADER, **kwargs) -> tuple[ValidationReport, list[ParsedUnit]]:
    return validate_units_csv(csv_text(*rows, header=header), **kwargs)


def rules(report: ValidationReport, severity: str = "error") -> list[str]:
    return [i.rule for i in report.issues if i.severity == severity]


# ---- the happy path ---------------------------------------------------------------------


def test_valid_file_passes_with_no_issues():
    report, units = check(*VALID_ROWS)
    assert report.ok and report.issues == []
    assert report.row_count == 4
    assert report.counts_by_level == {
        "state_ut": 1,
        "district": 1,
        "subdistrict": 1,
        "locality": 1,
    }
    assert len(units) == 4


def test_parents_are_ordered_before_children_even_if_the_file_lists_them_last():
    report, units = check(*reversed(VALID_ROWS))
    assert report.ok
    assert [u.level for u in units] == ["state_ut", "district", "subdistrict", "locality"]


def test_a_unit_can_reference_a_parent_defined_later_in_the_file():
    report, _ = check(VALID_ROWS[1], VALID_ROWS[0])
    assert report.ok


def test_file_may_be_a_path_not_just_bytes(tmp_path):
    path = tmp_path / "units.csv"
    path.write_bytes(csv_text(*VALID_ROWS))
    report, units = validate_units_csv(path)
    assert report.ok and len(units) == 4


def test_bom_crlf_quotes_and_unicode_are_handled():
    raw = (
        "﻿" + HEADER + "\r\n"
        'state_ut,01,"Synthetic, State ""A""",,\r\n'
        "district,001,परीक्षण जिला,state_ut,01\r\n"
        "subdistrict,00001,પરીક્ષણ તાલુકો,district,001\r\n"
    ).encode()
    report, units = validate_units_csv(raw)
    assert report.ok, report.to_text()
    assert units[0].name == 'Synthetic, State "A"'
    assert units[1].name == "परीक्षण जिला"
    assert units[2].name == "પરીક્ષણ તાલુકો"


def test_header_is_case_and_space_tolerant_but_not_order_tolerant():
    report, _ = check(*VALID_ROWS, header=" Level , CODE ,name,parent_level,parent_code")
    assert report.ok


# ---- identifiers: strings, never numbers ---------------------------------------------------


@pytest.mark.parametrize("code", ["0", "00", "007", "000123", "0A1", "A001"])
def test_codes_are_preserved_exactly_as_strings(code):
    report, units = check(f"state_ut,{code},Synthetic State,,")
    assert report.ok
    assert units[0].code == code and isinstance(units[0].code, str)


def test_leading_zeros_survive_for_every_level():
    _, units = check(*VALID_ROWS)
    assert [u.code for u in units] == ["01", "001", "00001", "000001"]
    assert [u.parent_code for u in units] == [None, "01", "001", "00001"]


@pytest.mark.parametrize(
    ("code", "rule"),
    [
        ("", "code.blank"),
        (" 01", "code.whitespace"),
        ("01 ", "code.whitespace"),
        ("1.0", "code.format"),  # a spreadsheet turned the code into a float
        ("1,5", "code.format"),
        ("-1", "code.format"),
        ("A-1", "code.format"),
        ("é1", "code.format"),
        ("1" * 33, "code.format"),
    ],
)
def test_malformed_codes_are_errors_never_silently_fixed(code, rule):
    quoted = f'"{code}"'
    report, units = check(f"state_ut,{quoted},Synthetic State,,")
    assert not report.ok and units == []
    assert rule in rules(report)


def test_codes_differing_only_by_leading_zeros_are_ambiguous():
    report, _ = check("state_ut,7,Synthetic State One,,", "state_ut,007,Synthetic State Two,,")
    assert "code.zero_padding_ambiguous" in rules(report)


def test_zero_ambiguity_is_scoped_to_a_single_level():
    report, _ = check(
        "state_ut,7,Synthetic State,,",
        "district,007,Synthetic District,state_ut,7",
    )
    assert report.ok


def test_codes_are_case_sensitive():
    report, _ = check("state_ut,a1,Synthetic One,,", "state_ut,A1,Synthetic Two,,")
    assert report.ok


def test_fixed_width_rule_catches_stripped_leading_zeros():
    report, _ = check("state_ut,1,Synthetic State,,", code_widths={"state_ut": 2})
    assert "code.width" in rules(report)
    ok, _ = check("state_ut,01,Synthetic State,,", code_widths={"state_ut": 2})
    assert ok.ok


def test_width_rule_applies_only_to_the_configured_level():
    report, _ = check(*VALID_ROWS, code_widths={"state_ut": 2})
    assert report.ok


# ---- names -----------------------------------------------------------------------------------


def test_blank_name_is_an_error():
    report, _ = check("state_ut,01,   ,,")
    assert "name.blank" in rules(report)


def test_overlong_name_is_an_error():
    report, _ = check(f"state_ut,01,{'x' * 301},,")
    assert "name.length" in rules(report)


def test_name_whitespace_is_normalised_with_a_warning_not_an_error():
    report, units = check('state_ut,01,"  Synthetic   State\tA  ",,')
    assert report.ok
    assert units[0].name == "Synthetic State A"
    assert rules(report, "warning") == ["name.normalized"]


def test_normalise_name_applies_nfc():
    decomposed = "é"  # e + combining acute
    assert normalise_name(decomposed) == "é"


@pytest.mark.parametrize("char", ["\x07", "\x1b", "\x0b"])
def test_control_characters_are_rejected(char):
    report, _ = check(f'state_ut,01,"bad{char}name",,')
    assert "row.control_chars" in rules(report)


def test_line_breaks_inside_a_quoted_name_are_collapsed_with_a_warning():
    report, units = check('state_ut,01,"Synthetic\nState",,')
    assert report.ok and units[0].name == "Synthetic State"
    assert "name.normalized" in rules(report, "warning")


def test_a_tab_inside_a_code_is_still_an_error():
    report, _ = check('state_ut,"0\t1",Synthetic,,')
    assert "code.format" in rules(report)


# ---- level and parent rules -----------------------------------------------------------------


def test_unknown_level_is_an_error():
    report, _ = check("planet,01,Synthetic,,")
    assert "level.unknown" in rules(report)


def test_root_level_cannot_have_a_parent():
    report, _ = check("state_ut,01,Synthetic A,,", "state_ut,02,Synthetic B,state_ut,01")
    assert "parent.root_has_parent" in rules(report)


def test_non_root_level_requires_a_parent():
    report, _ = check("district,001,Synthetic District,,")
    assert "parent.missing" in rules(report)


@pytest.mark.parametrize(
    "row", ["district,001,Synthetic D,state_ut,", "district,001,Synthetic D,,01"]
)
def test_parent_fields_must_be_both_set_or_both_empty(row):
    report, _ = check("state_ut,01,Synthetic State,,", row)
    assert "parent.partial" in rules(report)


def test_levels_cannot_be_skipped():
    report, _ = check(
        "state_ut,01,Synthetic State,,",
        "subdistrict,00001,Synthetic Sub,state_ut,01",
    )
    assert "parent.level_not_allowed" in rules(report)


def test_levels_cannot_be_reversed():
    report, _ = check(
        "state_ut,01,Synthetic State,,",
        "district,001,Synthetic District,state_ut,01",
        "state_ut,02,Synthetic State 2,district,001",
    )
    assert "parent.root_has_parent" in rules(report)


def test_unknown_parent_level_is_reported():
    report, _ = check("state_ut,01,Synthetic S,,", "district,001,Synthetic D,galaxy,01")
    assert "parent.level_unknown" in rules(report)


def test_parent_must_exist_in_the_file():
    report, _ = check(
        "state_ut,01,Synthetic State,,",
        "district,001,Synthetic District,state_ut,99",
    )
    assert "parent.not_found" in rules(report)


def test_parent_is_matched_by_level_and_code_not_by_code_alone():
    # code 001 exists, but as a district, not as a state_ut
    report, _ = check(
        "state_ut,01,Synthetic State,,",
        "district,001,Synthetic District,state_ut,01",
        "district,002,Synthetic District 2,state_ut,001",
    )
    assert "parent.not_found" in rules(report)


def test_parent_code_must_match_exactly_including_zeros():
    report, _ = check(
        "state_ut,01,Synthetic State,,",
        "district,001,Synthetic District,state_ut,1",
    )
    assert "parent.not_found" in rules(report)


def test_duplicate_level_and_code_is_an_error_naming_the_first_line():
    report, _ = check("state_ut,01,Synthetic A,,", "state_ut,01,Synthetic B,,")
    [issue] = [i for i in report.issues if i.rule == "unit.duplicate"]
    assert "line 2" in issue.message and issue.line == 3


# ---- file-level problems --------------------------------------------------------------------


@pytest.mark.parametrize(
    "header",
    [
        "level,code,name,parent_level",  # missing column
        HEADER + ",extra",  # unknown column
        "code,level,name,parent_level,parent_code",  # wrong order
        "level,code,name,parent_level,parent_level",  # duplicated column
    ],
)
def test_bad_headers_are_rejected(header):
    report, units = validate_units_csv(csv_text(*VALID_ROWS, header=header))
    assert rules(report) == ["file.header"] and units == []


def test_empty_file_and_header_only_file_are_rejected():
    assert rules(validate_units_csv(b"")[0]) == ["file.empty"]
    assert rules(validate_units_csv((HEADER + "\n").encode())[0]) == ["file.empty"]


def test_invalid_utf8_is_rejected():
    report, _ = validate_units_csv(HEADER.encode() + b"\nstate_ut,01,\xff\xfe,,\n")
    assert rules(report) == ["file.encoding"]


def test_nul_bytes_are_rejected():
    report, _ = validate_units_csv(HEADER.encode() + b"\nstate_ut,01,A\x00B,,\n")
    assert rules(report) == ["file.encoding"]


def test_wrong_number_of_fields_is_reported_with_its_line():
    report, _ = check("state_ut,01,Synthetic State,", "state_ut,02,Synthetic B,,,extra")
    assert [i.line for i in report.errors if i.rule == "row.field_count"] == [2, 3]


def test_blank_lines_are_ignored_with_a_warning():
    report, units = validate_units_csv((HEADER + "\n\nstate_ut,01,Synthetic,,\n\n").encode())
    assert report.ok and len(units) == 1
    assert "row.blank" in rules(report, "warning")


# ---- reporting ------------------------------------------------------------------------------


def test_every_problem_is_reported_not_just_the_first():
    report, _ = check(
        "planet,01,A,,",
        "state_ut,,B,,",
        "state_ut,03, ,,",
        "district,001,D,state_ut,99",
    )
    assert report.error_total >= 4
    assert {"level.unknown", "code.blank", "name.blank"} <= set(rules(report))


def test_issues_carry_line_numbers_with_the_header_as_line_one():
    report, _ = check(VALID_ROWS[0], "state_ut,,Synthetic,,")
    assert [i.line for i in report.errors] == [3]


def test_issue_list_is_capped_but_totals_stay_accurate():
    rows = [f"planet,{n},Synthetic,," for n in range(50)]
    report, _ = check(*rows, max_issues=10)
    assert len(report.issues) == 10
    assert report.error_total == 50
    assert report.truncated is True


def test_report_renders_as_text_and_json_with_a_clear_verdict():
    bad, _ = check("planet,01,A,,")
    assert "REJECTED" in bad.to_text() and "level.unknown" in bad.to_text()
    data = bad.to_dict()
    assert data["ok"] is False and data["error_total"] == 1
    assert data["issues"][0]["rule"] == "level.unknown" and data["issues"][0]["line"] == 2

    good, _ = check(*VALID_ROWS)
    assert "VALID" in good.to_text() and good.to_dict()["ok"] is True


def test_no_units_are_returned_when_there_are_errors():
    report, units = check(*VALID_ROWS, "planet,9,X,,")
    assert not report.ok and units == []


def test_validation_does_not_modify_codes_or_discard_rows_silently():
    report, units = check(*VALID_ROWS)
    assert report.row_count == len(units) == 4
