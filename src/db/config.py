import os
from pathlib import Path
from typing import Dict, Any
import yaml

from .exceptions import DatabaseConfigError


class DatabaseConfig:
    def __init__(self, config_path: str = None):
        self.config_path = config_path or self._get_default_config_path()
        self.config = self._load_config()
        self._validate_config()

    def _get_default_config_path(self) -> str:
        current_dir = Path(__file__).parent
        config_path = current_dir.parent / "config" / "database.yaml"
        return str(config_path)

    def _load_config(self) -> Dict[str, Any]:
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
                if not config:
                    raise DatabaseConfigError(f"配置文件为空: {self.config_path}")
                return config
        except FileNotFoundError:
            raise DatabaseConfigError(f"配置文件不存在: {self.config_path}")
        except yaml.YAMLError as e:
            raise DatabaseConfigError(f"配置文件格式错误: {e}")

    def _validate_config(self):
        required_fields = ['database']
        for field in required_fields:
            if field not in self.config:
                raise DatabaseConfigError(f"缺少必需的配置字段: {field}")

        db_config = self.config['database']
        required_db_fields = ['host', 'port', 'database', 'user', 'password']
        for field in required_db_fields:
            if field not in db_config:
                raise DatabaseConfigError(f"数据库配置缺少必需字段: {field}")

    def get_database_config(self) -> Dict[str, Any]:
        db_config = self.config['database'].copy()
        
        db_config['host'] = os.getenv('DB_HOST', db_config['host'])
        db_config['port'] = int(os.getenv('DB_PORT', db_config['port']))
        db_config['database'] = os.getenv('DB_NAME', db_config['database'])
        db_config['user'] = os.getenv('DB_USER', db_config['user'])
        db_config['password'] = os.getenv('DB_PASSWORD', db_config['password'])
        
        return db_config

    def get_pool_config(self) -> Dict[str, Any]:
        pool_config = self.config.get('connection_pool', {})
        
        return {
            'min_connections': int(os.getenv('DB_POOL_MIN', pool_config.get('min_connections', 1))),
            'max_connections': int(os.getenv('DB_POOL_MAX', pool_config.get('max_connections', 10))),
            'connection_timeout': int(os.getenv('DB_POOL_TIMEOUT', pool_config.get('connection_timeout', 30)))
        }

    def get_logging_config(self) -> Dict[str, Any]:
        logging_config = self.config.get('logging', {})
        
        return {
            'level': os.getenv('DB_LOG_LEVEL', logging_config.get('level', 'INFO')),
            'format': logging_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        }