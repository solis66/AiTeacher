"""
咨询上下文装配

职责：把「学情数据 + 历史批改片段 + 教研资料」组装成可注入 prompt 的文本。
不做生成、不拼最终提示词——提示词的措辞与约束由 consultation_service 决定。

本模块解决的核心问题是**范围解析**：同一条提问，落在谁身上？
    - 学生问「我开头总是写不好」        → 范围 = 提问者本人
    - 老师问「李明的学情怎么样」        → 范围 = 李明（且只在本账号的记录内）
    - 学生问「议论文论据怎么用」        → 不涉及具体人，只给教研资料
范围搞错会让建议张冠李戴（把 A 的问题说成 B 的），因此宁可判为"不注入"，
也不要在没把握时猜一个人出来。

身份来源说明（沿用项目既有约定）：
    项目通过 X-Username 请求头做数据隔离，该值由前端填写，不是身份认证手段。
    因此本模块的"角色"不是安全边界，而是**提示级别的意图声明**：
    role='student' / 'auto' 时才允许把"我"解析为学生本人；role='teacher' 时
    必须显式指明学生。真正的数据隔离仍由 `owner` 字段在检索过滤条件里保证。
"""

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rag import knowledge_loader
from rag.review_index import ReviewIndex, render_hits, render_profile
from utils.path_tool import get_abs_path

logger = logging.getLogger(__name__)

# 自指词：出现这些词才可能把范围解析为"提问者本人"
SELF_WORDS = ('我', '自己', '咱')

# 学情词：与作文/写作相关的提问特征。用于判断"这条提问是否与个人写作情况有关"。
# 命中即视为作文话题——咨询入口本身就只处理作文相关问题，所以这个判断是宽松的，
# 宁可多注入一次个人学情（对学生是有益的个性化），也不要漏掉。
STUDY_WORDS = (
    '作文', '写作', '文章', '分数', '得分', '评语', '批改', '学情', '水平', '成绩',
    '弱', '差', '问题', '毛病', '短板', '优势', '优点', '亮点', '提高', '提升',
    '进步', '退步', '改进', '怎么改', '哪里', '哪方面', '总结', '表现', '情况',
    '开头', '结尾', '结构', '选材', '立意', '语言', '错别字', '标点', '字数',
)

# 单次检索的日志文件（JSONL）。命中率是知识库迭代的唯一依据——
# 没有它就无法区分"检索没做好"和"库里根本没有这条"。
LOG_FILE = Path(get_abs_path('logs/consult_retrieval.jsonl'))

_index: Optional[ReviewIndex] = None
_index_lock = threading.Lock()


def get_index() -> ReviewIndex:
    """进程内单例。向量库客户端与指标缓存都应当复用，避免每次咨询重建。"""
    global _index
    if _index is None:
        with _index_lock:
            if _index is None:
                _index = ReviewIndex()
    return _index


# --------------------------------------------------------------------------- 范围解析

def resolve_scope(message: str, owner: str, role: str = 'auto',
                  student_hint: str = '', known_students: Optional[List[str]] = None) -> Dict:
    """
    判断这条提问针对的是谁。

    参数：
        message:        用户提问
        owner:          当前账号（数据隔离键）
        role:           'student' / 'teacher' / 'auto'（默认 auto，按数据自动判断）
        student_hint:   前端显式指定的学生名（老师端选择学生时使用）
        known_students: 当前账号名下出现过的学生名

    返回：
        {'scope': 'self'|'student'|'none', 'student': str,
         'owner_scoped': bool, 'reason': str}
        owner_scoped=True 表示检索时还要按 owner 过滤（老师查自己名下的学生）。
    """
    msg = (message or '').strip()
    owner = (owner or '').strip()
    known = [n for n in (known_students or []) if n and n.strip()]

    # 1) 显式指定学生（老师端下拉选择）
    hint = (student_hint or '').strip()
    if hint:
        if hint == owner:
            return {'scope': 'self', 'student': owner, 'owner_scoped': False, 'reason': '显式指定为本人'}
        return {'scope': 'student', 'student': hint, 'owner_scoped': True, 'reason': '显式指定学生'}

    # 2) 提问里出现已知学生名。取最长匹配，避免简称/单字误命中。
    matched = sorted((n for n in known if len(n) >= 2 and n in msg), key=len, reverse=True)
    if matched:
        name = matched[0]
        if name == owner:
            return {'scope': 'self', 'student': owner, 'owner_scoped': False, 'reason': '提问中出现本人姓名'}
        return {'scope': 'student', 'student': name, 'owner_scoped': True, 'reason': '提问中出现学生姓名'}

    # 3) 教师身份但没指明学生 → 不注入个人学情，避免猜错人
    if role == 'teacher':
        return {'scope': 'none', 'student': '', 'owner_scoped': False, 'reason': '教师身份但未指明学生'}

    # 4) 账号下有多名学生 ⇒ 该账号更像教师账号，此时"我"不能当作某个学生
    #    （数据依据：一个学生账号下只会有一个学生名）
    if role == 'auto' and len(set(known)) > 1:
        return {'scope': 'none', 'student': '', 'owner_scoped': False,
                'reason': '账号下有多名学生（疑似教师），未指明学生'}

    # 5) 学生自指，或提问本身是作文话题 → 注入本人学情做个性化
    if any(w in msg for w in SELF_WORDS) or any(w in msg for w in STUDY_WORDS):
        return {'scope': 'self', 'student': owner, 'owner_scoped': False, 'reason': '本人自指或作文话题'}

    return {'scope': 'none', 'student': '', 'owner_scoped': False, 'reason': '未识别到学情意图'}


# --------------------------------------------------------------------------- 上下文装配

def resolve(message: str, owner: str, role: str = 'auto', student: str = '') -> Dict:
    """
    轻量范围解析（不做检索、不调模型）。

    用途：咨询服务在决定"走固定知识库还是走模型"之前，需要先知道这条提问
    是否针对某个具体的人。针对个人的提问必须走模型并带上真实数据——
    预设知识库里只有通用标准，回答"我记叙文标准掌握得如何"是答非所问。

    任何异常都退化为 scope='none'（即按通用问题处理）。
    """
    try:
        index = get_index()
        index.sync()
        known = index.students()
    except Exception:
        known = []
    return resolve_scope(message, owner, role, student, known)


def build_context(message: str, owner: str, role: str = 'auto', student_hint: str = '') -> Dict:
    """
    组装咨询所需的全部参考资料。

    返回：
        {
          'scope', 'student', 'profile_text', 'cases_text', 'knowledge_text',
          'profile': dict, 'n_cases': int, 'notes': [str], 'debug': {...}
        }
    任何一步失败都只降级该部分内容，绝不让咨询整体失败。
    """
    index = get_index()
    notes: List[str] = []

    # 同步索引：无变化时只有一次轻量查询，可以在每次咨询前调用
    sync_result = {}
    try:
        sync_result = index.sync()
    except Exception as exc:
        notes.append(f'索引同步失败：{exc}')

    try:
        known = index.students()
    except Exception as exc:
        known = []
        notes.append(f'学生名单读取失败：{exc}')

    scope = resolve_scope(message, owner, role, student_hint, known)
    logger.info('[咨询检索] 范围解析 → scope=%s student=%s (%s)',
                scope['scope'], scope['student'], scope['reason'])

    profile_text = ''
    cases_text = ''
    profile: Dict = {}
    hits: List = []

    if scope['scope'] != 'none':
        student = scope['student']
        owner_filter = owner if scope['owner_scoped'] else None
        try:
            profile = index.student_profile(student, owner_filter)
            profile_text = render_profile(profile)
        except Exception as exc:
            notes.append(f'学情聚合失败：{exc}')

        try:
            hits = index.search(message, student, owner=owner_filter)
            cases_text = render_hits(hits)
        except Exception as exc:
            notes.append(f'批改片段检索失败：{exc}')

        if profile and not profile.get('has_data'):
            notes.append(f'{student} 名下暂无已完成的批改记录')

    # 教研资料：学情类提问走检索（方法类资料与"某人学情"关系不大，只取相关小节），
    # 方法类提问在小语料下全文注入。
    try:
        knowledge_text = knowledge_loader.get_context(
            message, force_retrieval=(scope['scope'] != 'none'))
    except Exception as exc:
        knowledge_text = knowledge_loader.NO_REFERENCE_NOTE
        notes.append(f'教研资料加载失败：{exc}')

    result = {
        'scope': scope['scope'],
        'student': scope['student'],
        'profile_text': profile_text,
        'cases_text': cases_text,
        'knowledge_text': knowledge_text,
        'profile': profile,
        'n_cases': len(hits),
        'notes': notes,
        'debug': {
            'reason': scope['reason'],
            'owner': owner,
            'role': role,
            'known_students': known[:20],
            'top_scores': [round(float(s), 4) for _, s in hits[:5]],
            'sync': sync_result,
        },
    }
    _write_log(message, result)
    return result


def _write_log(message: str, result: Dict) -> None:
    """
    记录一次检索的命中情况。

    这是知识库迭代的唯一依据：只有同时看到"问句 / 命中条数 / 最高分 / 范围"，
    才能区分"检索没做好"和"库里根本没有这条内容"。
    """
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            'ts': datetime.now().isoformat(timespec='seconds'),
            'query': (message or '')[:200],
            'scope': result.get('scope'),
            'student': result.get('student'),
            'n_cases': result.get('n_cases'),
            'top_scores': result.get('debug', {}).get('top_scores', []),
            'reason': result.get('debug', {}).get('reason'),
            'notes': result.get('notes', []),
        }
        with LOG_FILE.open('a', encoding='utf-8') as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + '\n')
    except Exception:
        pass


def render_context_block(context: Dict) -> str:
    """
    把上下文渲染成注入 prompt 的文本块。

    每个小节都带明确的用途说明与"没有内容时怎么写"，
    让模型在无资料时降低表述的确定性，而不是编造内容与出处。
    """
    if not context:
        return ''

    parts: List[str] = []

    if context.get('profile_text'):
        parts.append(
            '### 学情数据（系统直接统计，非模型推断，引用时必须与此一致）\n'
            f'{context["profile_text"]}'
        )

    if context.get('cases_text'):
        parts.append(
            '### 该学生历史批改片段（按本次提问检索，共'
            f'{context.get("n_cases", 0)}条）\n{context["cases_text"]}'
        )

    if context.get('knowledge_text'):
        parts.append(f'### 教研参考资料\n{context["knowledge_text"]}')

    if context.get('notes'):
        parts.append('### 资料完整性提示\n' + '；'.join(context['notes']))

    return '\n\n'.join(parts)


def initialize() -> Dict:
    """
    启动时的显式初始化：同步索引并把结果返回给调用方（供启动日志与健康检查使用）。

    刻意不做成"服务启动时同步建库并阻塞等待"——作文很多时首次建索引要调用
    embedding 接口，可能耗时数分钟。这里只在后台线程里跑，失败不影响服务启动。
    """
    def _warm():
        try:
            result = get_index().sync()
            logger.info('[咨询检索] 索引同步完成：%s', result)
            knowledge_loader.ensure_index()
        except Exception as exc:
            logger.warning('[咨询检索] 索引同步失败（不影响服务启动）：%s', exc)

    threading.Thread(target=_warm, daemon=True).start()
    return {'started': True}
