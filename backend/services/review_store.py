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
        老库升级：补出 student 冗余列（跨学生汇总时不必解析 payload）。

        SQLite 的 ADD COLUMN 不支持 IF NOT EXISTS，只能先读 PRAGMA table_info 判断 ——
        否则第二次启动就会因 duplicate column name 直接崩掉。
        """
        cols = {row[1] for row in db.execute('PRAGMA table_info(reviews)').fetchall()}
        if 'student' not in cols:
            db.execute('ALTER TABLE reviews ADD COLUMN student TEXT')

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def create(self, record, owner):
        # 必须显式列出列名：表结构缺省值较多，省略列名的 INSERT 容易随升级错位。
        with self.connect() as db:
            db.execute(
                'INSERT INTO reviews (id, owner, version, payload, student) '
                'VALUES (?, ?, ?, ?, ?)',
                (record['id'], owner, record['version'],
                 json.dumps(record, ensure_ascii=False),
                 record.get('student') or None),
            )

    def get(self, record_id, owner):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM reviews WHERE id=? AND owner=?', (record_id, owner)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self, owner):
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM reviews WHERE owner=? ORDER BY rowid DESC LIMIT 200', (owner,)).fetchall()
        return [json.loads(row[0]) for row in rows]

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

    # 说明：账号改名迁移方法已随「旧账号一次性清理」需求移除。
    # 当前账号体系统一为学生，管理员只通过 owner 只读查看记录，不再改账号归属。
