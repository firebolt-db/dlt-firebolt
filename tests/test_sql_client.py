"""Unit tests for FireboltSqlClient transaction behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from dlt.common.data_writers.escape import escape_postgres_identifier
from dlt.common.destination import DestinationCapabilitiesContext

from firebolt_dest.configuration import FireboltCredentials
from firebolt_dest.sql_client import FireboltSqlClient


def _client(*, in_transaction: bool = False) -> FireboltSqlClient:
    caps = DestinationCapabilitiesContext()
    caps.escape_identifier = escape_postgres_identifier
    caps.casefold_identifier = str.lower
    creds = FireboltCredentials()
    creds.database = "db"
    client = FireboltSqlClient("demo", "demo_staging", creds, caps)
    client._conn = MagicMock()
    client._conn.in_transaction.return_value = in_transaction
    return client


def test_begin_transaction_commits_on_success() -> None:
    client = _client()
    with client.begin_transaction():
        pass
    client._conn.commit.assert_called_once()
    client._conn.rollback.assert_not_called()
    assert client._in_transaction is False


def test_begin_transaction_commits_existing_transaction_first() -> None:
    client = _client(in_transaction=True)
    with client.begin_transaction():
        pass
    assert client._conn.commit.call_count == 2
    assert client._in_transaction is False


def test_begin_transaction_rolls_back_on_error() -> None:
    client = _client()
    with pytest.raises(RuntimeError, match="boom"):
        with client.begin_transaction():
            raise RuntimeError("boom")
    client._conn.rollback.assert_called_once()
    client._conn.commit.assert_not_called()
    assert client._in_transaction is False


def test_execute_query_rolls_back_after_error_outside_transaction() -> None:
    client = _client()
    client._conn.execute.side_effect = RuntimeError("table missing")
    with pytest.raises(Exception):
        client.execute_sql("SELECT 1")
    client._conn.rollback.assert_called_once()


def test_execute_query_does_not_commit_outside_transaction() -> None:
    client = _client()
    client.execute_sql("SELECT 1")
    client._conn.commit.assert_not_called()


def test_execute_query_defers_rollback_to_begin_transaction() -> None:
    client = _client()
    client._conn.execute.side_effect = RuntimeError("fail")
    with pytest.raises(Exception):
        with client.begin_transaction():
            client.execute_sql("SELECT 1")
    client._conn.rollback.assert_called_once()
