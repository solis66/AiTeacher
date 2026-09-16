"""
作文批改工作台服务

职责：把“上传/提交 → 分页与识别 → AI 批改 → 落库 → 查询/保存/导出”串成一条可追踪的流水线。

状态机：
    queued → recognizing → grading → done
                       ↘         ↘
                        failed（任一环节异常，保留 error 原因，可重试）

设计要点（对应需求）：
- 失败即失败：任何环节出错都落到 failed 并记录可读原因，不产生虚假的完成结果
- AI 原始结果（ai_result）与人工修改后的结果（result）分开保存，便于审计与回滚
- 手工批注（marks）独立字段保存，不覆盖 AI 批注
- 记录带 version 乐观锁，避免多窗口互相覆盖
"""

import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from services.review_documents import MAX_PAGES, prepare_pages, validate_upload
from services.review_grader import grade
from services.review_store import ReviewStore

# 允许的年级与体裁（与前端选项一致）
GRADES = ('七年级', '八年级', '九年级')
ESSAY_TYPES = ('议论文', '记叙文', '说明文')


def _now():
    return datetime.now().isoformat(timespec='seconds')


class ReviewWorkbench:
    """批改工作台：负责记录生命周期与文件存储。"""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.store = ReviewStore(self.root)
        # 服务重启后内存中的任务已丢失，把未完成记录明确标记为失败，供用户重试
        self.store.interrupt_pending()

    # ------------------------------------------------------------------ 工具

    def _dir(self, record_id):
        path = self.root / record_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _write(self, record, **changes):
        """带乐观锁的更新：先读最新版本，再写入，冲突时重试一次。"""
        for _ in range(3):
            current = self.store.get(record['id'], record['owner'])
            if current is None:
                return None
            current.update(changes)
            current['updated_at'] = _now()
            try:
                self.store.update(current, record['owner'], current['version'])
                return current
            except ValueError:
                continue
        raise RuntimeError('记录已被其他窗口修改，请刷新后重试')

    # -------------------------------------------------------------- 创建与执行

    def create(self, owner, grade, essay_type, title, requirements, body, uploads, student=None):
        """
        创建一条批改记录并启动后台批改。

        参数：
            owner:        用户名（数据隔离键：谁提交的）
            grade:        年级（七年级/八年级/九年级）
            essay_type:   体裁（议论文/记叙文/说明文，可选；留空由 AI 依据题干要求判定）
            title:        作文题目（可选）
            requirements: 题干要求（可选）
            body:         直接输入的作文正文（可选）
            uploads:      [(原始文件名, 二进制内容)]，按用户排列顺序传入
            student:      作文所属学生（可选）

        关于 owner 与 student 的分工（2026-09 新增）：
            owner 是「提交者 / 租户」，用于数据隔离，沿用既有 X-Username 约定；
            student 是「这篇作文属于哪个学生」，用于学情检索与个性化建议。
            - 学生自己提交：student 留空 → 落库时取 owner，行为与改造前一致
            - 老师代学生提交：student 填学生名
            两者分离的原因：老师的账号下会有很多学生，若把 owner 当学生用，
            老师就无法咨询「某个学生」的学情。

        返回：
            dict: 新建的记录

        异常：
            ValueError: 参数或附件校验不通过
        """
        # ---- 参数校验（不做任何猜测性补全）----
        if grade not in GRADES:
            raise ValueError('请选择有效的年级（七年级/八年级/九年级）')
        # 体裁改为可选：不再强制用户选择，由 AI 依据题干要求判定
        essay_type = (essay_type or '').strip()
        if essay_type and essay_type not in ESSAY_TYPES:
            raise ValueError('请选择有效的作文体裁（议论文/记叙文/说明文）')
        body = (body or '').strip()
        if not body and not uploads:
            raise ValueError('请填写作文正文，或上传作文图片/PDF')
        if len(uploads) > MAX_PAGES:
            raise ValueError(f'一次上传最多{MAX_PAGES}张图片/PDF（将作为同一篇作文批改）')

        # 学生归属：未指定时视为「本人提交」，取 owner。
        # 这样学生自己上传的场景（最常见）不需要前端做任何改动。
        student = (student or '').strip() or (owner or '').strip() or 'anonymous'
        if len(student) > 40:
            raise ValueError('学生姓名过长（最多40个字符）')

        record_id = uuid.uuid4().hex

        # ---- 附件落盘（先校验真实性，再按用户顺序编号）----
        # 注意：目录是在校验之前创建的，任何失败都必须把目录清掉，
        # 否则会在 data/reviews 下留下没有记录归属的空目录。
        directory = self._dir(record_id)
        attachments = []
        try:
            for index, (name, raw) in enumerate(uploads, start=1):
                suffix = validate_upload(name, raw)      # 校验失败直接抛中文提示
                filename = f'att-{index}{suffix}'
                (directory / filename).write_bytes(raw)
                attachments.append({'file': filename,
                                    'kind': 'pdf' if suffix == '.pdf' else 'image',
                                    'name': name})

            record = {
                'id': record_id,
                'owner': owner,
                'student': student,
                'version': 1,
                'status': 'queued',
                'error': None,
                'created_at': _now(),
                'updated_at': _now(),
                'input': {
                    'grade': grade,
                    'essay_type': essay_type,
                    'title': (title or '').strip(),
                    'requirements': (requirements or '').strip(),
                    'body': body,
                },
                'attachments': attachments,
                'pages': [],
                'pages_ready': False,
                'ai_result': None,
                'result': None,
                'marks': [],
            }
            self.store.create(record, owner)
        except Exception:
            shutil.rmtree(directory, ignore_errors=True)
            raise

        # ---- 后台执行，避免请求长时间阻塞 ----
        threading.Thread(target=self._run, args=(record_id, owner), daemon=True).start()
        return record

    def _run(self, record_id, owner):
        """后台流水线：分页识别 → AI 批改 → 落库。"""
        record = self.store.get(record_id, owner)
        if record is None:
            return
        try:
            # 阶段一：分页与识别
            record = self._write(record, status='recognizing')
            directory = self._dir(record_id)
            pages = prepare_pages(record, directory)
            # 页面就绪后立即落库，前端可先看到原文
            record = self._write(record, pages=pages, pages_ready=True, status='grading')

            # 阶段二：AI 批改
            result = grade(record)

            # ai_result 保留模型原始产物；result 为当前生效版本（后续可被人工修改覆盖）
            # input 一并写回：grade 内会根据题干回写实际生效的体裁，需要持久化
            record = self._write(record, status='done', input=record['input'],
                                 ai_result=result, result=result, error=None)
        except Exception as exc:
            # 失败时保留已完成的中间产物（例如页面已渲染好），只标记失败与原因
            try:
                self._write(record, status='failed', error=str(exc)[:500])
            except Exception:
                pass

    def retry(self, record_id, owner):
        """重试失败的记录：复用已有附件与页面，只重跑 AI 批改。"""
        record = self.store.get(record_id, owner)
        if record is None:
            raise ValueError('批改记录不存在')
        if record['status'] not in ('failed', 'done'):
            raise ValueError('当前状态无需重试')
        self._write(record, status='recognizing', error=None)
        threading.Thread(target=self._run, args=(record_id, owner), daemon=True).start()
        return True

    # -------------------------------------------------------------- 查询与保存

    def get(self, record_id, owner):
        return self.store.get(record_id, owner)

    def list(self, owner):
        return self.store.list(owner)

    @staticmethod
    def student_of(record):
        """
        读取记录的学生归属，兼容 student 字段引入之前的历史记录。

        student 字段是 2026-09 新增的；此前的记录没有该字段，
        统一回退为 owner（即「提交者本人」），避免历史数据在学情检索里全部丢失。
        """
        if not record:
            return ''
        return (record.get('student') or '').strip() or (record.get('owner') or '').strip()

    def students(self, owner):
        """
        列出该 owner 名下出现过的全部学生名（去重，按记录数从多到少）。

        用途：老师咨询时用它把「某个学生」识别出来——名单直接从既有数据推导，
        不需要额外维护一张学生表。
        """
        counts = {}
        for record in self.list(owner):
            name = self.student_of(record)
            if name:
                counts[name] = counts.get(name, 0) + 1
        return sorted(counts, key=lambda n: (-counts[n], n))

    def save(self, record_id, owner, expected_version, patch):
        """
        保存人工修改。

        patch 支持覆盖：score / rating / overall_comment / dimensions /
        rewrites / corrections / analysis / highlights / suggestions /
        polished_title / polished_text / marks。

        注意：只合并白名单字段，避免前端越权改写 input/status 等元数据。
        """
        record = self.store.get(record_id, owner)
        if record is None:
            raise ValueError('批改记录不存在')
        if expected_version is not None and int(expected_version) != int(record['version']):
            raise ValueError('记录已更新，请重新加载后再保存')

        allowed = {'score', 'rating', 'overall_comment', 'dimensions', 'rewrites', 'corrections',
                   'analysis', 'highlights', 'suggestions', 'polished_title', 'polished_text'}
        result = dict(record.get('result') or {})
        for key in allowed:
            if key in patch:
                result[key] = patch[key]
        # 分数改动后同步等级，保持两者一致
        if 'score' in patch:
            try:
                score = int(result['score'])
                result['score'] = score
                result['rating'] = patch.get('rating') or ('优' if score >= 40 else '良' if score >= 30 else '需改进')
            except (TypeError, ValueError):
                raise ValueError('分数必须是整数')

        changes = {'result': result}
        if 'marks' in patch:
            changes['marks'] = patch['marks']
        return self._write(record, **changes)

    def page_file(self, record_id, owner, filename):
        """
        返回页面图片路径（带归属校验，防止越权读取他人作文）。

        异常：
            ValueError: 记录不存在或文件名不在该记录中
        """
        record = self.store.get(record_id, owner)
        if record is None:
            raise ValueError('批改记录不存在')
        # 只允许访问该记录内的文件，且必须是已登记页面
        allowed = {p['file'] for p in record.get('pages', [])}
        if Path(filename).name != filename or filename not in allowed:
            raise ValueError('文件不存在')
        path = self._dir(record_id) / filename
        if not path.exists():
            raise ValueError('文件不存在')
        return path

    def export(self, record_id, owner, fmt):
        """按已保存版本导出 PDF。"""
        from utils.export_utils import export_pdf

        record = self.store.get(record_id, owner)
        if record is None:
            raise ValueError('批改记录不存在')
        if record['status'] != 'done' or not record.get('result'):
            raise ValueError('批改尚未完成，无法导出')
        if fmt != 'pdf':
            raise ValueError('不支持的导出格式')
        return export_pdf(record), 'application/pdf'

    def delete(self, record_id, owner):
        """删除记录及其文件目录。"""
        record = self.store.get(record_id, owner)
        if record is None:
            return False
        shutil.rmtree(self.root / record_id, ignore_errors=True)
        with self.store.connect() as db:
            db.execute('DELETE FROM reviews WHERE id=? AND owner=?', (record_id, owner))
        return True
