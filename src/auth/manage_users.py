"""Administrative user provisioning without passwords in process arguments.

Usage:
    python -m src.auth.manage_users create <username>
    python -m src.auth.manage_users create <username> --password-stdin
    python -m src.auth.manage_users list
"""

import asyncio
import getpass
import os
import sys
from dotenv import load_dotenv
from src.auth.store import create_user, list_users
from src.common.database import close_pools


async def run():
    load_dotenv()
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL is required")
    try:
        if len(sys.argv) in {3, 4} and sys.argv[1] == "create":
            if len(sys.argv) == 4 and sys.argv[3] != "--password-stdin":
                raise SystemExit(
                    "Do not pass passwords in arguments; use the prompt or --password-stdin"
                )
            password = (
                sys.stdin.readline().rstrip("\r\n")
                if len(sys.argv) == 4
                else getpass.getpass("Password: ")
            )
            if not 8 <= len(password) <= 128:
                raise SystemExit("Password must contain 8–128 characters")
            await create_user(url, sys.argv[2], password)
            print(
                "User updated; existing sessions revoked if the account already existed."
            )
        elif len(sys.argv) == 2 and sys.argv[1] == "list":
            for user in await list_users(url):
                print(user["identifier"], user["createdAt"])
        else:
            raise SystemExit(__doc__)
    finally:
        await close_pools()


if __name__ == "__main__":
    asyncio.run(run())
