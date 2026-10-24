"""
咨询记忆存储（滚动摘要 + 长期记忆）

为什么单独一个库：
    会话原文留在 history/*.md（可读、可按天归档），而摘要与长期记忆是派生数据，
    写入频率与生命周期都与原文不同：原文每轮追加，摘要在窗口滑出时更新，
    长期记忆按批次抽取。混进同一张表会让原文表被反复重写，
    也会让派生数据随原文删除一起消失（用户删会话不该丢掉自己的长期画像）。

两张表：
    session_summaries：每个会话一行。covered_upto 记录「已摘要到第几条消息」，
        保证摘要只做增量合并、不重复读旧消息；memory_upto 同理用于长期记忆抽取。
    user_memories：按 owner 隔离的长期记忆条目。embedding 以 float32 BLOB 存储，
        条目少时直接全量注入，条目多时按语义相似度取 top-k（见 memory_service）。

并发：
    摘要与记忆在后台线程写入，请求线程同时读取。用 WAL + busy timeout 让读写不互斥。
"""

import sqlite3
from array import array
from pathlib import Path
from typing import Dict, List, Optional

from utils.path_tool import get_abs_path

_DEFAULT_ROOT = get_abs_path('data/memory')


def pack_embedding(vector: Optional[List[float]]) -> Optional[bytes]:
    """把向量打包成 float32 BLOB（JSON 存 1024 维约 20KB，BLOB 只需 4KB）。"""
    if not vector:
        return None
    return array('f', [float(v) for v in vector]).tobytes()


def unpack_embedding(blob: Optional[bytes]) -> List[float]:
    """把 BLOB 还原成浮点列表；空值或损坏时返回空列表。"""
    if not blob:
        return []
    try:
        values = array('f')
        values.frombytes(blob)
        return list(values)
    except Exception:
        return []


class MemoryStore:
    """摘要与长期记忆的 SQLite 存储。"""

    def __init__(self, root: str = _DEFAULT_ROOT):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'memory.sqlite3'
        with self.connect() as db:
            # WAL：后台线程写入摘要时不阻塞请求线程读取
            db.execute('PRAGMA journal_mode=WAL')
            db.execute(
                'CREATE TABLE IF NOT EXISTS session_summaries ('
                ' owner TEXT NOT NULL,'
                ' session_id TEXT NOT NULL,'
                ' summary TEXT NOT NULL DEFAULT \'\','
                ' covered_upto INTEGER NOT NULL DEFAULT 0,'
                ' memory_upto INTEGER NOT NULL DEFAULT 0,'
                ' updated_at TEXT NOT NULL,'
                ' PRIMARY KEY (owner, session_id))'
            )
            db.execute(
                'CREATE TABLE IF NOT EXISTS user_memories ('
                ' id INTEGER PRIMARY KEY AUTOINCREMENT,'
                ' owner TEXT NOT NULL,'
                ' kind TEXT NOT NULL,'
                ' content TEXT NOT NULL,'
                ' embedding BLOB,'
                ' created_at TEXT NOT NULL,'
                ' updated_at TEXT NOT NULL,'
                ' UNIQUE(owner, content))'
            )
            db.execute('CREATE INDEX IF NOT EXISTS user_memories_owner ON user_memories(owner)')
            # 派生数据的元信息（目前只有"这批向量是用哪个模型算的"）。
            # 单独一张表而不是塞进 user_memories：它是全局状态，不属于任何一条记忆。
            db.execute(
                'CREATE TABLE IF NOT EXISTS memory_meta ('
                ' key TEXT PRIMARY KEY,'
                ' value TEXT NOT NULL,'
                ' updated_at TEXT NOT NULL)'
            )

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    # ------------------------------------------------------------ 会话摘要游标

    def get_session_state(self, owner: str, session_id: str) -> Dict:
        """读取某会话的记忆游标；没有记录时返回空状态（游标为 0）。"""
        with self.connect() as db:
            row = db.execute(
                'SELECT summary, covered_upto, memory_upto FROM session_summaries '
                'WHERE owner=? AND session_id=?',
                (owner, session_id),
            ).fetchone()
        if not row:
            return {'summary': '', 'covered_upto': 0, 'memory_upto': 0}
        return {'summary': row[0] or '', 'covered_upto': int(row[1] or 0), 'memory_upto': int(row[2] or 0)}

    def save_summary(self, owner: str, session_id: str, summary: str,
                     covered_upto: int, memory_upto: int, updated_at: str) -> None:
        """
        写入摘要与两个游标。

        memory_upto 一起写是为了避免覆盖：摘要在后台线程更新时，
        另一个批次可能已经把长期记忆游标推进了，这里用调用方传入的最新值。
        """
        with self.connect() as db:
            db.execute(
                'INSERT INTO session_summaries (owner, session_id, summary, covered_upto, memory_upto, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(owner, session_id) DO UPDATE SET '
                ' summary=excluded.summary, covered_upto=excluded.covered_upto,'
                ' memory_upto=excluded.memory_upto, updated_at=excluded.updated_at',
                (owner, session_id, summary, int(covered_upto), int(memory_upto), updated_at),
            )

    def save_memory_upto(self, owner: str, session_id: str, memory_upto: int, updated_at: str) -> None:
        """只推进长期记忆游标（本次只抽了记忆、没更新摘要时使用）。"""
        with self.connect() as db:
            db.execute(
                'INSERT INTO session_summaries (owner, session_id, summary, covered_upto, memory_upto, updated_at) '
                'VALUES (?, ?, \'\', 0, ?, ?) '
                'ON CONFLICT(owner, session_id) DO UPDATE SET '
                ' memory_upto=excluded.memory_upto, updated_at=excluded.updated_at',
                (owner, session_id, int(memory_upto), updated_at),
            )

    # ------------------------------------------------------------ 长期记忆

    def list_memories(self, owner: str) -> List[Dict]:
        """按最近更新排序取出该账号的全部记忆条目。"""
        with self.connect() as db:
            rows = db.execute(
                'SELECT id, kind, content, embedding, updated_at FROM user_memories '
                'WHERE owner=? ORDER BY updated_at DESC, id DESC',
                (owner,),
            ).fetchall()
        return [
            {'id': row[0], 'kind': row[1], 'content': row[2],
             'embedding': row[3], 'updated_at': row[4]}
            for row in rows
        ]

    def upsert_memory(self, owner: str, kind: str, content: str,
                      embedding: Optional[bytes], now: str) -> None:
        """
        写入一条记忆。

        以 (owner, content) 做唯一约束：同一句话被重复抽取时只刷新时间和类型，
        既避免重复注入，也能让旧记忆被新对话"重新确认"后排到前面。
        """
        with self.connect() as db:
            db.execute(
                'INSERT INTO user_memories (owner, kind, content, embedding, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?, ?) '
                'ON CONFLICT(owner, content) DO UPDATE SET '
                ' kind=excluded.kind,'
                ' embedding=COALESCE(excluded.embedding, user_memories.embedding),'
                ' updated_at=excluded.updated_at',
                (owner, kind, content, embedding, now, now),
            )

    # ------------------------------------------------------------ 向量模型元数据

    def get_meta(self, key: str) -> str:
        """读取元信息；不存在时返回空串。"""
        with self.connect() as db:
            row = db.execute('SELECT value FROM memory_meta WHERE key=?', (key,)).fetchone()
        return (row[0] or '') if row else ''

    def set_meta(self, key: str, value: str, now: str) -> None:
        """写入元信息（覆盖旧值）。"""
        with self.connect() as db:
            db.execute(
                'INSERT INTO memory_meta (key, value, updated_at) VALUES (?, ?, ?) '
                'ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at',
                (key, value, now),
            )

    def list_all_memories(self) -> List[Dict]:
        """取出所有账号的记忆条目（重算向量时用，不按 owner 过滤）。"""
        with self.connect() as db:
            rows = db.execute(
                'SELECT id, content, embedding FROM user_memories ORDER BY id'
            ).fetchall()
        return [{'id': row[0], 'content': row[1], 'embedding': row[2]} for row in rows]

    def update_embedding(self, memory_id: int, embedding: Optional[bytes]) -> None:
        """
        只替换向量，不动 updated_at。

        updated_at 决定"最近记忆优先"的排序与注入顺序；重算向量不是用户产生的新信息，
        改时间会让旧记忆凭空排到最前面。
        """
        with self.connect() as db:
            db.execute('UPDATE user_memories SET embedding=? WHERE id=?', (embedding, int(memory_id)))

    def clear_embeddings(self) -> None:
        """
        清空全部记忆向量。

        用途：向量模型已变更但向量服务此刻不可用。旧模型的向量与新问句不可比，
        留着只会让排序悄悄错乱；清空后退回"按最近更新"的降级路径，语义可接受。
        """
        with self.connect() as db:
            db.execute('UPDATE user_memories SET embedding=NULL')

    def list_memories_missing_embedding(self, limit: int = 64) -> List[Dict]:
        """
        取出向量为空的记忆条目（供补算守卫使用）。

        空向量是"写入时向量服务不可用"留下的：内容有价值必须保留，向量只能后补。
        这里限制单批条数，避免一次补算把外部接口打满。
        """
        with self.connect() as db:
            rows = db.execute(
                'SELECT id, owner, content FROM user_memories '
                'WHERE embedding IS NULL OR length(embedding) = 0 '
                'ORDER BY id LIMIT ?',
                (max(1, int(limit)),),
            ).fetchall()
        return [{'id': row[0], 'owner': row[1], 'content': row[2]} for row in rows]

