# 咨询 Agent 批改记录工具设计（search_reviews / review_detail）

日期：2026-10-24
状态：待批准

## 1. 意图与动机

学生问「我那篇《春天》为什么只有 38 分」时，咨询链路目前只能依靠自动注入的
最多 6 条批改片段来回答——片段是扁平的评语文本，缺篇目语境，也拿不到五维得分
与原文对应关系，回答只能泛泛而谈。

本次给咨询 Agent 增加两个按需查询工具，让学生能追问到「某一篇」的细节；
同时把无条件注入的片段数从 6 降到 3，把 token 成本从「每轮必付」改为
「真正需要时才付」。

## 2. 目标 / 非目标 / 反目标

**目标**
- 新增 `search_reviews`：按体裁、分数区间、时间范围、关键词检索**当前账号**的批改记录。
- 新增 `review_detail`：按记录 id 查看单篇的裁剪版批改详情。
- 数据范围由运行时上下文提供 owner，模型入参里没有账号字段。
- 自动注入的案例片段从 6 条降为 3 条。

**非目标**
- 不做跨账号查询（管理员看他人记录仍走「用户管理」独立接口）。
- 不引入语义检索（不调用 embedding、不依赖 0.20 阈值）。
- 不改前端、不改批改流水线。

**反目标**（技术上能跑也算失败）
- 模型可以通过参数指定他人账号——机制上杜绝，不靠提示词约束。
- 单次 `review_detail` 返回超过约 1500 字，把上下文撑爆。
- 工具调用把预算用光，导致模型无法收尾作答。

## 3. 约束

- 数据访问只复用现有 `ReviewStore`：`list(owner)`（按 rowid 倒序、上限 200 条）与 `get(id, owner)`；
  不新增 SQL、不改表结构。
- 工具必须声明 `runtime: ToolRuntime[AgentContext]`；`AgentContext.owner` 由
  `create_agent(context_schema=...)` + `stream/invoke(context={'owner': ...})` 注入
  （已用真实模型实测：`context={'owner':'admin'}` → 工具读到 `owner=admin`）。
- `agent_max_tool_calls` 由 2 提升为 3；`agent_recursion_limit` 保持 20。
- 记录状态非 `done`（queued/recognizing/grading/failed）时，详情工具返回说明而非内容。

## 4. 方案（已选 A）

| 方案 | 做法 | 取舍 |
|---|---|---|
| **A（选中）** | 读该账号记录，在内存里按结构化条件过滤 | 零 embedding、毫秒级、结果可解释；不支持纯语义模糊描述 |
| B | 转调 `review_index.search`，片段聚合为篇 | 能应对模糊描述；但片段≠篇、多一次 embedding、阈值刚换模型未重标定 |
| C | A 过筛，0 条时再走 B | 兼顾两者；两条失败模式不同，提示词与排查更复杂 |

选 A 的理由：每账号记录上限 200 条，结构化过滤已覆盖「哪篇最差」「上次写春天的」
「议论文都多少分」这类真实问法；语义模糊需求由自动注入的 3 条片段兜底。
B/C 的收益不足以抵消新增的不确定性。

## 5. 我替你做的决定（可在批准时推翻）

1. **模块位置**：`backend/agent/tools/review_tools.py`，与 `agent_tools.py`（知识库检索）分开，
   避免把「批改数据访问」混进「知识检索」。
2. **`AgentContext`** 定义在同一模块（`owner: str`），`ReactAgent` 创建 agent 时传
   `context_schema=AgentContext`，三处 `stream/invoke` 调用都带 `context={'owner': owner}`。
3. **`search_reviews` 入参**：`query`（关键词，可空）、`essay_type`（可空）、`min_score`、
   `max_score`（0 表示不限）、`days`（0 表示不限）、`limit`（默认 5，上限 8）。
4. **排序规则**：有关键词时按命中次数降序、再按时间倒序；无关键词时纯时间倒序。
5. **`review_detail` 返回字段**：题目、体裁、日期、总分、等级、五维得分、
   总评、改进建议、亮点、原文纠正、原文前 400 字；**不含** `pages`、`ai_result`、
   `marks`、附件路径。整体截断到约 1500 字并注明「已截断」。
6. **工具输出形态**：纯文本摘录（键值行 + 列表），不是 JSON——模型读文本更稳。
7. **提示词**：在 `main_prompt.txt` 增补「何时调 search_reviews / 何时调 review_detail」，
   并写明「工具只能查提问者本人，不要试图查询他人」。
8. **自动注入**：`config/chroma.yaml` 的 `consult.k_cases` 由 6 改为 3。

## 6. 留给构建者的部分

- 详情字段的具体排版与截断实现。
- 关键词匹配的归一化（去空白、英文小写）。
- 工具返回文案的措辞。

## 7. 验证要点

- `review_detail` 输出不含 `pages` / `marks` / 图片路径，长度不超上限。
- 跨账号：owner=A 指定 B 的记录 id → 返回「未找到该记录」。
- 无参数调用 `search_reviews` → 返回最近记录。
- 工具上限 3：搜一次 + 看一次详情后仍有预算收尾。
- 自动注入 3 条：`build_context` 的 `n_cases` 从 6 降为 3。
