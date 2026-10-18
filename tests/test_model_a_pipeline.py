"""Offline tests for the aggregation pipeline definition (it is only run against Atlas by the script)."""
import json

from episode_three.features import model_a
from episode_three.features import model_a_pipeline as pipeline


def test_pipeline_stages_and_merge_target():
    stages = pipeline.features_pipeline()
    assert [list(s)[0] for s in stages] == ["$match", "$lookup", "$unwind", "$project", "$set", "$merge"]
    assert stages[0]["$match"] == {"status": "trainable"}
    assert stages[1]["$lookup"]["from"] == pipeline.CANDIDATES
    merge = stages[-1]["$merge"]
    assert merge["into"] == pipeline.FEATURES and merge["on"] == "_id"
    assert merge["whenMatched"] == "replace"   # re-running replaces the same documents: identical output


def test_split_boundaries_match_the_python_rule():
    expr = pipeline.split_expression()["$switch"]
    assert expr["branches"][0]["case"] == {"$lte": ["$season_year", model_a.TRAIN_LAST_YEAR]}
    assert expr["branches"][1]["case"] == {"$eq": ["$season_year", model_a.VALIDATION_YEAR]}
    assert [b["then"] for b in expr["branches"]] == ["train", "validation"] and expr["default"] == "test"


def test_pipeline_projects_only_named_columns_and_no_current_or_window_two_fields():
    text = json.dumps(pipeline.features_pipeline())
    assert "current_" not in text and "snapshots_w" not in text and "stats" not in text
    projected = pipeline.features_pipeline()[3]["$project"]
    assert set(projected) == {"season", "season_year", "title", "features", "label", "flags"}
    metadata = projected["features"]["$mergeObjects"][1]
    assert set(metadata) == {"episodes_planned", "format", "source_material", "genres"}
