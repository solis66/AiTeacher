"""
PostgreSQL 数据库连接配置

统一管理用户注册/登录所需的数据库连接参数。
取值优先级（高 → 低）：
    1. 进程环境变量 PG_*（部署平台注入，无需改代码）
    2. backend/.env 文件（本地开发/快捷配置；KEY=VALUE 逐行解析）
    3. 本地默认值（仅开发机用，指本机 teachears）

连接方式统一走 get_connection() 返回隔离的 psycopg2 connection，
避免业务代码里散落连接串与凭据。
"""

import os
from pathlib import Path

# backend/.env 所在位置（相对本文件：backend/utils/ → backend/）
_ENV_FILE = Path(__file__).resolve().parent.parent / '.env'


def _load_env_file():
    """
    读取 backend/.env 中的 PG_* 变量到 os.environ（不覆盖已存在的进程环境变量）。

    .env 每行一个 KEY=VALUE，支持以 # 开头的注释，值可带单/双引号。
    该文件属敏感配置，已在 .gitignore 中排除，不应提交版本库。
    """
    if not _ENV_FILE.exists():
        return
    try:
        for raw in _ENV_FILE.read_text(encoding='utf-8').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, value = line.partition('=')
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            # 优先级：进程环境变量 > .env，故 .env 不覆盖已存在的值
            if key and key not in os.environ:
                os.environ[key] = value
    except OSError as exc:
        print(f'[db_config] 读取 .env 失败（忽略）: {exc}')


# 模块首次导入即加载 .env
_load_env_file()

# 数据库连接参数（PG_* 环境变量优先，其次 .env，最后本地默认值）
# 注意：密码不提供默认值（由环境变量 / .env 提供），避免将本地/云数据库口令写入版本库。
DB_CONFIG = {
    'host': os.getenv('PG_HOST', '127.0.0.1'),
    'port': int(os.getenv('PG_PORT', '5432')),
    'dbname': os.getenv('PG_DB', 'teachears'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', ''),
}


def get_db_config():
    """返回数据库连接参数字典（copy，避免外部改动全局配置）。"""
    return dict(DB_CONFIG)


def get_connection():
    """
    返回一个新建的 psycopg2 数据库连接。

    异常：
        连接失败时抛出 psycopg2.OperationalError，由调用方决定如何降级/提示。
    """
    import psycopg2
    return psycopg2.connect(**get_db_config())