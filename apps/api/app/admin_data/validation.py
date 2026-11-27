"""Validation of an administrative-units CSV file ("atlas-admin-units-v1").

This module is pure: it reads a file and returns a report. It never touches the database and never
changes the data it validates (see `name.normalized` for the one tolerated cosmetic fix).

File format (UTF-8, header row required, comma separated, RFC 4180 quoting):

    level,code,name,parent_level,parent_code

- `level`         a level key from the level graph (state_ut, district, subdistrict, locality).
- `code`          the official identifier AS A STRING. Never converted to a number, so leading
                  zeros survive. Letters and digits only, 1-32 characters, no surrounding spaces.
- `name`          the unit's official name as published.
- `parent_level`, `parent_code`   both empty for root units, both filled for every other unit.

Official exports are NOT in this format. A future adapter maps a real export onto it; that
adapter, not this validator, is where publisher-specific rules belong.

Every problem is reported with its line number. Nothing is "fixed" silently: bad codes, bad
parents and duplicates are errors. The import is refused if there is any error.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.admin_data.levels import DEFAULT_LEVEL_GRAPH, LevelGraph
from app.admin_data.models import CODE_MAX_LENGTH, CODE_REGEX

FORMAT_NAME = "atlas-admin-units-v1"
CSV_COLUMNS = ("level", "code", "name", "parent_level", "parent_code")
NAME_MAX_LENGTH = 300
DEFAULT_MAX_ISSUES = 1000

_CODE = re.compile(CODE_REGEX)
_WHITESPACE_RUN = re.compile(r"\s+")


@dataclass(frozen=True)
class Issue:
    severity: str  # "error" | "warning"
    rule: str  # stable machine-readable id, e.g. "parent.not_found"
    message: str
    line: int | None = None  # 1-based line in the file (the header is line 1)
    level: str | None = None
    code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line is not None else "file"
        ident = f" [{self.level} {self.code}]" if self.level and self.code else ""
        return f"{self.severity.upper():7} {where}{ident} {self.rule}: {self.message}"


@dataclass(frozen=True)
class ParsedUnit:
    line: int
    level: str
    code: str
    name: str
    parent_level: str | None
    parent_code: str | None


@dataclass
class ValidationReport:
    format: str = FORMAT_NAME
    row_count: int = 0
    counts_by_level: dict[str, int] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)
    error_total: int = 0
    warning_total: int = 0
    truncated: bool = False  # more issues exist than were recorded

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return self.error_total == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": self.format,
            "ok": self.ok,
            "row_count": self.row_count,
            "counts_by_level": dict(self.counts_by_level),
            "error_total": self.error_total,
            "warning_total": self.warning_total,
            "truncated": self.truncated,
            "issues": [i.to_dict() for i in self.issues],
        }

    def to_text(self) -> str:
        lines = [
            f"Format: {self.format}",
            f"Rows: {self.row_count}",
            "Per level: "
            + (", ".join(f"{k}={v}" for k, v in sorted(self.counts_by_level.items())) or "none"),
            f"Errors: {self.error_total}   Warnings: {self.warning_total}",
            f"Result: {'VALID' if self.ok else 'REJECTED'}",
        ]
        lines += [str(i) for i in self.issues]
        if self.truncated:
            lines.append(f"... more issues exist; only the first {len(self.issues)} are listed.")
        return "\n".join(lines)


class _Collector:
    def __init__(self, report: ValidationReport, max_issues: int) -> None:
        self.report = report
        self.max_issues = max_issues

    def add(self, severity: str, rule: str, message: str, **where: Any) -> None:
        if severity == "error":
            self.report.error_total += 1
        else:
            self.report.warning_total += 1
        if len(self.report.issues) < self.max_issues:
            self.report.issues.append(Issue(severity, rule, message, **where))
        else:
            self.report.truncated = True

    def error(self, rule: str, message: str, **where: Any) -> None:
        self.add("error", rule, message, **where)

    def warning(self, rule: str, message: str, **where: Any) -> None:
        self.add("warning", rule, message, **where)


def normalise_name(raw: str) -> str:
    """Trim, collapse whitespace runs and apply Unicode NFC. Applied to names only, never codes."""
    return _WHITESPACE_RUN.sub(" ", unicodedata.normalize("NFC", raw)).strip()


_ORDINARY_WHITESPACE = "\t\n\r"


def _has_control_chars(value: str) -> bool:
    """True for control characters such as BEL or ESC. Tabs and line breaks are ordinary
    whitespace: they are collapsed in names (with a warning) and rejected by the code rules."""
    return any(unicodedata.category(ch) == "Cc" and ch not in _ORDINARY_WHITESPACE for ch in value)


def validate_units_csv(
    source: str | Path | bytes,
    graph: LevelGraph = DEFAULT_LEVEL_GRAPH,
    *,
    code_widths: Mapping[str, int] | None = None,
    max_issues: int = DEFAULT_MAX_ISSUES,
) -> tuple[ValidationReport, list[ParsedUnit]]:
    """Validate a units CSV. `source` is a file path or the raw file bytes.

    Returns (report, units). `units` is meaningful only when `report.ok`; it is ordered so that
    every parent appears before its children. `code_widths` optionally maps a level key to the
    exact code length a given identifier scheme uses (e.g. zero-padded fixed-width codes).
    """
    report = ValidationReport()
    out = _Collector(report, max_issues)

    raw = Path(source).read_bytes() if isinstance(source, (str, Path)) else source
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        out.error("file.encoding", f"file is not valid UTF-8 (byte offset {exc.start})")
        return report, []
    if "\x00" in text:
        out.error("file.encoding", "file contains NUL bytes; it is not a text CSV")
        return report, []

    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
    except csv.Error as exc:
        out.error("file.header", f"cannot parse header: {exc}", line=1)
        return report, []
    if header is None:
        out.error("file.empty", "file is empty")
        return report, []

    header = [h.strip().lower() for h in header]
    if header != list(CSV_COLUMNS):
        missing = [c for c in CSV_COLUMNS if c not in header]
        unknown = [c for c in header if c not in CSV_COLUMNS]
        dupes = [c for c, n in Counter(header).items() if n > 1]
        out.error(
            "file.header",
            f"header must be exactly {','.join(CSV_COLUMNS)} "
            f"(missing: {missing or 'none'}, unknown: {unknown or 'none'}, "
            f"duplicated: {dupes or 'none'}, order matters)",
            line=1,
        )
        return report, []

    units: list[ParsedUnit] = []
    by_key: dict[tuple[str, str], ParsedUnit] = {}
    by_zero_stripped: dict[tuple[str, str], ParsedUnit] = {}

    while True:
        try:
            row = next(reader, None)
        except csv.Error as exc:
            out.error("file.csv", f"malformed CSV: {exc}", line=reader.line_num)
            break
        if row is None:
            break
        line = reader.line_num
        if not row or all(cell.strip() == "" for cell in row):
            out.warning("row.blank", "blank line ignored", line=line)
            continue
        report.row_count += 1

        if len(row) != len(CSV_COLUMNS):
            out.error(
                "row.field_count",
                f"expected {len(CSV_COLUMNS)} fields, found {len(row)}",
                line=line,
            )
            continue
        level, code, name, parent_level, parent_code = row
        if any(_has_control_chars(cell) for cell in row):
            out.error("row.control_chars", "contains control characters", line=line)
            continue

        row_ok = True

        # ---- level ----
        if level != level.strip() or not graph.has_level(level):
            out.error(
                "level.unknown",
                f"unknown level {level!r}; expected one of {sorted(graph.level_keys)}",
                line=line,
            )
            continue  # nothing else can be judged without a valid level
        report.counts_by_level[level] = report.counts_by_level.get(level, 0) + 1

        # ---- code: exact, never normalised ----
        if code != code.strip():
            out.error(
                "code.whitespace",
                "code has leading/trailing whitespace",
                line=line,
                level=level,
                code=code.strip(),
            )
            row_ok = False
        elif code == "":
            out.error("code.blank", "code is empty", line=line, level=level)
            row_ok = False
        elif len(code) > CODE_MAX_LENGTH or not _CODE.match(code):
            out.error(
                "code.format",
                f"code must be 1-{CODE_MAX_LENGTH} letters/digits only (got {code!r})",
                line=line,
                level=level,
                code=code,
            )
            row_ok = False
        elif code_widths and level in code_widths and len(code) != code_widths[level]:
            out.error(
                "code.width",
                f"code must be exactly {code_widths[level]} characters for level {level} "
                f"(got {len(code)}); a stripped leading zero?",
                line=line,
                level=level,
                code=code,
            )
            row_ok = False

        # ---- name: cosmetic whitespace/NFC fixes only, recorded as a warning ----
        clean_name = normalise_name(name)
        if clean_name == "":
            out.error("name.blank", "name is empty", line=line, level=level, code=code)
            row_ok = False
        elif len(clean_name) > NAME_MAX_LENGTH:
            out.error(
                "name.length",
                f"name longer than {NAME_MAX_LENGTH} characters",
                line=line,
                level=level,
                code=code,
            )
            row_ok = False
        elif clean_name != name:
            out.warning(
                "name.normalized",
                "name whitespace/Unicode form was normalised",
                line=line,
                level=level,
                code=code,
            )

        # ---- parent fields ----
        p_level = parent_level.strip() or None
        p_code = parent_code if parent_code.strip() else None
        if (p_level is None) != (p_code is None):
            out.error(
                "parent.partial",
                "parent_level and parent_code must both be set or both empty",
                line=line,
                level=level,
                code=code,
            )
            row_ok = False
        elif graph.is_root(level) and p_level is not None:
            out.error(
                "parent.root_has_parent",
                f"level {level} is the root and cannot have a parent",
                line=line,
                level=level,
                code=code,
            )
            row_ok = False
        elif not graph.is_root(level) and p_level is None:
            out.error(
                "parent.missing",
                f"level {level} requires a parent",
                line=line,
                level=level,
                code=code,
            )
            row_ok = False
        elif p_level is not None:
            if parent_code != parent_code.strip():
                out.error(
                    "parent.code_whitespace",
                    "parent_code has surrounding whitespace",
                    line=line,
                    level=level,
                    code=code,
                )
                row_ok = False
            if not graph.has_level(p_level):
                out.error(
                    "parent.level_unknown",
                    f"unknown parent level {p_level!r}",
                    line=line,
                    level=level,
                    code=code,
                )
                row_ok = False
            elif p_level not in graph.allowed_parents(level):
                out.error(
                    "parent.level_not_allowed",
                    f"a {level} cannot have a {p_level} as parent "
                    f"(allowed: {sorted(graph.allowed_parents(level))})",
                    line=line,
                    level=level,
                    code=code,
                )
                row_ok = False

        if not row_ok:
            continue

        # ---- uniqueness ----
        unit = ParsedUnit(line, level, code, clean_name, p_level, p_code)
        key = (level, code)
        if key in by_key:
            out.error(
                "unit.duplicate",
                f"duplicate of line {by_key[key].line}",
                line=line,
                level=level,
                code=code,
            )
            continue
        stripped = (level, code.lstrip("0") or "0")
        if stripped in by_zero_stripped:
            out.error(
                "code.zero_padding_ambiguous",
                f"differs from {by_zero_stripped[stripped].code!r} (line "
                f"{by_zero_stripped[stripped].line}) only by leading zeros",
                line=line,
                level=level,
                code=code,
            )
            continue
        by_key[key] = unit
        by_zero_stripped[stripped] = unit
        units.append(unit)

    if report.row_count == 0 and report.error_total == 0:
        out.error("file.empty", "file has a header but no data rows")

    # ---- references: every parent must exist in this file ----
    for unit in units:
        if unit.parent_level is not None and (unit.parent_level, unit.parent_code) not in by_key:
            out.error(
                "parent.not_found",
                f"parent {unit.parent_level} {unit.parent_code!r} is not in the file",
                line=unit.line,
                level=unit.level,
                code=unit.code,
            )

    if report.ok:
        units.sort(key=lambda u: (graph.rank(u.level), u.line))
    return report, units if report.ok else []


def group_by_level(units: list[ParsedUnit]) -> dict[str, list[ParsedUnit]]:
    grouped: dict[str, list[ParsedUnit]] = defaultdict(list)
    for unit in units:
        grouped[unit.level].append(unit)
    return grouped
