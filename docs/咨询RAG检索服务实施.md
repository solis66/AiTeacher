# 咨询 RAG 检索服务 · 实施与验证记录

> 日期：2026-09-15
> 上游设计：[`咨询RAG检索服务设计.md`](./咨询RAG检索服务设计.md)
> 结论：**已落地并通过全链路自检**（编译 14 文件 / 语料 4 篇 6182 字 / 案例库 69 片段 / 老师路径多学生隔离 / 并发同步无重复）。

---

## 1. 这次做的是什么

按设计文档的落地顺序把「咨询检索」建了起来，目标有二：

1. **学生侧**：AI 批改过的多篇作文，要能成为该学生后续咨询的依据（"我开头为什么总写不好"→ 答的是他自己的评语）。
2. **老师侧**：老师问某个学生的学情，AI 要能答那个学生的（"李明的学情怎么样"→ 给李明一个人的画像）。

与设计文档的差别：设计文档把范围限定在「教研资料检索」。实际实现时发现**真正值钱的数据是老师/学生自己积攒的批改记录**，所以检索面扩成了三层，详见 §3。

---

## 2. 数据模型：owner 与 student 必须分开

实施前的一个硬前提：原记录只有 `owner`，而 `owner` 是**提交者**（也是数据隔离键，来自 `X-Username`）。

如果只有 `owner`，"老师代学生上传作文"这条最需要学情能力的路径就**无法表达**——李明和王芳的作文都挂在老师账号下，学情必然混在一起。

因此 `services/review_workbench.create()` 增加 `student` 参数：

| 字段 | 含义 | 缺省 |
|---|---|---|
| `owner` | 提交者 / 租户 / **隔离键** | `X-Username` |
| `student` | 作文所属学生 / **学情检索键** | 缺省 = `owner`（学生自传场景） |

```python
# services/review_workbench.py
student = (student or '').strip() or (owner or '').strip() or 'anonymous'
```

**缺省回退为 owner 这一点是有意为之**：它让 `student` 字段引入之前的历史记录自动被正确归类（老师自己＝自己名下的唯一学生），不需要数据迁移。

配套：
- `ReviewIndex.student_of(record)` — 兼容旧记录的回退读取
- `GET /api/review/students` — 返回当前账号名下的学生名，供老师端下拉选择
- `review_workbench.students(owner)` / `record['student']`

---

## 3. 三层检索，三种正确性来源

这是整个实现里最重要的设计决定：**不是所有内容都该走向量检索。**

| 层 | 来源 | 方法 | 为什么不换另一种 |
|---|---|---|---|
| **学情数据** | `reviews.sqlite3` | 确定性聚合（直接算） | 数字**必须来自计算**。向量检索算平均分一定出错，而"模型算错了平均分"是不可接受的错误 |
| **批改案例** | 已入库的评语片段 | 语义检索 | 跨篇问句（"开头为什么总写不好"）与单篇评语之间**没有共同关键词**，只有向量能召回 |
| **教研资料** | `data/knowledge/*.md` | 小语料全文注入 / 大语料检索 | 见 §4 |

### 3.1 索引粒度：一篇作文拆成四类片段

`rag/review_index.py:build_documents()`

| kind | 内容 | 服务的问题 |
|---|---|---|
| `summary` | 得分 + 各维度 + 总体评价 + 亮点 + 建议（一篇一条） | "我整体怎么样""这个学生学情如何" |
| `analysis` | 内容/结构/语言/技巧/情感，每个方面一条 | "我结构上有什么问题" |
| `issue` | 每条改进建议、每条原文纠正各一条 | "我开头为什么总写不好" |
| `strength` | 每条亮点一条 | "我哪里写得好" |

**粒度太粗时检索等于没有**：整篇评语存一条，向量会被"分数、结构、语言"等信息稀释，问"开头怎么写"命中率极低。

每条片段带 metadata：`owner / student / review_id / grade / essay_type / title / score / rating / created_at / kind`。

### 3.2 学情聚合的四个防误导约束

`student_profile()` 里每个阈值都对应一次实测踩坑：

| 约束 | 值 | 不加会怎样 |
|---|---|---|
| `MIN_DIM_SAMPLES` | 2 | 某维度只出现 1 篇时被列为"你最薄弱的维度"——不同体裁同名维度满分都不一样，没有可比性 |
| `MIN_TREND_SAMPLES` | 5 | 4 篇混合体裁的作文算出"下降 14 分"——这是误导，不是洞察 |
| 按**篇**计数而非按条计数 | — | "3 条建议提到开头"≠"3 篇作文有问题"，改成"2 篇提到" |
| 趋势样本不足时显式说明 | — | 实测输出：`成绩趋势：目前仅2篇，少于5篇，不足以判断成绩趋势` |

---

## 4. 语料规模决定策略（不是一个参数）

`rag/knowledge_loader.py`

```
语料总字数 <= full_inject_limit(12000) → 全文注入 prompt
语料总字数 >  12000                    → 向量检索 + 阈值过滤
```

理由（设计文档 §10 的推导，这里是落地）：小语料下向量检索是**负收益**——有漏检、有 embedding 延迟、要调 4 个参数，而全量注入零漏检、零延迟、完全可控。

当前语料 4 篇 / **6182 字**，走全文注入。`consult_knowledge` collection 仍照建（23 片段），这样语料一过线，切换只是配置判定自动发生，不需要改代码。

一个例外：**学情类提问强制走检索**（`get_context(force_retrieval=True)`）。问"李明的学情"时，写作方法论与问题无关，塞全文纯属干扰。

---

## 5. 范围解析：宁可判"不注入"，也不猜一个人

`services/consult_context.py:resolve_scope()` — 优先级从高到低：

| # | 条件 | 结果 |
|---|---|---|
| 1 | 前端显式指定学生（下拉） | `student`（`owner_scoped=True`） |
| 2 | 提问中出现已知学生名（取最长匹配，≥2 字） | `student` |
| 3 | `role='teacher'` 但未指明学生 | `none` |
| 4 | `role='auto'` 且账号下有多名学生 | `none`（疑似教师账号，不能把"我"当学生） |
| 5 | 出现自指词或作文话题词 | `self` |
| 6 | 其他 | `none` |

**第 4 条是从数据反推身份**：一个学生账号下只会有一个学生名，出现多个就是教师账号。这比让前端把角色传对更可靠——`X-Username` 本来就不是认证手段，角色只能当提示级意图声明，真正的隔离靠 `owner` 过滤。

---

## 6. 阈值是标定出来的，不是拍的

`config/chroma.yaml:consult.score_threshold = 0.20`

实测分布（`qwen3.7-text-embedding` + chroma 默认距离）：

| 问句 | 最高分 | 应否保留 |
|---|---|---|
| 今天天气怎么样 | 0.147 | ❌ 过滤 |
| 结构问题 | 0.256 | ✅ 保留 |
| 错别字和标点 | 0.567 | ✅ 保留 |

0.20 落在"无关 / 相关"之间。**该阈值与 embedding 模型的距离尺度绑定，换模型必须重新标定**——这句话写在配置注释里了。

> 咨询与批改最重要的行为差别在这里：**批改不能拒答**（必须给分），**咨询必须能拒答**。低分片段塞给模型会诱导它强行引用，产生幻觉且表述更自信。

---

## 7. 性能：增量同步 + 紧凑指标侧车

前提是用户明确说的"作文会越来越多"。

1. **增量依据是 `reviews.version`**。任何写入（批改完成 / 人工保存 / 重启标记失败）都会推进它，所以 version 变化 = 内容变化。
2. **无变化时只做一次 `SELECT id, version`**，不解析 payload、不加载指标文件、不构造向量库客户端。因此可以在**每次咨询前**无负担调用。
3. **变化的记录按 `review_id` 先删后加**——否则同一篇作文的新旧两版评语同时在库里，检索随机命中旧版。
4. **指标侧车 `consult_metrics.json`**：原始 payload 含分页全文、批注坐标，单条可达数十 KB，而学情聚合只需要几百字节。抽出来存侧车，避免重复解析。

若每次咨询都解析全部 payload，500 篇时单次就是秒级——那次咨询的响应时间不可接受。

---

## 8. 注入点：三种 prompt 形态

`consultation_service._generate_ai_response()` 有三条路径，参考资料与历史的处理**方向相反**：

| 变量 | 用于 | 历史 | 参考资料 |
|---|---|---|---|
| `prompt_core` | ① Agent 主路径 | 走 messages 数组，**从 prompt 剥离** | **必须留在 prompt**（没有 messages 通道） |
| `prompt_full` | ② 降级：直接调模型 | 渲染进 prompt | 留在 prompt |
| `prompt_simple` | ③ 最后兜底 | 无 | 无 |

历史要剥离、资料要保留——**这个不对称是最容易改错的地方**，所以变量名从 `prompt_plain` / `prompt_with_history` 改成了三个语义清晰的名字。

注入块的三个小节，每节都写明用途与"没有内容时怎么写"：

```
### 学情数据（系统直接统计，非模型推断，引用时必须与此一致）
### 该学生历史批改片段（按本次提问检索，共N条）
### 教研参考资料
### 资料完整性提示        ← 无内容时在这里如实说明
```

空结果固定话术：

> 未检索到直接相关的教研资料，请基于通用教学常识回答，并说明这是通用建议。

**这句"如实说明"比任何 prompt 技巧都重要**——它让模型在无资料时降低表述确定性，而不是编造出处。

---

## 9. 实测验证结果

自检脚本全部跑通（脚本已删）。

### 9.1 编译与语料

```
14 个文件 py_compile 通过
knowledge_stats: files=4, chars=6182, mode=full
```

### 9.2 索引状态与集合隔离

```
collections            : agent(0) / consult_knowledge(23) / review_cases(69)
review_index_state.json: 4 条记录，version 与 reviews 表一致
```

### 9.3 老师路径端到端（隔离环境，不动真实数据）

> 方法：拷贝 reviews 库到临时目录，集合改用 `review_cases_selftest`，把隔离实例注入 `consult_context._index`，从而走**真实**的 `build_context` 全链路；跑完 drop 集合、删临时目录。

合成数据：`owner=teacher_li`，`student=李明` 2 篇、`student=王芳` 1 篇。

| 提问 | scope | student | 命中片段 | 学生正确 | 串到别人 |
|---|---|---|---|---|---|
| 李明开头总是写不好，怎么辅导？ | student | 李明 | 6 | ✅ | ❌ |
| 王芳的作文水平如何？ | student | 王芳 | 3 | ✅ | ❌ |
| admin 的作文情况怎么样？ | student | admin | 0 | ✅ | ❌ |
| 这个学生该怎么辅导 | none | — | 0 | ✅ | — |

第 3 行是**隔离性证明**：`admin` 的记录挂在 `owner='admin'` 下，老师账号 `teacher_li` 查不到，且如实提示"admin 名下暂无已完成的批改记录"，没有硬编内容。

`students('teacher_li')` → `['李明', '王芳']`（不含 admin）✅

### 9.4 实际注入的学情数据（人眼核对）

```
学生：李明
已完成批改：2篇（2026-09-01 至 2026-09-01）
平均分：40.0/50（最高42，最低38，最近一次42）        ← (38+42)/2 = 40 ✓
成绩趋势：目前仅2篇，少于5篇，不足以判断成绩趋势      ← 不给误导性数字 ✓
各维度得分率（由低到高）：结构 得分率80%（2篇）；内容 得分率90%（2篇）
        ← 结构 24/30 = 80% ✓  内容 36/40 = 90% ✓
最薄弱维度：结构（得分率80%，2篇）                   ← 取真实最低 ✓
反复出现的问题：开头（2篇提到）；描写细节（2篇提到）   ← 按"篇"计数 ✓
相对稳定的优点：描写细节（2篇）
最近几篇：2026-09-01《雨中的伞》38分良好；2026-09-01《那盏灯》42分良好
```

### 9.5 并发同步安全性

**这是本次验证抓到并修掉的一个真实缺陷。**

6 个线程在一条记录 version 变化后同时 `sync()`：

| | 结果 |
|---|---|
| 加锁前（预期） | 6 个线程各自 delete + add，7×6 = 42 片段 → 同一篇作文的分片重复入库 |
| **加锁后（实测）** | `added_per_thread = [7, 0, 0, 0, 0, 0]`，**总 7 = 该记录应有的片段数，无重复** |

修复：`rag/review_index.py` 增加模块级 `_SYNC_LOCK`，`sync()` 与 `remove()` 整体串行化。它同时是那对 `state` / `metrics` 侧车文件（读-改-写、无事务）的写锁——否则并发写互相覆盖，已索引的记录会被误判为"没索引过"而重复建库。代价可忽略（同步本身毫秒级，只有真有变化时才调 embedding）。

`rag/knowledge_loader.py:ensure_index()` 有同样的问题，用 `_ENSURE_LOCK` 同样处理。

### 9.6 前端

```
vite v4.5.14  building for production...
1816 modules transformed.
dist/index.html                 0.45 kB │ gzip:  0.33 kB
dist/assets/index-191f5a95.css 40.08 kB │ gzip:  7.50 kB
dist/assets/index-489bdff7.js 189.84 kB │ gzip: 68.82 kB
built in 2.83s   EXIT=0
```

---

## 10. 与设计文档的偏离（都有理由）

| 设计文档 | 实际实现 | 原因 |
|---|---|---|
| 新建 `rag/knowledge_retriever.py` 作为独立检索层 | 检索并入 `rag/knowledge_loader.py` | 建库与检索共用同一 collection 实例、同一 md5 状态、同一语料缓存。拆两个文件后两边都要初始化 Chroma 和读状态文件，反而产生"两处各自判断语料规模"的不一致风险 |
| metadata 加 `audience` 字段做角色分叉 | **未采用**，改用 owner/student 范围解析 | 实现时发现角色的真正用途不是"给学生看的材料 vs 给老师看的材料"，而是"这条提问落在谁身上"。`audience` 会变成一个填不满的空列（设计文档 §7.4 自己也警告过这一点） |
| §7.2 用 `utils/cache.py` 的 LRUCache 缓存检索结果 | 用进程内缓存（语料按文件签名失效、指标缓存） | 语料是静态文件，进程内按 mtime 签名失效已经等价；LRU+TTL 只是多一层过期语义。检索层没有加缓存是因为**当前走全文注入，根本没有检索调用可缓存** |
| 阈值建议 0.35 起步 | 标定为 0.20 | 0.35 会误杀真实命中（实测"结构问题"类相关问句最高 0.256） |
| `rag_service.filter_relevant_docs` 改用分数阈值 | 直接删掉字符重叠启发式，只保留长度/模板占位符/去重过滤 | 该函数在 agent 链路上已不可达，保留分数逻辑等于维护死代码 |

另外修掉的两处不一致：
- `knowledge_loader.DEFAULT_THRESHOLD` 兜底值原为 `0.35`，与 `review_index` 的 `0.20` 不一致 → 统一为 `0.20`。配置项缺失时两个模块会按不同阈值过滤，同一句问句在"教研资料"与"批改案例"上的召回标准悄悄分叉且无任何报错。
- `agent_tools.get_user_id()` 返回 `random.choice` 的**假 ID**，已删除（设计文档 §9 也点到了）。

---

## 11. 已知限制

1. **指标缓存不跨进程失效**。`ReviewIndex._metrics_cache` 是进程内的，`sync()` 的快速路径靠 `state` 与 `alive` 的差异兜住"记录被改/被删"，所以**进程内一致**。但如果外部进程直接改了 `reviews.sqlite3`，正在运行的服务会拿旧缓存，需重启。生产路径（都走 API）不受影响。
2. **`agent` collection 仍是空的**。批改标准现在由 `utils/standard_loader.py` **全文注入**（`review_grader` 与 `review_service` 都走它），向量路径只剩 `api.py` 的旧批改入口。该 collection 属于历史遗留，未清理也未使用——留着不影响功能，但要知道它是空转的。
3. **`student` 依赖前端配合**。老师端目前没有"选择学生"的 UI 入口，`student` 字段依赖老师在上传时填写。前端不填时，`student` 缺省为 `owner`，行为等同于"老师自己是一名学生"，学情检索会静默退化为按老师账号聚合——**不报错但结果无意义**。这是下一步最该补的一环。
4. **多篇作文的体裁差异未归一化**。趋势判断已在样本 < 5 篇时明确说明"不足以判断"，但样本足够时不同体裁（记叙文/说明文维度满分不同）的分数仍直接比较。当前数据量下不构成问题。

---

## 12. 涉及文件

**新增**

| 文件 | 职责 |
|---|---|
| `rag/knowledge_loader.py` | 教研语料：加载、按规模选策略、建库、检索 |
| `rag/review_index.py` | 批改案例：建索引、语义检索、确定性学情聚合 |
| `services/consult_context.py` | 范围解析 + 三层上下文装配 + 命中率日志 |
| `data/knowledge/01_写作方法.md` | 教研语料 |
| `data/knowledge/02_体裁指导.md` | 教研语料 |
| `data/knowledge/03_评分解读.md` | 教研语料 |
| `data/knowledge/04_常见问题.md` | 教研语料 |

**修改**

| 文件 | 改动 |
|---|---|
| `config/chroma.yaml` | 新增 `consult:` 节点（独立 collection / 切片参数 / 阈值与标定注释） |
| `config/rag.yaml` | `embedding_timeout`、`embedding_max_retries` |
| `model/factory.py` | `OpenAIEmbeddings` 支持 `request_timeout` / `max_retries` |
| `services/review_workbench.py` | `create(student=)`、`student_of()`、`students()` |
| `routes/review.py` | 表单读 `student`、摘要返回 `student`、新增 `GET /api/review/students` |
| `services/consultation_service.py` | `_generate_ai_response` 三形态 prompt、智能体/老师双 persona、10 条回答约束 |
| `services/consult_context.py` | `initialize()` 后台预热 |
| `api.py` | 启动时后台预热索引；`/chat` 透传 `role` / `student` |
| `rag/vector_store.py` | `search_with_scores()`；`load_document()` 按 source 先删后加 |
| `rag/rag_service.py` | 删除无效的字符重叠相关性过滤 |
| `agent/tools/agent_tools.py` | 新增 `search_knowledge`；删除假 ID 工具 |
| `agent/tools/react_agent.py` | 工具列表改为 `[search_knowledge]` |
| `prompts/main_prompt.txt` | 说明如何使用注入的学情/片段/资料与硬约束 |
| `utils/file_handler.py` | `listdir_with_allowed_type` 改 `os.walk` 递归 |

**未动**：批改链路（`services/review_grader.py`）、`utils/standard_loader.py`、`prompts/rag_summarize.txt`。
