# 咨询链路 RAG 检索服务设计

> 目标：给学生 / 老师与 AI 的咨询对话接上知识检索能力。
> 日期：2026-09-15
> 结论先行：**现有 RAG 在咨询链路上是完全空转的（实测三重断点），不能"接上"，只能"重建"——但要复用它已有的向量设施。**

---

## 1. 现状诊断（全部为实测结果，非推断）

### 1.1 向量库是空的

直接读取 `chroma_db/chroma.sqlite3`：

```
collections        : 1  →  name = "agent"
embeddings         : 0 条
embedding_metadata : 0 条
retriever.invoke("议论文的论点怎么写") → 0 条命中
```

collection 之所以存在，是因为 `agent_tools.py:5` 在模块导入时就 `rag = RagSummarizeService()`，进而 `vector_store.py:14` 创建了 collection。**但 `load_document()`（`vector_store.py:30`）全项目从未被调用**，只出现在文件末尾的注释代码里（`vector_store.py:107-111`）。

结论：**咨询链路里的"RAG 检索"目前检索不到任何东西。**

### 1.2 三重断点

| # | 断点位置 | 具体问题 | 证据 |
|---|---|---|---|
| ① | `agent_tools.py:9-20` | `rag_summarize` 被注册为 agent 的唯一检索工具（`react_agent.py:93`），但它的返回值是**整份批改 JSON**，不是检索片段 | 签名 `rag_summarize(query, essay_type) -> str`，内部走 `RagSummarizeService.rag_summarize`（`rag_service.py:368`）→ `prompts/rag_summarize.txt` 批改模板 |
| ② | `rag_service.py:419-423` | 向量检索被包在 `if not criteria:` 里。而 `criteria = load_criteria_by_type()` → `load_unified_standard()` 有**内置兜底文本**（`standard_loader.py:28-73`），**恒非空** | `retriever_docs()` 在这条路径上永不可达 |
| ③ | `chroma_db/chroma.sqlite3` | 向量库 0 条数据（见 1.1） | 即使 ② 通了也检索不到 |

**①的后果最严重**：学生问"议论文的论点怎么写"，agent 判断"需要查资料"→ 调用 `rag_summarize("议论文的论点怎么写")` → `detect_essay_type` 对**问题文本**做体裁判断 → 送进批改模板 → 返回一份"总分 XX / 各项评分"的假批改结果。

**答非所问，而且每次白烧一次 36s 的大模型调用**（`config/rag.yaml:15` 实测批改耗时）。

### 1.3 即使灌了数据，也灌不到什么

```yaml
# config/chroma.yaml
data_path: data                                    # 不递归
allowed_knowledge_file_type: ["txt"]
```

`data/` 下**只有一个 txt**：`广东省中考作文评分标准.txt`。

而这份内容**本来就通过 `load_unified_standard()` 直接进了 prompt**（`consultation_service.py:261`）。也就是说：索引它 = 把已经在上下文里的东西再检索一遍，收益为零。

另外 `listdir_with_allowed_type`（`file_handler.py:41-51`）用 `os.listdir` **不递归**，`data/reviews/**/*.jpg` 之类永远进不了库。

### 1.4 咨询的知识来源目前是硬编码

`_essay_knowledge`（`consultation_service.py:91-94`）是一个 6 键的 dict，靠 `_get_knowledge_response`（`:446-523`）做**关键词匹配**——匹配体裁词 + 类型词（标准/技巧/开头/结尾/提高/如何/怎样/怎么/方法），命中则返回对应文本。

**这才是当前咨询问答实际依赖的知识源。**它有三个固有限制：

- 加一条知识要改代码、重启服务
- 只能命中 6 个预设话题，换个问法就落空
- 反过来说，它是**可控的**——这句话在设计时要记住（见 §6.1）

### 1.5 一个被忽略的漏洞

`_build_consultation_prompt`（`consultation_service.py:678-711`）里第 3 条回答要求写着：

> 3. 结合初中作文评分标准进行专业分析

**但评分标准根本没有进这个 prompt。** prompt 里只有"问题 + 回答要求"。模型只能靠训练记忆编造评分标准——这是当前咨询质量差的一个直接原因，而且**修它不需要 RAG**（见 §6）。

---

## 2. 核心区分：批改 RAG ≠ 咨询 RAG

现在项目里只有"批改 RAG"，它和"咨询 RAG"是两种东西，被混为一谈了：

| 维度 | 批改 RAG（已有） | 咨询 RAG（要建） |
|---|---|---|
| 输入 | 一整篇作文（500~800 字） | 一个问句（10~30 字） |
| 输出 | 结构化 JSON 评分 | 若干条知识片段 |
| 在 prompt 中的角色 | **辅依据**（评分参照） | **论据**（回答依据） |
| 关键约束 | 必须评全维度、可解释、不能拒答 | 必须**只答问到的**、不跑题、**可以拒答** |
| 命中失败时 | 用兜底标准继续评 | 明说"没找到相关资料"，不硬编 |
| 调用频率 | 一篇一次 | 一条消息一次（含追问） |

这个差别决定了架构：**不能复用 `RagSummarizeService` 的入口，只能复用它内部的 `VectorStoreService`。**

现在 `rag_service.py:230-231` 把 `VectorStoreService` 和 `retriever` 私有地关在 `RagSummarizeService.__init__` 里，咨询拿不到。咨询需要的是：

```python
retrieve(query) -> list[tuple[Document, float]]     # 片段 + 分数
```

而不是：

```python
rag_summarize(query) -> str                          # 一份批改 JSON
```

---

## 3. 目标架构

### 3.1 写入与读取分离，中间靠向量库解耦

```
离线 · 建库                          在线 · 咨询
─────────────                       ─────────────
data/knowledge/**.md                学生/老师提问
      │                                    │
      ▼                                    ▼
load_documents()                     KnowledgeRetriever.retrieve()
      │                                    │
      └──────►  Chroma  ◄──────────────────┘
              consult_knowledge
              (与批改用的 agent 分开)
```

### 3.2 三层职责

| 层 | 文件 | 职责 | 明确不做 |
|---|---|---|---|
| **建库层** | `rag/knowledge_loader.py`（新增） | 扫 `data/knowledge/**`，切块，打 metadata，写库；按文件 md5 去重 | 不做检索，不做生成 |
| **检索层** | `rag/knowledge_retriever.py`（新增） | `retrieve(query, role, k, threshold)` → 带分数的片段列表 | 不做生成，不拼 prompt |
| **注入层** | `consultation_service.py`（改） | 把片段渲染成 prompt 段落，处理空结果 | 不做检索，不碰向量库 |

**三个文件，职责不重叠。**混在一起（像现在 `RagSummarizeService` 那样把建库/检索/生成全塞一个类）是这类系统最先腐烂的地方。

---

## 4. 检索层设计（核心）

### 4.1 独立 collection，不复用 `agent`

```python
COLLECTION = 'consult_knowledge'     # 批改用 'agent'，两者不共享
```

**理由**：批改库装的是权威评分标准，检索参数是 `k=3`；咨询库装的是写作方法、病句示例、修辞讲解。混在一个 collection 里，`k=3` 会被评分标准片段挤满——而评分标准已经在 prompt 里了，等于白检。

### 4.2 必须拿到分数，必须设阈值

当前 `get_retriever()`（`vector_store.py:27-28`）用 `as_retriever(search_kwargs={"k": 3})`——**封装把相似度分数丢了**，无法做阈值过滤。

改用：

```python
vector_store.similarity_search_with_relevance_scores(query, k=k)
# → [(Document, score), ...]
```

然后在检索层**强制阈值**：

```python
hits = [(d, s) for d, s in raw if s >= SCORE_THRESHOLD]   # 建议 0.35 起步
```

**低分片段直接丢弃。**这是咨询 RAG 与批改 RAG 最重要的行为差别：

- 批改场景**不能拒答**（必须给分），所以无关片段也得留着当背景
- 咨询场景**必须能拒答**——塞一段无关材料给模型，它会被诱导着强行引用，产生幻觉且更自信

### 4.3 metadata 设计：为「学生 / 老师」分叉预留

每个 chunk 带：

```json
{
  "topic": "开头",
  "genre": "通用",
  "audience": "student",
  "grade": "初中",
  "source": "写作方法/开头.md",
  "chunk_index": 2
}
```

`audience` 是这个项目的关键字段：**学生问"怎么把开头写好"，老师问"这类开头在评分标准里归到哪一档"**——同一话题，需要的是两份不同材料。检索时按角色过滤：

```python
filters = {"audience": {"$in": [role, "both"]}}
```

注意：`langchain_chroma` 的 `Chroma` 构造时可以传 `collection_metadata`，但**按 metadata 过滤必须在查询时用 `filter=` 参数**——`as_retriever()` 的 `search_kwargs` 也支持传 `filter`，但既然要分数，统一走 `similarity_search_with_relevance_scores(query, k=k, filter=...)`。

### 4.4 切片参数要单独配，不能沿用批改的

```yaml
# config/chroma.yaml 现在是给评分标准那种短条目调的
chunk_size: 200
chunk_overlap: 20
```

一条"如何写好开头"的教研材料通常是 300~500 字的方法论。切 200 字会把一条完整方法截成半句，检索出来的片段自己都读不通。

建议**咨询库单独一组参数**（放进 `config/chroma.yaml` 新增节点，不要改批改的）：

```yaml
consult:
  collection_name: consult_knowledge
  data_path: knowledge            # 相对项目根，与批改的 data/ 分开
  chunk_size: 400
  chunk_overlap: 50
  k: 4
  score_threshold: 0.35
```

### 4.5 建库要挂进启动流程

`load_document()` 现在没有任何调用点——这是 1.1 的根因。**不能靠人手动跑。**

```python
# api.py 启动时（或首次咨询惰性触发）
def ensure_knowledge_indexed():
    """collection 为空则建库；非空则按 md5 增量补档。"""
```

两个约束：
- **不能同步阻塞启动太久**：embedding 是网络调用（`qwen3.7-text-embedding`），500 个 chunk 约 1~3 分钟。放后台线程（复用 `review_workbench.py:147` 的 `threading.Thread(daemon=True)` 模式）
- **失败要可见**：建库失败不能让咨询直接崩，降级为"无参考资料"继续

---

## 5. 接入咨询链路：两种方式，建议并存

### 5.1 方案对比

**方案 A：作为工具交给 agent 自主决定**

```python
@tool(description="检索教研知识库，返回与问题相关的教学资料片段")
def search_knowledge(query: str) -> str: ...
```

- 优点：灵活，模型自己决定查不查、查几次、要不要换个说法再查
- 缺点：**不可控**。模型可能不查直接答、可能查了不用、可能反复查。而且 `prompts/main_prompt.txt:9` 现有那句"若 5 次工具调用后仍信息不足，则回复用户：我不知道"会让它在检索为空时**直接拒答**
- 适合：开放式、无法预判的问题

**方案 B：作为前置步骤确定性检索（建议做默认）**

在 `_generate_ai_response` 里**调模型之前**先检索，把片段拼进 prompt。

- 优点：**每次必查、必进上下文、行为可预测**；不占工具调用轮次；不受模型"想不想查"影响
- 缺点：无关问题也要付一次 embedding + 向量查询（约 100~300ms，可接受）
- 适合：本项目——**用户问的就是作文问题，命中面窄且明确**

### 5.2 结论：B 做默认，A 同时注册

两者不冲突：**B 是注入 prompt，A 是工具调用。**B 提供基础资料，agent 觉得不够可以再调 A 补充。

实施顺序：先做 B（确定性收益，可验证），再注册 A（增益项）。

---

## 6. 注入点：`_build_consultation_prompt`

### 6.1 先补一个零成本的大洞

`_build_consultation_prompt`（`consultation_service.py:678-711`）要求模型"结合评分标准"，但评分标准不在 prompt 里。

**直接把 `load_unified_standard()` 拼进去**——零新依赖、零延迟、当天可验证。这一步的收益**比整个 RAG 加起来还大**，因为评分标准是这个系统里最权威、最常被引用、也最常被模型编造的内容。

**这一步必须先做，而且做完再评估要不要 RAG。**

### 6.2 加了检索之后的 prompt 结构

```python
def _build_consultation_prompt(self, question, history=None, references=None, role='student'):
    history_block = build_history_block(history)
    ref_block = self._render_references(references)   # 空则返回固定话术
    prompt = f"""你是一位专业的初中语文作文辅导老师……

{history_block}
### 参考资料（来自本校教研知识库）
{ref_block}

### 回答要求
1~6 条保持不变。
7. 若参考资料与问题无关，忽略它，不要强行引用。
8. 引用资料时不要编造来源；没有资料支撑时如实说明。
9. 评分标准相关内容必须以上文资料为准，不要凭记忆编造。

问题：{question}

请开始回答："""
```

`_render_references` 的空结果处理：

```python
if not references:
    return '未检索到直接相关的教研资料，请基于通用教学常识回答，并说明这是通用建议。'
```

**这句"如实说明"比任何 prompt 技巧都重要**——它让模型在无资料时降低自信表述，而不是编。

### 6.3 与三条降级路径的关系（重要）

`_generate_ai_response`（`:581-676`）有三条路径：

| 路径 | 历史怎么给 | 参考资料怎么给 |
|---|---|---|
| ① ReactAgent（`execute_stream`） | 走 `history` 参数 → messages 数组 | **必须留在 prompt 里**（没有 messages 通道） |
| ② 直接调模型（完整 prompt） | 渲染进 prompt | 同①，同一份 prompt |
| ③ 简化 prompt | 无 | 无 |

注意**和历史处理的差异**：

- 上一轮做对话记忆时，历史在路径①走 messages 数组，所以**要从 prompt 里剥离**，否则同一段上下文进两遍
- **参考资料正相反**：它没有 messages 通道，路径①②都只能用同一份带资料的 prompt

所以 `prompt_plain`（基础）与 `prompt_with_history`（含记忆）这两个变量的区分逻辑要调整，**改成三个形态**：

```python
prompt_core = self._build_consultation_prompt(question, references=refs)          # 路径①用（历史走 messages）
prompt_full = self._build_consultation_prompt(question, references=refs,
                                              history=history)                    # 路径②用（历史渲染进文本）
prompt_simple = f"作为初中语文老师，请回答问题：{question}"                          # 路径③保持无资料
```

现在代码里是 `prompt_plain` / `prompt_with_history`，加检索后 `prompt_plain` 也要带资料——**命名要改清楚，否则很容易改错**。

---

## 7. 配套必须做的四件事

### 7.1 检索超时与降级

embedding 是网络调用。**必须设超时（3~5s）并失败即降级为空资料**——不能让一次 embedding 超时把整个咨询拖成错误。参考 `config/rag.yaml:21` 已有的 `chat_timeout` 做法，给检索单独配。

### 7.2 缓存检索结果

`utils/cache.py` 里那套 `LRUCache`（目前零调用，见上一轮分析）正好用在这里：`MD5(normalized_query + role)` → 片段列表，TTL 建议 30 分钟。

学生连问三次"怎么开头"是常态；`_get_knowledge_response` 的关键词匹配也是在做同一件事。语料是静态文件，检索结果在 TTL 内天然幂等。

### 7.3 命中率可观测

**必须记录**：`query / role / 命中条数 / 最高分 / 是否注入 / 耗时`。

没有这个数据，你无法判断知识库该补什么。**这是知识库迭代的唯一依据**——也是区分"检索没做好"和"库里根本没这条"的唯一办法。

建议直接落 JSONL 到 `logs/`，而不是只写 logger——需要能统计。

### 7.4 角色分叉要一路透传

`answer_consultation(message, history)` 现在没有 role 参数（`api.py:1423` 调用处）。要做学生/老师分叉，得从 `/chat` 路由一路传下来。

**先确认前端有没有角色概念**——如果没有，`audience` 字段会变成和上一轮 `memory_profile.student` 同类的"填不满的空列"。**这个前提要在写建库脚本之前定下来。**

---

## 8. 顺手要修的三个 bug（都在 RAG 相关代码里）

### 8.1 `filter_relevant_docs` 的相关性判断完全无效

`rag_service.py:355-356`：

```python
query_words = set(query[:500].replace('，', '').replace('。', '').replace('\n', '')[:100])
doc_words = set(content[:500].replace('，', '').replace('。', '').replace('\n', '')[:100])
overlap = len(query_words & doc_words)
```

**这是字符集合，不是词集合。**中文没分词，`set("议论文怎么写")` = `{'议', '论', '文', '怎', '么', '写'}` —— 字符级重叠在任何两段中文之间都大量存在，这个判据**等于没判**。

更糟的是 `:360`：

```python
if overlap == 0 and not has_essay_keyword:
    continue
```

`has_essay_keyword` 在前面 `:349-351` 已经被 `continue` 过为 False 的文档——所以 `not has_essay_keyword` 到这里**恒为 True**，整个条件退化成 `if overlap == 0`，而 overlap 又几乎不为 0。**这个检查是死条件。**

→ **换成向量相似度分数阈值**，别用字符重叠。

### 8.2 `filter_relevant_docs` 会误杀正常内容

`rag_service.py:344`：

```python
if any(keyword in content for keyword in ['prompt', 'template', '系统提示', '指令', '请你']):
    continue
```

`'请你'` 这个词——教研资料里"请你分析下面的病句""请你看这段描写"这类**例句和练习题会被整条丢掉**。

→ 黑名单应收紧到真正的提示词模板特征，例如检测占位符 `'{essay_content}'`、`'{scoring_criteria}'`，而不是日常用语。

### 8.3 `load_document()` 的 md5 去重不覆盖"内容改了"

`vector_store.py:74-76` 只判断 md5 是否**出现过**，出现过就跳过。如果某份材料更新了（新 md5 没出现过），会**新增一批 chunk 而不删除旧的**——库里同一份文件有两代内容，检索时随机命中旧版。

→ 建库时按 `source` 字段先删后加（`vector_store.delete(where={"source": path})`）。

---

## 9. 落地顺序

| 阶段 | 内容 | 依赖 | 验证方式 |
|---|---|---|---|
| **P0** | 把 `load_unified_standard()` 拼进 `_build_consultation_prompt` | 无 | 问"评分标准怎么给分"，看回答是否引用了真实标准 |
| **P0** | 修 §8 的三个 bug | 无 | — |
| **P0** | 摘掉 `rag_summarize` 的咨询工具注册（`react_agent.py:93`） | 无 | 问"议论文论点怎么写"不再返回批改 JSON |
| **P1** | 建 `data/knowledge/` 语料 + `rag/knowledge_loader.py` 建库 | 语料准备 | collection 条数 > 0 |
| **P1** | `rag/knowledge_retriever.py` + 阈值 + 缓存 | P1 建库 | 离线跑 20 个真实问题，看命中率与分数分布 |
| **P1** | 注入 `_build_consultation_prompt` | 上两步 | 回答中出现"资料1"来源标注 |
| **P2** | `search_knowledge` 工具注册（方案 A） | P1 | agent 能自主补充检索 |
| **P2** | `audience` 角色分叉 | 需先定角色前提 | — |
| **P2** | 命中率看板 | P1 | — |

### 关于 `rag_summarize` 摘除的说明

P0 摘掉咨询里的注册后，**批改链路不受影响**——批改走的是 `review_grader`，不是这个工具（`services/review_grader.py` 里 `load_unified_standard()` 独立调用）。

摘掉后 agent 就只剩 `get_user_id` 一个工具了，而它返回的是 `random.choice` 的**假 ID**（`agent_tools.py:22-24`）。**要么把 `search_knowledge` 补上让它有真实工具可用，要么这个 agent 退化成纯对话模型**——后者其实也完全够用（咨询本质就是知识问答，不需要 ReAct）。

---

## 10. 规模临界点：什么时候 RAG 是负收益

这一点必须说清楚，因为它决定了上面这套要不要做。

**语料规模 < 1 万字（约 20~30 条方法讲解）时，全量塞进 prompt 比 RAG 更准、更快、更可控：**

| | 全量塞 prompt | 向量检索 |
|---|---|---|
| 准确率 | 100%（不存在漏检） | 有漏检，取决于切片和阈值 |
| 延迟 | 0 | 每次 +100~300ms（含 embedding） |
| 调参 | 无 | chunk_size / overlap / k / threshold 四个参数 |
| 可控性 | 完全 | 检索失败、切片截断、阈值误杀 |

**RAG 的价值随语料规模增长。**在 1 万字以下，它是负收益。

而 `qwen3.8-max` 的上下文窗口接住 1 万字毫无压力，成本约 1.5 万 token/次——咨询是低频操作，这个成本可接受。

### 所以建议的顺序是

1. **先做 §6.1**：把评分标准拼进 prompt（零依赖、当天见效）
2. **语料从 `_essay_knowledge` 迁移到 `data/knowledge/*.md`**（解耦"改知识要改代码"这个真问题）——但此时仍**全量塞 prompt**
3. **语料过 1 万字（或需要按 `audience` 分叉导致全量塞不下）时**，再把上文这套检索层接上

**第 2 步是可选的优化，第 3 步才是 RAG 真正的触发点。**

判断信号很明确：当"全量塞 prompt"开始导致 token 成本或延迟不可接受，或者你发现模型在一大堆资料里**找不准该引用哪条**（长上下文注意力涣散）时，RAG 就从负收益翻正了。

---

## 附：涉及文件清单

**新增**
- `rag/knowledge_loader.py` — 建库
- `rag/knowledge_retriever.py` — 检索层
- `data/knowledge/**` — 咨询语料
- `config/chroma.yaml` 新增 `consult:` 节点

**修改**
- `services/consultation_service.py` — `_build_consultation_prompt` 注入资料；`_generate_ai_response` 三形态 prompt；`answer_question` 透传 role
- `agent/tools/react_agent.py:93` — 工具列表调整
- `agent/tools/agent_tools.py` — 新增 `search_knowledge`，摘除咨询侧的 `rag_summarize`
- `rag/rag_service.py:344,355-360,419-423` — 修 §8 的 bug
- `rag/vector_store.py` — 支持按 source 先删后加
- `api.py` — 启动时后台建库；`/chat` 透传 role
- `utils/cache.py` — 接上检索缓存（该文件目前零调用）

**不动**
- 批改链路（`services/review_grader.py`、`rag_summarize.txt` 模板）
- `utils/standard_loader.py`（模块级缓存 + txt 落盘 + mtime 比对的设计是对的，继续用）
