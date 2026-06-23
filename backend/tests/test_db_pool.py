import unittest
from unittest.mock import MagicMock
from sqlalchemy.pool import QueuePool
from sqlalchemy.exc import TimeoutError as SqlTimeoutError


class TestDatabasePool(unittest.IsolatedAsyncioTestCase):

    def test_pool_configuration(self):
        """Verify that the engine's pool size and max_overflow are set correctly."""
        from app.database import engine
        
        # Check if the pool is a QueuePool (default for dialect databases)
        if isinstance(engine.pool, QueuePool):
            self.assertEqual(engine.pool.size(), 2)
            self.assertEqual(engine.pool._max_overflow, 3)
            print(f"Verified engine configuration: pool_size={engine.pool.size()}, max_overflow={engine.pool._max_overflow}")
        else:
            # Fallback assertion just in case it is wrapped/different pool
            self.assertEqual(getattr(engine.pool, "_size", None), 2)
            self.assertEqual(getattr(engine.pool, "_max_overflow", None), 3)

    async def test_pool_limit_concurrency(self):
        """
        Simulate QueuePool behavior with pool_size=2 and max_overflow=3.
        Verifies that exactly 5 concurrent connections can be acquired,
        the 6th blocks/times out, and releasing one allows another checkout.
        """
        connection_count = 0

        def mock_creator():
            nonlocal connection_count
            connection_count += 1
            return MagicMock()

        # Instantiate a test QueuePool with our target limits and a short timeout
        pool = QueuePool(
            creator=mock_creator,
            pool_size=2,
            max_overflow=3,
            timeout=1  # 1 second timeout for test speed
        )

        connections = []
        try:
            # Check out 5 connections concurrently (2 pool + 3 overflow)
            for i in range(5):
                conn = pool.connect()
                connections.append(conn)
            
            self.assertEqual(connection_count, 5, "Should have created exactly 5 connections")
            self.assertEqual(len(connections), 5)

            # The 6th checkout should fail with TimeoutError since pool is exhausted (limit=5)
            with self.assertRaises(SqlTimeoutError):
                pool.connect()

            # Release one connection back to the pool
            connections[0].close()

            # The 6th checkout should now succeed immediately
            new_conn = pool.connect()
            self.assertIsNotNone(new_conn)
            new_conn.close()

        finally:
            # Clean up all connections to prevent resource leaks
            for conn in connections:
                try:
                    conn.close()
                except Exception:
                    pass
