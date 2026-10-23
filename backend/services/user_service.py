"""
用户注册/登录数据服务（基于 PostgreSQL）

职责：
- init_users_table()：启动时创建/升级 users 表，确保管理员账号存在，并执行一次性账号清理。
- create_user()：注册新用户（仅学生），返回生成的用户 ID。
- get_user_by_account()：按账号查询用户（账号查用户）。
- verify_password()：用 bcrypt 校验登录密码。
- record_login() / touch_activity()：记录登录时间与最后活跃时间，供在线状态判断。
- list_users() / get_user_role()：管理员查看用户列表、服务端权限复核。

密码一律采用 bcrypt 加盐哈希存储（结果串自带盐，无需独立 salt 列）。
禁止明文存储、禁止使用无盐 sha256。

账号体系（2026-10 调整）：
- 只保留 admin（管理员）与 student（学生）两种角色，老师角色及其功能已整体移除。
- 管理账号 admin 为管理员角色；其余注册账号一律是学生。
- users 表新增 last_login_at / last_active_at，在线状态按「最后活跃时间在 180 秒内」计算。
- app_migrations 记录一次性迁移的执行状态：账号清理只执行一次，后续启动不会删除新用户。
"""

import logging

import bcrypt
import psycopg2

from utils.db_config import get_connection

logger = logging.getLogger(__name__)

# 管理账号（管理员角色）
TEST_ACCOUNT = 'admin'
TEST_PASSWORD = '123456'
TEST_ROLE = 'admin'

# 账号校验：5~20 位，允许字母、数字、下划线，首字符须为字母或数字。
# 由原先的 ^1\d{10}$（中国大陆 11 位手机号）放宽而来。
ACCOUNT_PATTERN = r'^[A-Za-z0-9][A-Za-z0-9_]{4,19}$'
ACCOUNT_MIN_LENGTH, ACCOUNT_MAX_LENGTH = 5, 20

# 角色定义
VALID_ROLES = ('admin', 'student')
DEFAULT_ROLE = 'student'
ROLE_LABELS = {'admin': '管理员', 'student': '学生'}

# 一次性账号清理的迁移标记（写在 app_migrations 表中）
REMOVE_TEACHER_ACCOUNTS_KEY = 'remove_teacher_accounts_v1'

# 兼容旧引用名（历史上 api.py 通过 user_service.PHONE_PATTERN 取校验正则）
PHONE_PATTERN = ACCOUNT_PATTERN


class DuplicateAccountError(Exception):
    """账号已存在，注册冲突。"""


class DatabaseUnavailableError(Exception):
    """数据库不可用，操作无法完成。"""


# 创建用户表（BIGSERIAL 自增主键 + 唯一账号索引 + bcrypt 哈希 + 角色）
# account 放宽到 VARCHAR(32)：旧结构 11 位只够放手机号，塞不下 admin 这类账号。
# app_migrations 记录一次性数据迁移是否执行过，避免每次启动重复执行破坏性操作。
_CREATE_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS users (
    id BIGSERIAL PRIMARY KEY,
    account VARCHAR(32) NOT NULL UNIQUE,
    password_hash VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL DEFAULT 'student',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_users_account ON users(account);
CREATE TABLE IF NOT EXISTS app_migrations (
    key VARCHAR(64) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
'''

# 老库升级：放宽 account 长度 + 补 role / 在线状态列。全部幂等：
# - 只有当前长度确实小于 32 才 ALTER，避免每次启动都重写整张表；
# - 其余列用 ADD COLUMN IF NOT EXISTS。
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
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;
ALTER TABLE users ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;
'''


def _connect():
    """新建连接；失败抛 DatabaseUnavailableError。"""
    try:
        return get_connection()
    except psycopg2.OperationalError as exc:
        logger.error('[用户服务] 连接数据库失败: %s', exc)
        raise DatabaseUnavailableError('数据库连接失败') from exc


def _to_iso(value):
    """把数据库时间转换为 ISO 字符串；空值原样返回 None。"""
    return value.isoformat() if value else None


def _ensure_admin_account(cur):
    """
    保证管理账号存在且角色为管理员。

    全新库则按文档约定新建；已有账号但角色不是 admin 时校正。
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
    logger.info('[用户服务] 已写入初始管理账号 %s（角色 %s）', TEST_ACCOUNT, TEST_ROLE)


def _cleanup_legacy_users(cur):
    """
    一次性账号清理（需求：除 admin 外的旧用户记录全部清除）。

    以 app_migrations 中的标记作为「是否已执行」的唯一依据：
      - 没有标记 → 首次升级，删除除 admin 外的全部账号，然后写入标记；
      - 有标记   → 已经清理过，直接返回。
    这个标记是硬性要求：否则每次启动都会把后来注册的学生账号一起删掉。
    """
    cur.execute('SELECT 1 FROM app_migrations WHERE key = %s', (REMOVE_TEACHER_ACCOUNTS_KEY,))
    if cur.fetchone():
        return

    # admin 已由 _ensure_admin_account 保证存在；这里再确认一次，避免配置异常时误删全部账号
    cur.execute('SELECT 1 FROM users WHERE account = %s', (TEST_ACCOUNT,))
    if not cur.fetchone():
        logger.warning('[用户服务] 管理账号不存在，跳过一次性账号清理')
        return

    cur.execute('DELETE FROM users WHERE account <> %s', (TEST_ACCOUNT,))
    removed = cur.rowcount
    cur.execute(
        'INSERT INTO app_migrations (key) VALUES (%s) ON CONFLICT (key) DO NOTHING',
        (REMOVE_TEACHER_ACCOUNTS_KEY,),
    )
    logger.info('[用户服务] 一次性账号清理完成：删除 %d 个旧账号（仅保留 %s）',
                removed, TEST_ACCOUNT)


def init_users_table():
    """
    初始化 / 升级 users 表。

    步骤（全部幂等，除一次性清理外）：
        1. 建表（users 与 app_migrations）
        2. 放宽 account 长度、补 role 与在线状态列
        3. 确保管理账号存在且角色为 admin
        4. 一次性清理除 admin 外的旧账号（由 app_migrations 标记保证只执行一次）
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(_CREATE_TABLE_SQL)
            cur.execute(_MIGRATE_SQL)
            _ensure_admin_account(cur)
            _cleanup_legacy_users(cur)
            logger.info('[用户服务] users 表就绪')
    except Exception:
        logger.exception('[用户服务] 初始化 users 表失败')
        raise
    finally:
        conn.close()


def create_user(account, password, role=DEFAULT_ROLE):
    """
    注册新用户（仅学生）。

    参数：
        account: 账号（调用方需先按 ACCOUNT_PATTERN 校验格式）
        password: 明文密码（调用方需先校验长度/字符集）
        role: 只允许 'student'；传入其它值直接报错，便于路由返回明确提示

    返回：
        int - 新用户的自增 ID

    异常：
        ValueError - 角色不是学生
        DuplicateAccountError - 账号已存在
        DatabaseUnavailableError - 数据库不可用
    """
    if role != DEFAULT_ROLE:
        raise ValueError('仅支持创建学生账号')
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            try:
                cur.execute(
                    'INSERT INTO users (account, password_hash, role) VALUES (%s, %s, %s) RETURNING id',
                    (account, password_hash, DEFAULT_ROLE),
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


def get_user_role(account):
    """
    查询账号角色（服务端权限复核用，不信任 token 中的角色声明）。

    返回：
        str | None - 'admin' / 'student'；账号不存在返回 None
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT role FROM users WHERE account = %s', (account,))
            row = cur.fetchone()
            return (row[0] or DEFAULT_ROLE) if row else None
    finally:
        conn.close()


def record_login(account):
    """记录登录时间与最后活跃时间（登录成功时调用）。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                'UPDATE users SET last_login_at = now(), last_active_at = now() WHERE account = %s',
                (account,),
            )
    except DatabaseUnavailableError:
        raise
    finally:
        conn.close()


def touch_activity(account):
    """刷新最后活跃时间（前端心跳接口调用）。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('UPDATE users SET last_active_at = now() WHERE account = %s', (account,))
    except DatabaseUnavailableError:
        raise
    finally:
        conn.close()


def list_users():
    """
    列出全部用户及其在线状态（管理员用户管理使用）。

    在线判定：最后活跃时间在 3 分钟（180 秒）内；admin 固定排在最前。

    返回：
        list - [{account, role, created_at, last_login_at, last_active_at, online}, ...]
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                '''
                SELECT account, role, created_at, last_login_at, last_active_at,
                       (last_active_at IS NOT NULL
                        AND last_active_at > now() - interval '3 minutes') AS online
                FROM users
                ORDER BY (account = %s) DESC, created_at DESC
                ''',
                (TEST_ACCOUNT,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return [
        {
            'account': row[0],
            'role': row[1] or DEFAULT_ROLE,
            'created_at': _to_iso(row[2]),
            'last_login_at': _to_iso(row[3]),
            'last_active_at': _to_iso(row[4]),
            'online': bool(row[5]),
        }
        for row in rows
    ]


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
