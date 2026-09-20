"""
用户注册/登录数据服务（基于 PostgreSQL）

职责：
- init_users_table()：启动时创建/升级 users 表，幂等写入管理测试账号，并完成一次性账号迁移。
- create_user()：注册新用户，返回生成的用户 ID。
- get_user_by_account()：按账号查询用户（账号查用户）。
- verify_password()：用 bcrypt 校验登录密码。

密码一律采用 bcrypt 加盐哈希存储（结果串自带盐，无需独立 salt 列）。
禁止明文存储、禁止使用无盐 sha256。

账号体系（2026-09 调整）：
- 账号由「中国大陆 11 位手机号」放宽为 5~20 位字母数字下划线，兼容 admin 这类短账号；
  旧的 VARCHAR(11) 装不下，故 init 时会做一次列类型放宽。
- 新增 role 列区分老师 / 学生。管理测试账号 admin 为老师角色，拥有全部功能。
- 历史测试账号 13727575721 在升级时被改名/清除；它的存在同时被当作
  「账号迁移是否已执行」的标记，避免每启动一次就误删后来注册的新账号。
"""

import logging

import bcrypt
import psycopg2

from utils.db_config import get_connection

logger = logging.getLogger(__name__)

# 管理测试账号（老师角色，拥有老师账号的全部功能）
TEST_ACCOUNT = 'admin'
TEST_PASSWORD = '123456'
TEST_ROLE = 'teacher'

# 历史测试账号：升级时被改名/清除，同时作为「迁移是否已执行」的标记
LEGACY_TEST_ACCOUNT = '13727575721'

# 账号校验：5~20 位，允许字母、数字、下划线，首字符须为字母或数字。
# 由原先的 ^1\d{10}$（中国大陆 11 位手机号）放宽而来。
ACCOUNT_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_]{4,19}$'
ACCOUNT_MIN_LENGTH, ACCOUNT_MAX_LENGTH = 5, 20

# 角色定义
VALID_ROLES = ('teacher', 'student')
DEFAULT_ROLE = 'student'
ROLE_LABELS = {'teacher': '老师', 'student': '学生'}

# 兼容旧引用名（历史上 api.py 通过 user_service.PHONE_PATTERN 取校验正则）
PHONE_PATTERN = ACCOUNT_PATTERN


class DuplicateAccountError(Exception):
    """账号已存在，注册冲突。"""


class DatabaseUnavailableError(Exception):
    """数据库不可用，操作无法完成。"""


# 创建用户表（BIGSERIAL 自增主键 + 唯一账号索引 + bcrypt 哈希 + 角色）
# account 放宽到 VARCHAR(32)：旧结构 11 位只够放手机号，塞不下 admin 这类账号。
_CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    account VARCHAR(32) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'student',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_account ON users(account);
'''

# 老库升级：放宽 account 长度 + 补 role 列。两段都是幂等的：
# - 只有当前长度确实小于 32 才 ALTER，避免每次启动都重写整张表；
# - role 用 ADD COLUMN IF NOT EXISTS。
# 注意 information_schema 必须限定 public：Supabase 的 auth.users 与本表同名，
# 不限定 schema 会查到别人的列（当初排查时就被这一点误导过）。
_MIGRATE_SQL = '''
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = 'users'
                 AND column_name = 'account' AND character_maximum_length < 32) THEN
        ALTER TABLE users ALTER COLUMN account TYPE VARCHAR(32);
    END IF;
END $$;
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'student';
'''


def _connect():
    """新建连接；失败抛 DatabaseUnavailableError。"""
    try:
        return get_connection()
    except psycopg2.OperationalError as exc:
        logger.error('[用户服务] 连接数据库失败: %s', exc)
        raise DatabaseUnavailableError('数据库连接失败') from exc


def _retire_legacy_accounts(cur):
    """
    一次性账号迁移（需求：历史账号改为管理账号 admin，其余账号清除）。

    以「历史测试账号是否还在」作为「迁移是否已执行」的标记：
      - 还在 → 首次升级，此时完成改名/删除，并清掉其余历史账号；
      - 不在 → 已经迁移过，直接返回。
    这个标记很关键：否则每次容器启动都会把后来注册的师生账号一起删掉。
    """
    cur.execute('SELECT id FROM users WHERE account = %s', (LEGACY_TEST_ACCOUNT,))
    legacy = cur.fetchone()
    if not legacy:
        return

    cur.execute('SELECT id FROM users WHERE account = %s', (TEST_ACCOUNT,))
    if cur.fetchone():
        # admin 已存在：旧账号直接删掉（其名下批改记录由 review_store 的迁移转给 admin）
        cur.execute('DELETE FROM users WHERE id = %s', (legacy[0],))
        logger.info('[用户服务] 已删除历史测试账号 %s', LEGACY_TEST_ACCOUNT)
    else:
        # 直接把旧账号改名：复用它的 bcrypt 哈希，密码保持不变
        cur.execute(
            'UPDATE users SET account = %s, role = %s WHERE id = %s',
            (TEST_ACCOUNT, TEST_ROLE, legacy[0]),
        )
        logger.info('[用户服务] 历史测试账号 %s 已改名为 %s（密码与哈希保持不变）',
                    LEGACY_TEST_ACCOUNT, TEST_ACCOUNT)

    # 清掉其余历史账号，只保留管理账号
    cur.execute('SELECT count(*) FROM users WHERE account <> %s', (TEST_ACCOUNT,))
    removed = cur.fetchone()[0]
    if removed:
        cur.execute('DELETE FROM users WHERE account <> %s', (TEST_ACCOUNT,))
        logger.info('[用户服务] 已清除 %d 个历史账号（仅保留 %s）', removed, TEST_ACCOUNT)


def _ensure_admin_account(cur):
    """
    保证管理测试账号存在且角色为老师。

    若既没有 admin 也没有历史账号（全新库），则按文档约定新建一个。
    """
    cur.execute('SELECT id, role FROM users WHERE account = %s', (TEST_ACCOUNT,))
    row = cur.fetchone()
    if row:
        if row[1] != TEST_ROLE:
            cur.execute('UPDATE users SET role = %s WHERE id = %s', (TEST_ROLE, row[0]))
            logger.info('[用户服务] 管理账号 %s 的角色已校正为 %s', TEST_ACCOUNT, TEST_ROLE)
        return

    password_hash = bcrypt.hashpw(TEST_PASSWORD.encode(), bcrypt.gensalt()).decode()
    cur.execute(
        'INSERT INTO users (account, password_hash, role) VALUES (%s, %s, %s)',
        (TEST_ACCOUNT, password_hash, TEST_ROLE),
    )
    logger.info('[用户服务] 已写入初始管理测试账号 %s（角色 %s）', TEST_ACCOUNT, TEST_ROLE)


def init_users_table():
    """
    初始化 / 升级 users 表。

    步骤（全部幂等）：
        1. 建表（不存在时）
        2. 放宽 account 长度、补 role 列
        3. 一次性账号迁移（历史账号 → admin，其余清除）
        4. 确保管理账号存在且角色正确
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(_CREATE_TABLE_SQL)
            cur.execute(_MIGRATE_SQL)
            _retire_legacy_accounts(cur)
            _ensure_admin_account(cur)
            logger.info('[用户服务] users 表就绪')
    except Exception:
        logger.exception('[用户服务] 初始化 users 表失败')
        raise
    finally:
        conn.close()


def create_user(account, password, role=DEFAULT_ROLE):
    """
    注册新用户。

    参数：
        account: 账号（调用方需先按 ACCOUNT_PATTERN 校验格式）
        password: 明文密码（调用方需先校验长度/字符集）
        role: 'teacher' 或 'student'

    返回：
        int - 新用户的自增 ID

    异常：
        DuplicateAccountError - 账号已存在
        DatabaseUnavailableError - 数据库不可用
    """
    if role not in VALID_ROLES:
        role = DEFAULT_ROLE
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    'INSERT INTO users (account, password_hash, role) VALUES (%s, %s, %s) RETURNING id',
                    (account, password_hash, role),
                )
                row = cur.fetchone()
                return row[0]
            except psycopg2.errors.UniqueViolation:
                # 并发/重复注册：唯一索引兜底。with conn 会回滚此事务。
                raise DuplicateAccountError('该账号已注册') from None
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
    按账号查询用户。

    返回：
        dict | None - {id, account, password_hash, role}；不存在返回 None
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                'SELECT id, account, password_hash, role FROM users WHERE account = %s',
                (account,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {'id': row[0], 'account': row[1], 'password_hash': row[2],
                    'role': row[3] or DEFAULT_ROLE}
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
