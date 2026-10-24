"""
混合检索重排（向量召回 + 字面覆盖）

为什么需要：
    只用向量相似度时，短问句（"开头怎么写"）与长评语片段之间的匹配很容易被
    通用词稀释——一篇评语里明明写着"开头空洞"，却可能排在讲"结构"的片段后面。
    而"开头"这种字面高度重合的信号，恰恰是判官最可靠的依据之一。

做法（刻意保守）：
    1. 召回仍走向量检索，只把候选集扩大到 k * factor；
    2. 对候选按「向量分 × 权重 + 问句字面覆盖率 × 权重」重排；
    3. 相似度阈值仍作用在**向量分**上，不作用在混合分上——
       0.20 是按向量尺度实测标定的（见 config/chroma.yaml 注释），
       混入 0~1 的字面分后阈值会整体漂移，等于把标定结果作废。

中文没有空格，这里不做分词器依赖：按二元字组切分（"开头怎么写" →
我开/开头/头怎/怎么/么写），虚词字组直接丢弃。这个粒度对短问句足够，
也不会像单字切分那样把所有片段都算成"命中"。
"""

import re
from typing import List, Sequence, Tuple

# 高频虚词：两个字都是虚词的字组没有区分度
_STOP_CHARS = set('的了和是在我你他她它也就都又而及与或把被让给对从向于为以之其这那有没不很还个们着过地得')

_ALNUM = re.compile(r'[A-Za-z0-9_]+')
_CJK = re.compile(r'[\u4e00-\u9fff]+')


def tokenize(text: str) -> set:
    """中文二元字组 + 英文数字词。空文本返回空集合。"""
    text = (text or '').strip()
    if not text:
        return set()

    tokens = {word.lower() for word in _ALNUM.findall(text)}
    for run in _CJK.findall(text):
        if len(run) == 1:
            tokens.add(run)
            continue
        for index in range(len(run) - 1):
            gram = run[index:index + 2]
            if gram[0] in _STOP_CHARS and gram[1] in _STOP_CHARS:
                continue
            tokens.add(gram)
    return tokens


def lexical_coverage(query_tokens: set, text: str) -> float:
    """问句字面被片段覆盖的比例（0~1）。"""
    if not query_tokens:
        return 0.0
    matched = query_tokens & tokenize(text)
    return len(matched) / len(query_tokens)


def rerank(query: str, candidates: Sequence[Tuple], k: int,
           vector_weight: float = 0.7, lexical_weight: float = 0.3) -> List[Tuple]:
    """
    对向量召回结果做混合重排。

    参数：
        query:      检索问句（案例检索时是「问题 + 学情画像」拼出来的，见 consult_context）
        candidates: [(Document, vector_score), ...]，已通过阈值过滤
        k:          最终保留条数
        vector_weight / lexical_weight: 两路信号的权重

    返回：
        [(Document, vector_score), ...]，长度不超过 k。
        分数仍返回原始向量分——下游日志与阈值判断都按向量尺度解释。
    """
    if not candidates:
        return []

    limit = max(1, int(k))
    tokens = tokenize(query)
    if not tokens:
        return list(candidates[:limit])

    scored = []
    for doc, vector_score in candidates:
        try:
            coverage = lexical_coverage(tokens, getattr(doc, 'page_content', '') or '')
            blended = vector_weight * float(vector_score or 0) + lexical_weight * coverage
        except Exception:
            # 单条候选异常不影响整体检索：退回纯向量分
            blended = float(vector_score or 0)
        scored.append((blended, doc, vector_score))

    scored.sort(key=lambda item: item[0], reverse=True)
    return [(doc, vector_score) for _, doc, vector_score in scored[:limit]]
