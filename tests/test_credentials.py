"""Tests for Firebolt credentials URL mapping."""

import os

import pytest

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


def test_use_core_from_env() -> None:
    from firebolt_dest.configuration import use_core_from_env

    saved = {k: os.environ.get(k) for k in (
        "FIREBOLT_ACCOUNT_NAME",
        "FIREBOLT_CORE_URL",
    )}
    try:
        for k in saved:
            os.environ.pop(k, None)
        assert use_core_from_env() is False
        os.environ["FIREBOLT_ACCOUNT_NAME"] = "my-account"
        assert use_core_from_env() is False
        os.environ["FIREBOLT_CORE_URL"] = "http://localhost:3473"
        assert use_core_from_env() is True
        os.environ["FIREBOLT_ACCOUNT_NAME"] = "my-account"
        assert use_core_from_env() is True
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_managed_path_requires_account_name() -> None:
    from firebolt_dest.configuration import firebolt_url_from_env

    saved = {k: os.environ.get(k) for k in (
        "FIREBOLT_CORE_URL",
        "FIREBOLT_ACCOUNT_NAME",
        "FIREBOLT_CLIENT_ID",
        "FIREBOLT_CLIENT_SECRET",
        "FIREBOLT_DATABASE",
        "FIREBOLT_ENGINE",
    )}
    try:
        for k in saved:
            os.environ.pop(k, None)
        os.environ["FIREBOLT_CLIENT_ID"] = "id"
        os.environ["FIREBOLT_CLIENT_SECRET"] = "secret"
        os.environ["FIREBOLT_DATABASE"] = "db"
        os.environ["FIREBOLT_ENGINE"] = "engine"
        with pytest.raises(RuntimeError, match="FIREBOLT_ACCOUNT_NAME"):
            firebolt_url_from_env()
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_core_credentials_helper() -> None:
    from firebolt_dest.configuration import firebolt_core_credentials

    saved = {k: os.environ.get(k) for k in ("FIREBOLT_CORE_URL", "FIREBOLT_CORE_DATABASE")}
    try:
        for k in saved:
            os.environ.pop(k, None)
        os.environ["FIREBOLT_CORE_URL"] = "http://localhost:3473"
        creds = firebolt_core_credentials()
        assert creds.to_native_representation() == (
            "firebolt://firebolt?url=http://localhost:3473"
        )
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
