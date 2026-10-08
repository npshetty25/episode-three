"""Shared test setup.

A "fixture" is a piece of setup pytest runs for a test. The one below runs for
EVERY test automatically (autouse) and makes any attempt to open a network
connection fail, so normal tests are fast, repeatable, and never spend
AniList's rate limit. Tests marked @pytest.mark.live are allowed through.
"""
import json
import socket
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def block_network(request, monkeypatch):
    if request.node.get_closest_marker("live"):
        return

    def refuse(*args, **kwargs):
        raise RuntimeError("This offline test tried to use the network. Mark it @pytest.mark.live if intended.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def load_fixture(name):
    """Read a JSON file from tests/fixtures/."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))
