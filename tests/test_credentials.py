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


def test_core_connection_string_parses() -> None:
    creds = FireboltCredentials()
    creds.parse_native_representation(
        "firebolt://firebolt?url=http://localhost:3473"
    )
    creds.on_resolved()
    assert creds.database == "firebolt"
    assert creds.host == "firebolt"
    assert creds.account_name == "core"
    assert creds.query["url"] == "http://localhost:3473"
    native = creds.to_native_representation()
    assert native == "firebolt://firebolt?url=http://localhost:3473"
    assert "account_name" not in native


def test_core_credentials_helper() -> None:
    from firebolt_dest.configuration import firebolt_core_credentials

    creds = firebolt_core_credentials()
    assert creds.to_native_representation() == (
        "firebolt://firebolt?url=http://localhost:3473"
    )
