"""Administrative CLI for creating tenant keys without a public provisioning endpoint."""
import argparse
import secrets
from .db import Database


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/opspilot.db")
    parser.add_argument("--org", required=True)
    parser.add_argument("--org-name", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--role", choices=["owner", "editor", "viewer"], default="owner")
    args = parser.parse_args()
    db = Database(args.db)
    key = "ops_" + secrets.token_urlsafe(32)
    db.add_org(args.org, args.org_name)
    db.add_key(args.org, args.user, args.role, key)
    print("Created key (save it; not recoverable):", key)


if __name__ == "__main__":
    main()
