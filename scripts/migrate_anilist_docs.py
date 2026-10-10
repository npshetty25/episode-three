"""One-time migration (TASK 006, Part C) for documents written by the AniList sync.

1. my_entries: add source = "anilist" to every AniList entry (_id starts with "anilist_entry:").
2. my_entries and titles: rename synced_at -> content_changed_at on AniList documents.

Safe to run again: the filters only match documents that still need the change, so
a second run reports 0 everywhere.

Run from the episode-three folder:
    python scripts\\migrate_anilist_docs.py
"""
import sys
from pathlib import Path

# Lets "python scripts\migrate_anilist_docs.py" find the episode_three package.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from episode_three import config, db

DATABASES = [config.MONGODB_DB, "episode_three_test"]
ANILIST_ENTRY = {"_id": {"$regex": "^anilist_entry:"}}


def migrate(database):
    entries, titles = database["my_entries"], database["titles"]
    counts = {"anilist_entries": entries.count_documents(ANILIST_ENTRY),
              "anilist_titles": titles.count_documents({"source": "anilist"})}

    counts["source_added"] = entries.update_many(
        {**ANILIST_ENTRY, "source": {"$exists": False}}, {"$set": {"source": "anilist"}}).modified_count
    counts["entries_renamed"] = entries.update_many(
        {**ANILIST_ENTRY, "synced_at": {"$exists": True}},
        {"$rename": {"synced_at": "content_changed_at"}}).modified_count
    counts["titles_renamed"] = titles.update_many(
        {"source": "anilist", "synced_at": {"$exists": True}},
        {"$rename": {"synced_at": "content_changed_at"}}).modified_count

    # Checks after the migration: nothing should be left to fix.
    counts["entries_without_source"] = entries.count_documents({**ANILIST_ENTRY, "source": {"$ne": "anilist"}})
    counts["docs_still_with_synced_at"] = (entries.count_documents({"synced_at": {"$exists": True}})
                                           + titles.count_documents({"synced_at": {"$exists": True}}))
    return counts


def main():
    client = db.get_client()
    for name in DATABASES:
        counts = migrate(client[name])
        print(f"{name}:")
        for key, value in counts.items():
            print(f"  {key:<27} {value}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("\nMigration stopped: " + db.explain_error(error), file=sys.stderr)
        sys.exit(1)
