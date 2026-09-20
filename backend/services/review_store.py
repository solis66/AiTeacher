"""批改记录独立存储；原始结果和人工编辑版本分开保存。"""
import json
import sqlite3
from pathlib import Path


class ReviewStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'reviews.sqlite3'
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, owner TEXT NOT NULL, version INTEGER NOT NULL, payload TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS reviews_owner ON reviews(owner)')
            self._upgrade_schema(db)

    @staticmethod
    def _upgrade_schema(db):
        """
        老库升级：补出「按作业汇总班级提交」需要的列。

        SQLite 的 ADD COLUMN 不支持 IF NOT EXISTS，只能先读 PRAGMA table_info 判断 ——
        否则第二次启动就会因 duplicate column name 直接崩掉。
          - assignment_id：老师按作业查看全班提交时的查询键
          - student：冗余落列，跨学生汇总时不必解析 payload
        """
        cols = {row[1] for row in db.execute('PRAGMA table_info(reviews)').fetchall()}
        if 'assignment_id' not in cols:
            db.execute('ALTER TABLE reviews ADD COLUMN assignment_id TEXT')
        if 'student' not in cols:
            db.execute('ALTER TABLE reviews ADD COLUMN student TEXT')
        db.execute('CREATE INDEX IF NOT EXISTS reviews_assignment ON reviews(assignment_id)')

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def create(self, record, owner):
        # 必须显式列出列名：表结构升级后列数已多于 4，省略列名的 INSERT 会直接报错。
        with self.connect() as db:
            db.execute(
                'INSERT INTO reviews (id, owner, version, payload, assignment_id, student) '
                'VALUES (?, ?, ?, ?, ?, ?)',
                (record['id'], owner, record['version'],
                 json.dumps(record, ensure_ascii=False),
                 record.get('assignment_id') or None,
                 record.get('student') or None),
            )

    def get(self, record_id, owner):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM reviews WHERE id=? AND owner=?', (record_id, owner)).fetchone()
        return json.loads(row[0]) if row else None

    def get_any(self, record_id):
        """
        按 id 取记录，**不做 owner 过滤**。

        仅供需要「代查看」的场景使用（老师在班级里查看学生提交的批改结果）。
        调用方必须先自行完成权限校验——这里刻意不提供任何保护，
        直接对外暴露会绕过全部数据隔离。
        """
        with self.connect() as db:
            row = db.execute('SELECT payload FROM reviews WHERE id=?', (record_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, owner):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM reviews WHERE owner=? ORDER BY rowid DESC LIMIT 200', (owner,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def list_by_assignment_ids(self, assignment_ids):
        """
        取一组作业下的全部提交（跨学生）。

        用途：老师查看班级内所有学生提交的批改结果。这里刻意不按 owner 过滤 ——
        所以调用方必须先确认这些作业确实属于当前老师，否则会越权读到别人的数据。
        每条记录带上 owner，便于前端标注提交者。
        """
        ids = [str(x) for x in (assignment_ids or []) if x]
        if not ids:
            return []
        marks = ','.join('?' * len(ids))
        with self.connect() as db:
            rows = db.execute(
                'SELECT owner, payload FROM reviews WHERE assignment_id IN (%s) '
                'ORDER BY rowid DESC LIMIT 500' % marks, ids).fetchall()
        out = []
        for owner, payload in rows:
            record = json.loads(payload)
            record['owner'] = owner
            out.append(record)
        return out

    def update(self, record, owner, expected):
        # 乐观锁阻止多个窗口覆盖彼此修改，也用于防止重复重试任务。
        record['version'] = expected + 1
        with self.connect() as db:
            result = db.execute('UPDATE reviews SET version=?, payload=? WHERE id=? AND owner=? AND version=?',
                                (record['version'], json.dumps(record, ensure_ascii=False), record['id'], owner, expected))
            if result.rowcount != 1:
                raise ValueError('记录已更新，请重新加载后再保存')

    def interrupt_pending(self):
        # 服务重启后无法继续内存任务，明确标记失败以便用户重试。
        with self.connect() as db:
            rows = db.execute('SELECT id, payload FROM reviews').fetchall()
            for record_id, payload in rows:
                record = json.loads(payload)
                if record['status'] in ('queued', 'recognizing', 'grading'):
                    record.update(status='failed', error='服务重启导致批改中断，请重试', version=record['version'] + 1)
                    db.execute('UPDATE reviews SET version=?, payload=? WHERE id=?', (record['version'], json.dumps(record, ensure_ascii=False), record_id))

    def migrate_owner(self, old_owner, new_owner):
        """
        把某个账号名下的批改记录整体转归到另一个账号（账号改名用）。

        为什么必须做：批改记录以 owner 作为唯一隔离键，查询一律带 `WHERE owner=?`。
        账号一旦改名，原记录就再也查不出来 —— 数据还在库里，界面上却「全部消失了」，
        很容易被误判成数据丢失。

        幂等：old_owner 名下没有记录时不做任何事，可以安全地在每次启动时调用。

        返回：实际迁移的记录数
        """
        if not old_owner or not new_owner or old_owner == new_owner:
            return 0
        with self.connect() as db:
            result = db.execute('UPDATE reviews SET owner=? WHERE owner=?', (new_owner, old_owner))
            return result.rowcount
