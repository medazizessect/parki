"""Circuli - Database Manager with connection pooling."""

import logging
import os

import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger("circuli.database")


class DatabaseManager:
    """Manages MySQL database connections with pooling for Circuli."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        pool_size: int = 5,
    ):
        self.host = host or os.getenv("MYSQL_HOST", "localhost")
        self.port = port or int(os.getenv("MYSQL_PORT", "3306"))
        self.user = user or os.getenv("MYSQL_USER", "circuli")
        self.password = password or os.getenv("MYSQL_PASSWORD", "circuli")
        self.database = database or os.getenv("MYSQL_DATABASE", "circuli")
        self.pool_size = pool_size
        self._pool: pooling.MySQLConnectionPool | None = None
        logger.info("Circuli DatabaseManager initialized (host=%s, db=%s)", self.host, self.database)

    def connect(self) -> None:
        """Create the connection pool."""
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name="circuli_pool",
                pool_size=self.pool_size,
                pool_reset_session=True,
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                database=self.database,
            )
            logger.info("Circuli connection pool created (size=%d)", self.pool_size)
        except mysql.connector.Error as err:
            logger.error("Circuli failed to create connection pool: %s", err)
            raise

    def disconnect(self) -> None:
        """Close all connections in the pool."""
        if self._pool is not None:
            self._pool = None
            logger.info("Circuli connection pool closed")

    def get_connection(self) -> mysql.connector.MySQLConnection:
        """Get a connection from the pool."""
        if self._pool is None:
            raise RuntimeError("Circuli DatabaseManager is not connected. Call connect() first.")
        return self._pool.get_connection()

    def execute_query(
        self,
        query: str,
        params: tuple | None = None,
        fetch: bool = True,
    ) -> list[dict] | int:
        """Execute a SQL query and return results.

        Args:
            query: SQL query string.
            params: Optional query parameters.
            fetch: If True, fetch and return rows as list of dicts.
                   If False, commit and return affected row count.

        Returns:
            List of dicts for SELECT queries, row count for INSERT/UPDATE/DELETE.
        """
        conn = self.get_connection()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(query, params)
            if fetch:
                results = cursor.fetchall()
                logger.debug("Circuli query returned %d rows", len(results))
                return results
            else:
                conn.commit()
                row_count = cursor.rowcount
                logger.debug("Circuli query affected %d rows", row_count)
                return row_count
        except mysql.connector.Error as err:
            logger.error("Circuli query error: %s", err)
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()

    def execute_many(self, query: str, data: list[tuple]) -> int:
        """Execute a query with multiple parameter sets.

        Returns:
            Number of affected rows.
        """
        conn = self.get_connection()
        cursor = conn.cursor()
        try:
            cursor.executemany(query, data)
            conn.commit()
            row_count = cursor.rowcount
            logger.debug("Circuli batch query affected %d rows", row_count)
            return row_count
        except mysql.connector.Error as err:
            logger.error("Circuli batch query error: %s", err)
            conn.rollback()
            raise
        finally:
            cursor.close()
            conn.close()
