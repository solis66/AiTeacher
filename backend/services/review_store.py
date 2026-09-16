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

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def create(self, record, owner):
        with self.connect() as db:
            db.execute('INSERT INTO reviews VALUES (?, ?, ?, ?)', (record['id'], owner, record['version'], json.dumps(record, ensure_ascii=False)))

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
