"""CLI to create/update login users. Chainlit has no self-serve signup UI, so
demo/admin users are provisioned here instead -- see src/auth/store.py for
where these land.

Usage:
    python src/auth/manage_users.py create <username> <password>
    python src/auth/manage_users.py list
"""

import asyncio
import os
import sys

from dotenv import load_dotenv

sys.path.insert(0, os.getcwd())

from src.auth.store import create_user, list_users  # noqa: E402

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def main() -> None:
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set in .env")

    if len(sys.argv) == 4 and sys.argv[1] == "create":
        asyncio.run(create_user(DATABASE_URL, sys.argv[2], sys.argv[3]))
        print(f"User {sys.argv[2]!r} created/updated.")
    elif len(sys.argv) == 2 and sys.argv[1] == "list":
        users = asyncio.run(list_users(DATABASE_URL))
        if not users:
            print("(no users yet)")
        for u in users:
            print(f"{u['identifier']:20s} created {u['createdAt']}")
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
