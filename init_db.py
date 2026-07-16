"""Compatibility CLI for initializing and maintaining the Love Story database."""

from __future__ import annotations

import argparse
import getpass
import secrets

from main import (
    DB_PATH,
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize the Love Story database")
    parser.add_argument(
        "--password",
        help="Initial password for automation. Prefer ADMIN_PASSWORD or --reset-password.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Interactively set a strong password and invalidate every session.",
    )
    parser.add_argument(
        "--rebuild-thumbnails",
        action="store_true",
        help="Generate missing timeline thumbnails after initialization.",
    )
    args = parser.parse_args()

    if args.password and args.reset_password:
        parser.error("--password and --reset-password cannot be used together")

    if args.reset_password:
        password = prompt_new_password()
        initialize_database(password)
        reset_admin_password(password)
        print("Administrator password updated; all sessions were invalidated.")
    else:
        initialize_database(args.password)

    if args.rebuild_thumbnails:
        result = rebuild_missing_thumbnails()
        print(f"Thumbnails created: {result['created']}; skipped: {result['skipped']}")
    print(f"Database initialized: {DB_PATH}")


if __name__ == "__main__":
    main()
