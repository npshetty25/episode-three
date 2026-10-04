"""Remove MongoDB's sample datasets (sample_mflix etc.) to free up storage.

Run from the episode-three folder:
    python -m scripts.drop_sample_data          # dry run: only shows what would go
    python -m scripts.drop_sample_data --yes    # actually drops them

The sample data can be reloaded any time from Atlas
(your cluster -> "..." menu -> Load Sample Dataset).
"""
import argparse
import sys

from pymongo.errors import OperationFailure

from episode_three import db

NOT_AUTHORIZED = 13  # MongoDB's error code for "you don't have permission"


def main():
    parser = argparse.ArgumentParser(description="Drop the sample_* databases.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="actually drop them (without this, nothing is changed)",
    )
    args = parser.parse_args()

    client = db.get_client()
    sample_names = [name for name in client.list_database_names() if name.startswith("sample_")]
    if not sample_names:
        print("No sample_ databases found. Nothing to do.")
        return

    print("Sample databases found:")
    total_mb = 0
    for name in sample_names:
        mb = db.size_mb(name)
        total_mb += mb
        print(f"  {name:<22} {mb:9.2f} MB")
    print(f"  {'TOTAL':<22} {total_mb:9.2f} MB")

    # Without --yes, stop here. A "dry run" lets you check before deleting anything.
    if not args.yes:
        print("\nDry run: nothing was dropped. Run again with --yes to drop them.")
        return

    print()
    for name in sample_names:
        try:
            client.drop_database(name)
        except OperationFailure as error:
            if error.code == NOT_AUTHORIZED or "not authorized" in str(error).lower():
                print(
                    f"Not allowed to drop {name}: your Atlas database user lacks permission.\n"
                    "Drop them in the browser instead: Atlas -> Data Explorer (or Compass),\n"
                    "hover over each sample_ database and click the trash icon."
                )
                sys.exit(1)
            raise
        print(f"  Dropped {name}")
    print("\nDone. Run 'python -m scripts.check_db' to see the new total.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("\nFailed: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
