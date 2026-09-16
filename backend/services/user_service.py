"""
用户注册/登录数据服务（基于 PostgreSQL）

职责：
- init_users_table()：启动时创建 users 表（缺省则建），并幂等写入文档约定的测试账号。
- create_user()：注册新用户，返回生成的用户 ID。
- get_user_by_account()：按手机号查询用户（账号查用户）。
- verify_password()：用 bcrypt 校验登录密码。

密码一律采用 bcrypt 加盐哈希存储（结果串自带盐，无需独立 salt 列）。
禁止明文存储、禁止使用无盐 sha256。
"""

import logging

import bcrypt
import psycopg2

from utils.db_config import get_connection

logger = logging.getLogger(__name__)

# 文档约定的初始测试账号
TEST_ACCOUNT = '13727575721'
TEST_PASSWORD = '123456'

# 手机号校验：中国大陆 11 位手机号
PHONE_PATTERN = r'^1\d{10}$'


class DuplicateAccountError(Exception):
    """手机号已存在，注册冲突。"""


class DatabaseUnavailableError(Exception):
    """数据库不可用，操作无法完成。"""


# 创建用户表（BIGSERIAL 自增主键 + 唯一手机号索引 + bcrypt 哈希）
_CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    account VARCHAR(11) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_account ON users(account);
'''


def _connect():
    """新建连接；失败抛 DatabaseUnavailableError。"""
    try:
        return get_connection()
    except psycopg2.OperationalError as exc:
        logger.error('[用户服务] 连接数据库失败: %s', exc)
        raise DatabaseUnavailableError('数据库连接失败') from exc


def init_users_table():
    """
    初始化 users 表并幂等写入测试账号。

    仅在表不存在时建表；测试账号不存在时以 bcrypt 哈希插入（已存在则跳过）。
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(_CREATE_TABLE_SQL)
            cur.execute('SELECT 1 FROM users WHERE account = %s', (TEST_ACCOUNT,))
            if not cur.fetchone():
                password_hash = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt()).decode()
                cur.execute(
                    'INSERT INTO users (account, password_hash) VALUES (%s, %s)',
                    (TEST_ACCOUNT, password_hash),
                )
                logger.info('[用户服务] 已写入初始测试账号 %s', TEST_ACCOUNT)
            logger.info('[用户服务] users 表就绪')
    except Exception:
        logger.exception('[用户服务] 初始化 users 表失败')
        raise
    finally:
        conn.close()


def create_user(account, password):
    """
    注册新用户。

    参数：
        account: 手机号（调用方需先按 PHONE_PATTERN 校验格式）
        password: 明文密码（调用方需先校验长度/字符集）

    返回：
        int - 新用户的自增 ID

    异常：
        DuplicateAccountError - 手机号已存在
        DatabaseUnavailableError - 数据库不可用
    """
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    'INSERT INTO users (account, password_hash) VALUES (%s, %s) RETURNING id',
                    (account, password_hash),
                )
                row = cur.fetchone()
                return row[0]
            except psycopg2.errors.UniqueViolation:
                # 并发/重复注册：唯一索引兜底。with conn 会回滚此事务。
                raise DuplicateAccountError('该手机号已注册') from None
    except DuplicateAccountError:
        raise
    except DatabaseUnavailableError:
        raise
    except psycopg2.OperationalError as exc:
        logger.error('[用户服务] 注册时数据库连接失败: %s', exc)
        raise DatabaseUnavailableError('数据库连接失败') from exc
    except Exception:
        logger.exception('[用户服务] 注册用户失败: %s', account)
        raise
    finally:
        conn.close()


def get_user_by_account(account):
    """
    按手机号查询用户。

    返回：
        dict | None - {id, account, password_hash}；不存在返回 None
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT id, account, password_hash FROM users WHERE account = %s',
                (account,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {'id': row[0], 'account': row[1], 'password_hash': row[2]}
    except DatabaseUnavailableError:
        raise
    finally:
        conn.close()


def verify_password(user, password):
    """
    校验登录密码（bcrypt 比对）。

    参数：
        user: get_user_by_account 返回的用户 dict
        password: 用户输入的明文密码

    返回：
        bool - 通过与否
    """
    if not user:
        return False
    try:
        return bcrypt.checkpw(password.encode(), user['password_hash'].encode())
    except ValueError:
        # 存量哈希格式异常时视为校验失败，不抛给上层
        logger.warning('[用户服务] 用户 %s 的密码哈希格式异常', user['account'])
        return False