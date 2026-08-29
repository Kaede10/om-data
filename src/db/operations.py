import logging
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

from .connection import get_connection_pool, ConnectionPool
from .exceptions import DatabaseOperationError


class DatabaseOperations:
    def __init__(self, connection_pool: ConnectionPool = None):
        if connection_pool is None:
            connection_pool = get_connection_pool()
        self.pool = connection_pool
        self.logger = logging.getLogger(__name__)
    
    def execute_query(
        self,
        query: str,
        params: Optional[Tuple] = None
    ) -> List[Dict[str, Any]]:
        with self.pool.connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    columns = [desc[0] for desc in cursor.description]
                    rows = cursor.fetchall()
                    result = [dict(zip(columns, row)) for row in rows]
                    self.logger.debug(f"查询成功，返回 {len(result)} 条记录")
                    return result
            except Exception as e:
                self.logger.error(f"查询执行失败: {e}\n查询: {query}\n参数: {params}")
                raise DatabaseOperationError(f"查询执行失败: {e}")
    
    def execute_update(
        self,
        query: str,
        params: Optional[Tuple] = None,
        return_id: bool = False
    ) -> Optional[int]:
        with self.pool.connection() as conn:
            try:
                with conn.cursor() as cursor:
                    cursor.execute(query, params)
                    conn.commit()
                    affected_rows = cursor.rowcount
                    self.logger.debug(f"更新成功，影响 {affected_rows} 行")
                    
                    if return_id:
                        cursor.execute("SELECT lastval()")
                        result_id = cursor.fetchone()[0]
                        return result_id
                    
                    return affected_rows
            except Exception as e:
                conn.rollback()
                self.logger.error(f"更新执行失败: {e}\n查询: {query}\n参数: {params}")
                raise DatabaseOperationError(f"更新执行失败: {e}")
    
    @contextmanager
    def transaction(self):
        conn = self.pool.get_connection()
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
            self.logger.debug("事务提交成功")
        except Exception as e:
            conn.rollback()
            self.logger.error(f"事务执行失败，已回滚: {e}")
            raise DatabaseOperationError(f"事务执行失败: {e}")
        finally:
            self.pool.return_connection(conn)
    
    def execute_in_transaction(
        self,
        conn,
        query: str,
        params: Optional[Tuple] = None
    ) -> None:
        try:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                self.logger.debug(f"事务内执行成功: {query}")
        except Exception as e:
            self.logger.error(f"事务内执行失败: {e}\n查询: {query}\n参数: {params}")
            raise DatabaseOperationError(f"事务内执行失败: {e}")