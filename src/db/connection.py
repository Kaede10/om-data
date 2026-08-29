import logging
import threading
from typing import Optional
from contextlib import contextmanager
import psycopg2
from psycopg2 import pool

from .config import DatabaseConfig
from .exceptions import DatabaseConnectionError


class ConnectionPool:
    _instance: Optional['ConnectionPool'] = None
    _lock: threading.Lock = threading.Lock()
    
    def __new__(cls, config: DatabaseConfig = None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config: DatabaseConfig = None):
        if self._initialized:
            return
            
        if config is None:
            config = DatabaseConfig()
        
        self.config = config
        self.db_config = config.get_database_config()
        self.pool_config = config.get_pool_config()
        
        logging_config = config.get_logging_config()
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(getattr(logging, logging_config['level']))
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(getattr(logging, logging_config['level']))
            formatter = logging.Formatter(logging_config['format'])
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
        
        self._pool: Optional[pool.ThreadedConnectionPool] = None
        self._initialize_pool()
        self._initialized = True
    
    def _initialize_pool(self):
        try:
            self._pool = pool.ThreadedConnectionPool(
                minconn=self.pool_config['min_connections'],
                maxconn=self.pool_config['max_connections'],
                host=self.db_config['host'],
                port=self.db_config['port'],
                database=self.db_config['database'],
                user=self.db_config['user'],
                password=self.db_config['password'],
                connect_timeout=self.pool_config['connection_timeout']
            )
            self.logger.info("数据库连接池初始化成功")
        except Exception as e:
            self.logger.error(f"数据库连接池初始化失败: {e}")
            raise DatabaseConnectionError(f"无法初始化数据库连接池: {e}")
    
    def get_connection(self):
        try:
            conn = self._pool.getconn()
            self.logger.debug("从连接池获取连接")
            return conn
        except Exception as e:
            self.logger.error(f"获取数据库连接失败: {e}")
            raise DatabaseConnectionError(f"无法获取数据库连接: {e}")
    
    def return_connection(self, conn):
        try:
            self._pool.putconn(conn)
            self.logger.debug("归还连接到连接池")
        except Exception as e:
            self.logger.error(f"归还数据库连接失败: {e}")
    
    @contextmanager
    def connection(self):
        conn = None
        try:
            conn = self.get_connection()
            yield conn
        finally:
            if conn is not None:
                self.return_connection(conn)
    
    def close_all(self):
        try:
            if self._pool is not None:
                self._pool.closeall()
                self.logger.info("关闭所有数据库连接")
        except Exception as e:
            self.logger.error(f"关闭连接池失败: {e}")
    
    def __del__(self):
        self.close_all()


_connection_pool: Optional[ConnectionPool] = None


def get_connection_pool(config: DatabaseConfig = None) -> ConnectionPool:
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ConnectionPool(config)
    return _connection_pool


def close_connection_pool():
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.close_all()
        _connection_pool = None