"""Tests for Firebolt credentials URL mapping."""

from firebolt_dest.configuration import FireboltCredentials


def test_structured_credentials_match_connection_string() -> None:
    creds = FireboltCredentials(
        {
            "host": "demo_db",
            "database": "demo_engine",
            "username": "client_id",
            "password": "secret",
            "account_name": "developer",
        }
    )
    creds.on_resolved()
    url = creds.to_native_representation()
    assert url.startswith("firebolt://client_id:secret@demo_db/demo_engine")
    assert "account_name=developer" in url
