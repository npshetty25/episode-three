"""Check that Python can reach MongoDB Atlas, and how much storage is used.

Run from the episode-three folder:
    python -m scripts.check_db
"""
import sys
import time
from datetime import datetime, timezone

from pymongo.errors import OperationFailure

from episode_three import db

FREE_TIER_LIMIT_MB = 512


def main():
    client = db.get_client()

    # 1. Ping: the smallest possible request. If it works, we reached Atlas
    #    and the username/password were accepted.
    client.admin.command("ping")
    version = client.server_info()["version"]
    print(f"Ping OK (MongoDB server version {version})")

    # 2. Storage: data + indexes for every database, compared with the 512 MB limit.
    print("\nStorage per database (data + indexes):")
    total_mb = 0
    for name in client.list_database_names():
        try:
            mb = db.size_mb(name)
        except OperationFailure:
            # Some system databases don't let normal users read their size.
            print(f"  {name:<22} (size not readable)")
            continue
        total_mb += mb
        print(f"  {name:<22} {mb:9.2f} MB")
    percent = total_mb / FREE_TIER_LIMIT_MB
    print(f"  {'TOTAL':<22} {total_mb:9.2f} MB of {FREE_TIER_LIMIT_MB} MB ({percent:.1%})")

    # 3. Round trip: write a document, read it back, delete it, and time all three.
    #    This proves we can write, not just read.
    healthcheck = db.get_db()["healthcheck"]
    start = time.perf_counter()
    result = healthcheck.insert_one({"check": "round trip", "at": datetime.now(timezone.utc)})
    found = healthcheck.find_one({"_id": result.inserted_id})
    healthcheck.delete_one({"_id": result.inserted_id})
    elapsed_ms = (time.perf_counter() - start) * 1000
    healthcheck.drop()  # leave nothing behind
    if found is None:
        raise RuntimeError("Wrote a test document but could not read it back.")
    print(f"\nRound trip OK ({elapsed_ms:.0f} ms)")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Print a short, friendly message instead of a long traceback.
        print("\nCheck failed: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
