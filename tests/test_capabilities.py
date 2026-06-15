"""Destination capability flags."""

from __future__ import annotations

from firebolt_dest.factory import firebolt


def test_merge_runs_in_ddl_transaction() -> None:
    caps = firebolt().capabilities()
    assert caps.supports_ddl_transactions is True
    assert caps.supports_transactions is False
