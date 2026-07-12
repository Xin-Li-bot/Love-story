"""Initialize the lightweight SQLite database used by the love story site."""

import argparse
import os

from main import DB_PATH, initialize_database


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize database.db")
    parser.add_argument(
        "--password",
        help="Initial admin password. Defaults to ADMIN_PASSWORD or love2022.",
    )
    args = parser.parse_args()
    password = args.password or os.getenv("ADMIN_PASSWORD")
    initialize_database(password)
    print(f"Database initialized: {DB_PATH}")


if __name__ == "__main__":
    main()
