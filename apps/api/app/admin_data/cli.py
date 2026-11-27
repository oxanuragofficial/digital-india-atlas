"""Command-line tool for administrative data imports.

Run from apps/api (identical on Windows PowerShell, macOS and Linux):

    python -m app.admin_data validate FILE.csv
    python -m app.admin_data import FILE.csv --manifest MANIFEST.json --imported-by "Your Name"
    python -m app.admin_data status
    python -m app.admin_data submit-for-review ID
    python -m app.admin_data approve ID --reviewer "Your Name" [--note "..."]
    python -m app.admin_data publish ID
    python -m app.admin_data reject ID --reviewer "Your Name" --reason "..."

`validate` needs no database. Importing never publishes; publication is its own step and only an
approved dataset version can be published.

Exit codes: 0 success, 1 the data was rejected / a rule refused the action, 2 usage or
environment problem (missing DATABASE_URL, unreadable file, unknown id).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.admin_data import publishing
from app.admin_data.importer import ImportRefused, ImportRejected, import_units_csv
from app.admin_data.manifest import ManifestError, load_manifest
from app.admin_data.models import DatasetVersion
from app.admin_data.status import InvalidTransition
from app.admin_data.validation import validate_units_csv
from app.db.session import get_engine

EXIT_OK, EXIT_REFUSED, EXIT_USAGE = 0, 1, 2


def _parse_widths(items: list[str] | None) -> dict[str, int] | None:
    if not items:
        return None
    widths: dict[str, int] = {}
    for item in items:
        level, _, width = item.partition("=")
        if not level or not width.isdigit():
            raise SystemExit(f"--code-width expects LEVEL=NUMBER, got {item!r}")
        widths[level] = int(width)
    return widths


def _write_report(report, report_file: str | None) -> None:  # noqa: ANN001
    if report_file:
        Path(report_file).write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Report written to {report_file}")


def _with_session(action: Callable[[Session], int]) -> int:
    engine = get_engine()
    if engine is None:
        print(
            "DATABASE_URL is not set. Copy .env.example to .env and set it "
            "(see docs/SETUP_WINDOWS.md).",
            file=sys.stderr,
        )
        return EXIT_USAGE
    try:
        with Session(engine) as session, session.begin():
            return action(session)
    except SQLAlchemyError as exc:
        # Do not print the raw error: driver messages can contain connection details.
        print(f"Database error ({type(exc).__name__}); nothing was changed.", file=sys.stderr)
        return EXIT_USAGE


def cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return EXIT_USAGE
    report, _ = validate_units_csv(path, code_widths=_parse_widths(args.code_width))
    print(report.to_text())
    _write_report(report, args.report_file)
    return EXIT_OK if report.ok else EXIT_REFUSED


def cmd_import(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        print(f"File not found: {path}", file=sys.stderr)
        return EXIT_USAGE
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(f"Manifest problem: {exc}", file=sys.stderr)
        return EXIT_USAGE

    def run(session: Session) -> int:
        try:
            result = import_units_csv(
                session,
                path,
                manifest,
                imported_by=args.imported_by,
                code_widths=_parse_widths(args.code_width),
            )
        except ImportRejected as exc:
            print(exc.report.to_text())
            _write_report(exc.report, args.report_file)
            print("\nNothing was imported.")
            return EXIT_REFUSED
        except ImportRefused as exc:
            print(f"Import refused: {exc}", file=sys.stderr)
            return EXIT_REFUSED
        print(
            f"Imported dataset version {result.dataset_version_id}: {result.record_count} units "
            f"({', '.join(f'{k}={v}' for k, v in sorted(result.counts_by_level.items()))}), "
            f"{result.warning_total} warning(s). Status: {result.status.value}. "
            "It is NOT published; review it before publishing."
        )
        return EXIT_OK

    return _with_session(run)


def cmd_status(args: argparse.Namespace) -> int:
    def run(session: Session) -> int:
        rows = session.scalars(select(DatasetVersion).order_by(DatasetVersion.id)).all()
        if not rows:
            print("No dataset versions.")
        for v in rows:
            print(
                f"{v.id:>4}  {v.status:<12} {v.publisher} / {v.dataset_name} / {v.version_label}"
                f"  units={v.record_count}  source_date={v.source_date}"
                f"  licence={v.license_name}"
            )
        return EXIT_OK

    return _with_session(run)


def _workflow(call: Callable[[Session, argparse.Namespace], DatasetVersion], verb: str):
    def command(args: argparse.Namespace) -> int:
        def run(session: Session) -> int:
            try:
                version = call(session, args)
            except publishing.DatasetVersionNotFound as exc:
                print(str(exc), file=sys.stderr)
                return EXIT_USAGE
            except (InvalidTransition, publishing.MissingActor) as exc:
                print(f"Refused: {exc}", file=sys.stderr)
                return EXIT_REFUSED
            except SQLAlchemyError as exc:
                print(f"Refused by the database: {type(exc).__name__}", file=sys.stderr)
                return EXIT_REFUSED
            print(f"Dataset version {version.id} is now {version.status} ({verb}).")
            return EXIT_OK

        return _with_session(run)

    return command


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.admin_data", description="Administrative data import tool."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_width(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--code-width",
            action="append",
            metavar="LEVEL=N",
            help="require codes of this level to be exactly N characters (repeatable)",
        )
        p.add_argument("--report-file", help="also write the validation report as JSON")

    p = sub.add_parser("validate", help="validate a units CSV (no database needed)")
    p.add_argument("file")
    add_width(p)
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("import", help="validate and import a units CSV as a new dataset version")
    p.add_argument("file")
    p.add_argument("--manifest", required=True, help="provenance manifest (JSON)")
    p.add_argument("--imported-by", help="name recorded as the importer")
    add_width(p)
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("status", help="list dataset versions and their status")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("submit-for-review", help="freeze a validated version for review")
    p.add_argument("id", type=int)
    p.set_defaults(
        func=_workflow(lambda s, a: publishing.submit_for_review(s, a.id), "submitted for review")
    )

    p = sub.add_parser("approve", help="approve a version that is under review")
    p.add_argument("id", type=int)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--note")
    p.set_defaults(
        func=_workflow(
            lambda s, a: publishing.approve(s, a.id, reviewer=a.reviewer, note=a.note), "approved"
        )
    )

    p = sub.add_parser("publish", help="publish an approved version")
    p.add_argument("id", type=int)
    p.set_defaults(func=_workflow(lambda s, a: publishing.publish(s, a.id), "published"))

    p = sub.add_parser("reject", help="reject a version that has not been published")
    p.add_argument("id", type=int)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--reason", required=True)
    p.set_defaults(
        func=_workflow(
            lambda s, a: publishing.reject(s, a.id, reviewer=a.reviewer, reason=a.reason),
            "rejected",
        )
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
