"""Operational commands for the Love Story application."""

from __future__ import annotations

import argparse
import getpass
import secrets

from main import (
    DB_PATH,
    cleanup_orphan_uploads,
    initialize_database,
    rebuild_missing_thumbnails,
    reset_admin_password,
    validate_password_strength,
)


def prompt_new_password() -> str:
    password = getpass.getpass("New administrator password: ")
    confirmation = getpass.getpass("Confirm administrator password: ")
    if not secrets.compare_digest(password, confirmation):
        raise SystemExit("Passwords do not match")
    try:
        return validate_password_strength(password)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the Love Story application")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Initialize or migrate the configured database")
    subparsers.add_parser(
        "reset-password",
        help="Interactively reset the administrator password and every session",
    )
    thumbnails = subparsers.add_parser(
        "rebuild-thumbnails", help="Generate thumbnails missing from timeline records"
    )
    thumbnails.add_argument("--limit", type=int, default=None)
    cleanup = subparsers.add_parser(
        "cleanup-orphans", help="Delete tracked uploads no longer referenced by the timeline"
    )
    cleanup.add_argument("--grace-hours", type=int, default=24)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "reset-password":
        password = prompt_new_password()
        initialize_database(password)
        reset_admin_password(password)
        print("Administrator password updated; all sessions were invalidated.")
        return

    initialize_database()
    if args.command == "init":
        print(f"Database initialized: {DB_PATH}")
    elif args.command == "rebuild-thumbnails":
        result = rebuild_missing_thumbnails(limit=args.limit)
        print(f"Thumbnails created: {result['created']}; skipped: {result['skipped']}")
    elif args.command == "cleanup-orphans":
        result = cleanup_orphan_uploads(grace_hours=args.grace_hours)
        print(f"Orphan uploads removed: {result['removed']}")


if __name__ == "__main__":
    main()
