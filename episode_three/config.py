"""Settings for Episode Three, read from the .env file.

Secrets (like the database password) live in .env, which Git ignores, so they
never end up on GitHub. This module is the only place that reads them.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# .env sits in the project folder, one level above this file. Building the path
# from this file's own location means .env is found whichever folder you run from.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Which database inside the cluster to use. Optional in .env.
MONGODB_DB = os.getenv("MONGODB_DB") or "episode_three"


class ConfigError(Exception):
    """A required setting is missing from .env."""


def get_mongodb_uri():
    """Return the MongoDB connection string, or explain how to add it.

    This is a function rather than a plain variable so that importing this file
    never crashes. The error only appears when something actually needs the
    database.
    """
    uri = os.getenv("MONGODB_URI", "").strip()
    if not uri:
        raise ConfigError(
            "MONGODB_URI is missing.\n"
            "Add this line to the .env file in the episode-three folder:\n"
            "  MONGODB_URI=mongodb+srv://<user>:<password>@<cluster>/\n"
            "Copy the real string from Atlas -> Connect -> Drivers -> Python.\n"
            "See .env.example for the format."
        )
    return uri


def get_mal_data_dir():
    """Return the folder holding the Kaggle MyAnimeList 2020 CSV files.

    The data stays outside the repo (it is 2.7 GB and must never be committed).
    """
    folder = os.getenv("MAL_DATA_DIR", "").strip()
    if not folder:
        raise ConfigError(
            "MAL_DATA_DIR is missing.\n"
            "Add a line to the .env file pointing at the folder with animelist.csv:\n"
            "  MAL_DATA_DIR=C:\\path\\to\\anime-recommendation-database-2020"
        )
    path = Path(folder)
    if not path.is_dir():
        raise ConfigError(f"MAL_DATA_DIR points to a folder that does not exist: {path}")
    return path
