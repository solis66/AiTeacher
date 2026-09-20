"""
班级与作业数据服务（基于 PostgreSQL）

数据模型：
    classes        —— 班级：老师创建，自动分配 6 位邀请码
    class_members  —— 班级成员：学生凭邀请码加入
    assignments    —— 作文训练（作业）：老师发布到某个班级

提交关系**不额外建表**：学生提交作文走的是既有批改流程（reviews.sqlite3），
只是在批改记录里额外带上 assignment_id；老师的「班级提交」视图按它聚合。
这样批阅工作台、导出、学情报告等既有能力全部复用，不必为新功能重写一遍。

权限模型（一切以服务端为准）：
    - 老师只能操作**自己创建**的班级（classes.teacher = 当前账号）
    - 学生只能看到**自己加入**的班级（class_members.student = 当前账号）
    - 角色取自 users.role，绝不信任前端传来的 role 字段
"""

import logging
import secrets

import psycopg2

from utils.db_config import get_connection

logger = logging.getLogger(__name__)

# 邀请码字符集：去掉 0/O/1/I/L 等易混字符，避免口头传达时认错
_CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
_CODE_LENGTH = 6

CLASS_NAME_MAX = 32
ASSIGNMENT_TITLE_MAX = 100
ASSIGNMENT_REQUIREMENTS_MAX = 1000


class ClassroomError(Exception):
    """班级/作业操作失败；message 可直接展示给用户。"""


_CREATE_TABLES_SQL = '''
CREATE TABLE IF NOT EXISTS classes (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(32) NOT NULL,
    teacher VARCHAR(32) NOT NULL,
    join_code VARCHAR(8) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS class_members (
    id BIGSERIAL PRIMARY KEY,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    student VARCHAR(32) NOT NULL,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (class_id, student)
);

CREATE TABLE IF NOT EXISTS assignments (
    id BIGSERIAL PRIMARY KEY,
    class_id BIGINT NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
    teacher VARCHAR(32) NOT NULL,
    title VARCHAR(100) NOT NULL,
    requirements TEXT NOT NULL DEFAULT '',
    grade VARCHAR(16) NOT NULL DEFAULT '',
    essay_type VARCHAR(16) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS classes_teacher ON classes(teacher);
CREATE INDEX IF NOT EXISTS class_members_student ON class_members(student);
CREATE INDEX IF NOT EXISTS class_members_class ON class_members(class_id);
CREATE INDEX IF NOT EXISTS assignments_class ON assignments(class_id);
'''


def _connect():
    try:
        return get_connection()
    except psycopg2.OperationalError as exc:
        logger.error('[班级服务] 连接数据库失败: %s', exc)
        raise ClassroomError('数据库连接失败，请稍后重试') from exc


def init_tables():
    """建表（幂等），启动时调用一次。"""
    conn = _connect()
    try:
        with conn:
            conn.cursor().execute(_CREATE_TABLES_SQL)
            logger.info('[班级服务] classes / class_members / assignments 表就绪')
    except Exception:
        logger.exception('[班级服务] 初始化班级相关表失败')
        raise
    finally:
        conn.close()


def _generate_join_code(cur):
    """生成未被占用的 6 位邀请码；用 secrets 而非 random，避免可被猜到。"""
    for _ in range(30):
        code = ''.join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
        cur.execute('SELECT 1 FROM classes WHERE join_code = %s', (code,))
        if not cur.fetchone():
            return code
    raise ClassroomError('生成班级邀请码失败，请重试')


def _own_class(cur, class_id, teacher):
    """取班级并校验归属；不是自己的班一律拒绝。"""
    cur.execute('SELECT id, name, teacher, join_code FROM classes WHERE id = %s', (class_id,))
    row = cur.fetchone()
    if not row:
        raise ClassroomError('班级不存在或已被删除')
    if row[2] != teacher:
        raise ClassroomError('只能管理自己创建的班级')
    return {'id': row[0], 'name': row[1], 'teacher': row[2], 'join_code': row[3]}


# ---------------------------------------------------------------- 班级

def create_class(teacher, name):
    """老师创建班级，返回含邀请码的班级信息。"""
    name = (name or '').strip()
    if not name:
        raise ClassroomError('请填写班级名称')
    if len(name) > CLASS_NAME_MAX:
        raise ClassroomError(f'班级名称不能超过{CLASS_NAME_MAX}个字')

    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            code = _generate_join_code(cur)
            cur.execute(
                'INSERT INTO classes (name, teacher, join_code) VALUES (%s, %s, %s) '
                'RETURNING id, name, join_code, created_at',
                (name, teacher, code),
            )
            row = cur.fetchone()
            return {'id': row[0], 'name': row[1], 'join_code': row[2],
                    'created_at': row[3].isoformat(), 'student_count': 0,
                    'assignment_count': 0}
    finally:
        conn.close()


def list_teacher_classes(teacher):
    """老师创建的班级列表，附带学生数与作业数。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT c.id, c.name, c.join_code, c.created_at,
                       (SELECT count(*) FROM class_members m WHERE m.class_id = c.id),
                       (SELECT count(*) FROM assignments a WHERE a.class_id = c.id)
                FROM classes c
                WHERE c.teacher = %s
                ORDER BY c.id DESC
            ''', (teacher,))
            return [{'id': r[0], 'name': r[1], 'join_code': r[2],
                     'created_at': r[3].isoformat(),
                     'student_count': r[4], 'assignment_count': r[5]}
                    for r in cur.fetchall()]
    finally:
        conn.close()


def list_class_members(class_id, teacher):
    """班级学生名单（仅班主任老师可看）。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            _own_class(cur, class_id, teacher)
            cur.execute(
                'SELECT student, joined_at FROM class_members WHERE class_id = %s '
                'ORDER BY joined_at',
                (class_id,),
            )
            return [{'student': r[0], 'joined_at': r[1].isoformat()} for r in cur.fetchall()]
    finally:
        conn.close()


def remove_member(class_id, teacher, student):
    """把学生移出班级。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            _own_class(cur, class_id, teacher)
            cur.execute(
                'DELETE FROM class_members WHERE class_id = %s AND student = %s',
                (class_id, student),
            )
            if cur.rowcount != 1:
                raise ClassroomError('该学生不在此班级中')
    finally:
        conn.close()


def join_class(student, join_code):
    """学生凭邀请码加入班级。"""
    code = (join_code or '').strip().upper()
    if not code:
        raise ClassroomError('请输入班级邀请码')

    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT id, name, teacher FROM classes WHERE join_code = %s', (code,))
            row = cur.fetchone()
            if not row:
                raise ClassroomError('邀请码无效，请向老师确认后重试')
            class_id, name, teacher = row
            if teacher == student:
                raise ClassroomError('这是你自己创建的班级，无需加入')
            cur.execute(
                'SELECT 1 FROM class_members WHERE class_id = %s AND student = %s',
                (class_id, student),
            )
            if cur.fetchone():
                raise ClassroomError(f'你已经在该班级（{name}）中了')
            cur.execute(
                'INSERT INTO class_members (class_id, student) VALUES (%s, %s)',
                (class_id, student),
            )
            return {'id': class_id, 'name': name, 'teacher': teacher, 'join_code': code}
    finally:
        conn.close()


def list_student_classes(student):
    """学生已加入的班级列表。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT c.id, c.name, c.teacher, c.join_code, m.joined_at
                FROM class_members m
                JOIN classes c ON c.id = m.class_id
                WHERE m.student = %s
                ORDER BY m.joined_at DESC
            ''', (student,))
            return [{'id': r[0], 'name': r[1], 'teacher': r[2], 'join_code': r[3],
                     'joined_at': r[4].isoformat()} for r in cur.fetchall()]
    finally:
        conn.close()


def leave_class(student, class_id):
    """学生主动退出班级。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute(
                'DELETE FROM class_members WHERE class_id = %s AND student = %s',
                (class_id, student),
            )
            if cur.rowcount != 1:
                raise ClassroomError('你不在该班级中')
    finally:
        conn.close()


# ---------------------------------------------------------------- 作业

def create_assignment(teacher, class_id, title, requirements, grade, essay_type):
    """老师向自己的班级发布作文训练。"""
    title = (title or '').strip()
    requirements = (requirements or '').strip()
    if not title:
        raise ClassroomError('请填写作文题目')
    if len(title) > ASSIGNMENT_TITLE_MAX:
        raise ClassroomError(f'作文题目不能超过{ASSIGNMENT_TITLE_MAX}个字')
    if len(requirements) > ASSIGNMENT_REQUIREMENTS_MAX:
        raise ClassroomError(f'题干要求不能超过{ASSIGNMENT_REQUIREMENTS_MAX}个字')

    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            info = _own_class(cur, class_id, teacher)
            cur.execute(
                'INSERT INTO assignments (class_id, teacher, title, requirements, grade, essay_type) '
                'VALUES (%s, %s, %s, %s, %s, %s) '
                'RETURNING id, created_at',
                (class_id, teacher, title, requirements, grade or '', essay_type or ''),
            )
            row = cur.fetchone()
            return {'id': row[0], 'class_id': class_id, 'class_name': info['name'],
                    'title': title, 'requirements': requirements,
                    'grade': grade or '', 'essay_type': essay_type or '',
                    'created_at': row[1].isoformat(), 'submitted_count': 0,
                    'student_count': 0}
    finally:
        conn.close()


def list_class_assignments(class_id, teacher):
    """某班的作业列表（含已提交人数 / 班级人数）。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            info = _own_class(cur, class_id, teacher)
            cur.execute('''
                SELECT a.id, a.title, a.requirements, a.grade, a.essay_type, a.created_at,
                       (SELECT count(*) FROM class_members m WHERE m.class_id = a.class_id)
                FROM assignments a
                WHERE a.class_id = %s
                ORDER BY a.id DESC
            ''', (class_id,))
            rows = cur.fetchall()
            out = []
            for r in rows:
                out.append({'id': r[0], 'class_id': class_id, 'class_name': info['name'],
                            'title': r[1], 'requirements': r[2], 'grade': r[3],
                            'essay_type': r[4], 'created_at': r[5].isoformat(),
                            'student_count': r[6], 'submitted_count': 0})
            return out
    finally:
        conn.close()


def list_student_assignments(student):
    """学生可见的作业：来自他已加入的全部班级。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT a.id, a.class_id, c.name, c.teacher, a.title, a.requirements,
                       a.grade, a.essay_type, a.created_at
                FROM assignments a
                JOIN classes c ON c.id = a.class_id
                JOIN class_members m ON m.class_id = a.class_id AND m.student = %s
                ORDER BY a.id DESC
            ''', (student,))
            return [{'id': r[0], 'class_id': r[1], 'class_name': r[2], 'teacher': r[3],
                     'title': r[4], 'requirements': r[5], 'grade': r[6],
                     'essay_type': r[7], 'created_at': r[8].isoformat()}
                    for r in cur.fetchall()]
    finally:
        conn.close()


def delete_assignment(assignment_id, teacher):
    """删除作业（仅发布者本人）。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT teacher FROM assignments WHERE id = %s', (assignment_id,))
            row = cur.fetchone()
            if not row:
                raise ClassroomError('作业不存在或已被删除')
            if row[0] != teacher:
                raise ClassroomError('只能删除自己发布的作业')
            cur.execute('DELETE FROM assignments WHERE id = %s', (assignment_id,))
    finally:
        conn.close()


def get_assignment_owned_by_class(assignment_id, teacher):
    """
    取作业并校验「它是当前老师在自己班里发布的」。
    学生提交、老师查提交都要先过这一关。
    """
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT a.id, a.class_id, a.teacher, a.title, a.requirements,
                       a.grade, a.essay_type, c.name
                FROM assignments a JOIN classes c ON c.id = a.class_id
                WHERE a.id = %s
            ''', (assignment_id,))
            row = cur.fetchone()
            if not row:
                raise ClassroomError('作业不存在或已被删除')
            if row[2] != teacher:
                raise ClassroomError('只能查看自己发布的作业')
            return {'id': row[0], 'class_id': row[1], 'teacher': row[2], 'title': row[3],
                    'requirements': row[4], 'grade': row[5], 'essay_type': row[6],
                    'class_name': row[7]}
    finally:
        conn.close()


def get_assignment_for_student(assignment_id, student):
    """取作业，并校验该学生确实在所属班级里（提交前调用）。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('''
                SELECT a.id, a.class_id, a.teacher, a.title, a.requirements,
                       a.grade, a.essay_type, c.name
                FROM assignments a JOIN classes c ON c.id = a.class_id
                WHERE a.id = %s
            ''', (assignment_id,))
            row = cur.fetchone()
            if not row:
                raise ClassroomError('作业不存在或已被删除')
            class_id = row[1]
            cur.execute(
                'SELECT 1 FROM class_members WHERE class_id = %s AND student = %s',
                (class_id, student),
            )
            if not cur.fetchone():
                raise ClassroomError('你不在该作业所属的班级中，无法提交')
            return {'id': row[0], 'class_id': class_id, 'teacher': row[2], 'title': row[3],
                    'requirements': row[4], 'grade': row[5], 'essay_type': row[6],
                    'class_name': row[7]}
    finally:
        conn.close()


def class_and_assignment_ids(teacher):
    """老师的全部班级 id 与作业 id，用于批量取提交。"""
    conn = _connect()
    try:
        with conn:
            cur = conn.cursor()
            cur.execute('SELECT id FROM classes WHERE teacher = %s', (teacher,))
            class_ids = [r[0] for r in cur.fetchall()]
            if not class_ids:
                return [], []
            marks = ','.join(['%s'] * len(class_ids))
            cur.execute(
                'SELECT id FROM assignments WHERE class_id IN (%s)' % marks, class_ids)
            return class_ids, [r[0] for r in cur.fetchall()]
    finally:
        conn.close()
