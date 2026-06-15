from __future__ import annotations

from contextlib import contextmanager
from typing import Any, AnyStr, ClassVar, Iterator, List, Optional, Sequence, Tuple

import sqlalchemy as sa
from firebolt.utils.exception import FireboltStructuredError
from sqlalchemy.engine import Connection, Engine

from dlt.common.destination import DestinationCapabilitiesContext
from dlt.destinations.exceptions import (
    DatabaseTerminalException,
    DatabaseTransientException,
    DatabaseUndefinedRelation,
)
from firebolt_dest.configuration import FireboltCredentials
from dlt.destinations.typing import DBApi, DBTransaction
from dlt.common.destination.dataset import DBApiCursor
from dlt.destinations.sql_client import (
    DBApiCursorImpl,
    SqlClientBase,
    raise_database_error,
    raise_open_connection_error,
)


class FireboltSqlClient(SqlClientBase[Connection]):
    dbapi: ClassVar[DBApi] = sa

    def __init__(
        self,
        dataset_name: str,
        staging_dataset_name: str,
        credentials: FireboltCredentials,
        capabilities: DestinationCapabilitiesContext,
    ) -> None:
        super().__init__(credentials.database, dataset_name, staging_dataset_name, capabilities)
        self.credentials = credentials
        self._engine: Optional[Engine] = None
        self._conn: Optional[Connection] = None
        self._in_transaction: bool = False

    @raise_open_connection_error
    def open_connection(self) -> Connection:
        # Default autocommit: each statement is independent. Expected "table does not
        # exist" checks must not wedge the session (0.1.0 regression with autocommit=False).
        self._engine = sa.create_engine(self.credentials.to_native_representation())
        self._conn = self._engine.connect()
        return self._conn

    @raise_open_connection_error
    def close_connection(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    @contextmanager
    def begin_transaction(self) -> Iterator[DBTransaction]:
        if self._in_transaction:
            yield self
            return
        assert self._conn is not None
        # SQLAlchemy autobegins on first use; close any leftover transaction so merge
        # follow-up SQL commits as one unit without calling conn.begin() twice.
        if self._conn.in_transaction():
            self._conn.commit()
        self._in_transaction = True
        try:
            yield self
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self._in_transaction = False

    @property
    def native_connection(self) -> Connection:
        return self._conn

    @raise_database_error
    def execute_sql(
        self, sql: AnyStr, *args: Any, **kwargs: Any
    ) -> Optional[Sequence[Sequence[Any]]]:
        with self.execute_query(sql, *args, **kwargs) as cur:
            if cur.description is None:
                return None
            return cur.fetchall()

    @contextmanager
    @raise_database_error
    def execute_query(self, query: AnyStr, *args: Any, **kwargs: Any) -> Iterator:
        assert self._conn is not None
        query_str = str(query)
        if args:
            query_str, params = self._to_named_paramstyle(query_str, args)
        elif kwargs:
            params = kwargs
        else:
            params = None
        try:
            result = self._conn.execute(sa.text(query_str), params or {})
            yield DBApiCursorImpl(_FireboltCursor(result))
        except Exception as exc:
            if not self._in_transaction:
                try:
                    self._conn.rollback()
                except Exception:
                    pass
            raise self._make_database_exception(exc) from exc

    @staticmethod
    def _make_database_exception(ex: Exception) -> Exception:
        message = str(ex)
        if isinstance(ex, FireboltStructuredError):
            if "does not exist" in message.lower():
                return DatabaseUndefinedRelation(ex)
            return DatabaseTerminalException(ex)
        if "does not exist" in message.lower():
            return DatabaseUndefinedRelation(ex)
        if isinstance(ex, sa.exc.DBAPIError):
            return DatabaseTerminalException(ex)
        return DatabaseTransientException(ex)

    def _get_information_schema_components(
        self, *tables: str
    ) -> Tuple[Optional[str], str, List[str]]:
        folded = [
            self.make_qualified_table_name_path(table, quote=False, casefold=True)[-1]
            for table in tables
        ]
        return (None, "public", folded)

    def has_dataset(self) -> bool:
        # Firebolt has no separate schema object for dlt datasets.
        return True

    def create_dataset(self) -> None:
        return None

    def drop_dataset(self) -> None:
        return None

    def make_qualified_table_name_path(
        self, table_name: Optional[str], quote: bool = True, casefold: bool = True
    ) -> List[str]:
        if table_name is None:
            return ["public"]
        name = f"{self.dataset_name}_{table_name}" if self.dataset_name else table_name
        if casefold:
            name = self.capabilities.casefold_identifier(name)
        if quote:
            name = self.capabilities.escape_identifier(name)
        return [name]


class _FireboltCursor(DBApiCursor):
    def __init__(self, result: sa.CursorResult) -> None:
        super().__init__()
        self._result = result
        self.native_cursor = self
        self.description = result.cursor.description if result.cursor else None

    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError("Firebolt cursor is execute-once")

    def fetchall(self) -> Sequence[Sequence[Any]]:
        return self._result.fetchall()

    def fetchmany(self, size: int | None = None) -> Sequence[Sequence[Any]]:
        if size is None:
            return self._result.fetchmany()
        return self._result.fetchmany(size)

    def fetchone(self) -> Optional[tuple[Any, ...]]:
        row = self._result.fetchone()
        if row is None:
            return None
        return tuple(row)

    def close(self) -> None:
        self._result.close()
