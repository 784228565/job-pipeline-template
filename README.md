# job-pipeline-template

> 一套可复刻的求职自动化管道模板：5 个定时 LLM Agent 串联「搜索 → 筛选 → 预检 → 投递 → 通知」全链路，通过**文件契约**解耦，个人事实全部参数化，新用户跑一个引导脚本即可接入。

## 这个项目解决什么问题

求职投递是高频、规则明确、跨平台重复的劳动。本模板把整个过程拆成 5 个职责单一、可独立演进的 Agent 阶段，每个阶段是调度器（WorkBuddy 等）里的一条定时 prompt，阶段之间**只通过文件通信**——因此你可以单独替换任一环节（换搜索源、换评分模型、换通知渠道）而不影响其他环节。

与"一个超大 prompt 包办一切"的做法相比，本模板的核心设计决策：

| 决策 | 动机 | 落地位置 |
|---|---|---|
| **文件契约解耦** | 阶段失败模式完全不同（搜索=网络/反爬，筛选=数据质量，投递=登录态），独立演进、独立重试 | 各环节只读写约定的文件，见下节 |
| **语义归一化外置** | 中英技能词表、学历序数、字段映射若内嵌在 prompt 里，无法测试、静默漂移、prompt 一改就坏 | `contracts/taxonomy.json` / `field_map.json` |
| **候选人画像 IR 化** | 画像若复制在 prompt 正文，简历更新后 prompt 内的副本不会失效（本项目原型的真实事故） | `contracts/candidate_profile.json` + SHA256 新鲜度锚点 |
| **prompt 参数化** | 个人姓名/邮箱/路径硬编码会让复刻者改几十处，且登录检测正则漏改会造成"误判掉登录" | `{{TOKEN}}` 占位符 + `setup/apply_tokens.py` |

## 架构

```
                ┌─────────────── contracts/（共享词表与画像，唯一事实源）───────────────┐
                │  taxonomy.json        field_map.json        candidate_profile.json     │
                └──────────┬───────────────────────┬────────────────────┬───────────────┘
                           │ 列名归一化/词表          │ URL标准化            │ 画像+hash校验
 06:00  ┌──────────┐   ┌───▼────┐   ┌───────────┐   ┌──▼─────────┐   ┌───┴────────┐   ┌──────────┐
───────▶│ 1 搜索    │──▶│ 岗位池 │──▶│ 2 筛选     │──▶│ 当日投递   │──▶│ 3 预检    │──▶│ 4 投递    │──▶ ...
        │ (Web)    │   │ xlsx   │   │ 去重/闸门  │   │ 队列 xlsx  │   │ (CDP只读) │   │ (CDP写)  │
        └──────────┘   └────────┘   │ 评分排序   │   └────────────┘   └─────┬──────┘   └────┬─────┘
                                    └───────────┘                          │ 登录态契约     │ 状态CSV
                                                              12:30 ┌───────▼──────┐        │
                                                                    │ login_status │        │
                                                                    │    .json     │        │
                                                                    └──────────────┘        │
 15:00  ┌──────────┐                                                                        │
 ...───▶│ 5 通知   │◀────────────────────────────────────────────────────────────────────────┘
        │ (邮件)   │   消费 applicable_today.csv + delivery_status.csv + delivery_log.csv
        └──────────┘
```

### 环节间数据契约

| 生产者 → 消费者 | 契约文件 | 关键约束 |
|---|---|---|
| 搜索 → 筛选 | `搜索agent/YYYYMMDD_HHMMSS.xlsx` | 表头固定为 field_map 规范列名；多 sheet，元数据 sheet 跳过 |
| 筛选 → 投递 | `筛选agent/队列YYYY-MM-DD.xlsx` | 4 个 sheet（队列/剔除说明/统计摘要/行动建议）；当日唯一主文件，历史归档 |
| 筛选内部 | `delivery_log.csv` 回读 | 只认 `result` 非空的行；URL 标准化与去重同一套函数 |
| 预检 → 投递 | `投递状态记录/platform_login_status.json` | `version:1` + `checked_at` 当天时效 + **读写职责隔离** + 过期/缺失时投递端降级为自行探测 |
| 投递 → 全局 | `delivery_status.csv` / `delivery_log.csv` | 唯一真源，每次状态变更立即写回 |
| 筛选自身 | `contracts/candidate_profile.json` | 简历 SHA256 == `resume_source.sha256` 才直接用，否则从 PDF 重建 |

### 筛选环节的闸门与评分（环节 2 内部逻辑）

```
原始岗位 → [去重] → [已投递排除] → [闸门4.1 硬性匹配] → [闸门4.2 时效≤30天]
        → [闸门4.3 竞争度] → [闸门4.4 链接有效性] → [五维评分0-100] → 排序入队
```

- 硬闸门（学历/技能交集/经验年限/届次/签证地点）**先于**评分，剔除必进"剔除说明" sheet，禁止静默丢弃；
- 增量模式（当日队列已存在）只对新输入文件跑闸门，已有岗位只重算时效分，不踢出队列；
- 经验门槛自动适配：`exclude_experience_years_min = 本人年限 + 1`。

## 目录结构

```
├── docs/
│   └── prompts_template.md        # 5 段 prompt 全文（占位符化）+ 数据流契约 + 附A替换表/附B接入契约/附C脱敏清单
├── contracts/
│   ├── taxonomy.json              # 技能同义词(17组)/学历序数/职级阶梯/地点归一化/大厂名单
│   ├── field_map.json             # 输入 Excel 列名归一化 + URL 标准化规则（单一来源）
│   ├── candidate_profile.example.json  # 虚构示例画像（schema 见 docs 附B）
│   └── local_tokens.example.json       # 虚构示例替换表
├── setup/
│   ├── onboard.py                 # 引导式接入向导（交互 or --answers），生成画像+token并立即校验
│   ├── validate_profile.py        # 画像契约校验器（CI 可用 --no-file-check 跳过文件校验）
│   └── apply_tokens.py            # 模板 + local_tokens.json → build/prompts_personalized.md
├── tests/
│   ├── fixtures/tc1~tc5.json      # 虚构候选人：完整/日本签证/最小档案/非法字段/简历hash过期
│   ├── assets/dummy_resume.pdf    # 测试用占位 PDF
│   └── run_tests.py               # 端到端：onboard.collect → validate，断言通过/拒绝
├── .gitignore                     # 排除真实画像/token/简历/运行时产物
└── README.md
```

## 快速开始

前置：Python 3.8+；调度器（WorkBuddy / cron + 任意 agent 框架）；投递与预检环节需要本机 Chrome 以 CDP 9222 端口启动、目标平台已登录。

```bash
git clone <this-repo> && cd job-pipeline-template

# 1. 接入：回答 16 项必填 + 7 项选填，提供简历 PDF 路径
python setup/onboard.py                 # 或 --answers answers.json 非交互
#    → contracts/candidate_profile.json（画像，含简历 SHA256）
#    → local_tokens.json（11+5 种占位符替换值）
#    生成即按附B契约校验，不通过逐条报错

# 2. 生成个人版 prompt
python setup/apply_tokens.py            # → build/prompts_personalized.md（零残留占位符）

# 3. 部署：把 5 段 prompt 粘贴进调度器，设好 06:00/11:37/12:30/13:00/15:00 五个定时
#    并按 docs 附A 改写 3 处结构性段落（身份约束叙述/方向限定/平台黑名单）

# 4. 验证
python tests/run_tests.py               # 5/5 通过
```

**换简历**：重跑 `onboard.py`，或在筛选 Agent 运行时它会自动发现 hash 不一致并重建画像（TC5 测的就是这个）。

## 关键机制

- **新鲜度锚点**：简历不是"读了就用"——每次运行先 `certutil -hashfile` 比对 SHA256，不一致才重新解析 PDF 并重写画像，避免"PDF 更新了、prompt 里的旧画像还在用"。
- **幂等与防重**：投递地址标准化（去 tracking 参数、统一末尾斜杠、域名小写）是去重和已投递排除的同一套主键；通知邮件以 `notified_<date>.json` 的 rank_list 做幂等防重。
- **降级规则**：预检契约过期/缺失 → 投递端回退自行探测（行为等价于无预检）；筛选读不到 delivery_log → 跳过已投递排除并报告；增量合并读旧队列失败 → 降级全量生成。
- **写入职责隔离**：预检只写 `platform_login_status.json`、投递只读；投递只写 `delivery_*.csv`、通知只读。任何环节不得越界。

## 测试

```bash
python tests/run_tests.py
```

| 用例 | 场景 | 期望 |
|---|---|---|
| tc1 | 完整档案（含选填） | 创建成功 |
| tc2 | 日本签证担保方向 | 创建成功 |
| tc3 | 最小档案（选填全空） | 创建成功 |
| tc4 | 非法字段（学历序数=5、届次缺年份、词表外技能、地点外星球、空 japan_rule 等 8 项） | **拒绝**并逐条列出原因 |
| tc5 | 简历已更换但 hash 未更新 | **拒绝**并报"哈希不匹配" |

## 自定义与扩展

- **加技能词/地点/大厂**：只改 `contracts/taxonomy.json`，prompt 不用动；
- **接新的搜索来源**：来源 Excel 表头变体加进 `contracts/field_map.json` 的 `column_aliases`；
- **换通知渠道**：环节 5 是唯一纯下游消费者，改它的 prompt 即可；
- **新增环节**：遵循现有模式——定义输出契约文件（带 `schema_version`）、在下一环节的 prompt 中声明消费规则与降级行为、在 docs 数据流契约图里补一条边。

## 安全模型

- 真实画像 / token 替换表 / 生成的个人版 prompt / 简历 PDF 全部被 `.gitignore` 排除，仓库只含模板与虚构数据；
- 刻意**不采集**身份证号与详细住址——管道无任何环节消费它们，采集只会扩大泄露面；
- 发布前自检：对仓库 grep 真实邮箱/手机号/身份证/姓名，应为零命中（详见 docs 附C）。

## 已知边界

- 环节 3/4 依赖本机 Chrome CDP 环境（UserData 目录 + 9222 端口 + 各平台已登录），无此环境时这两环不可运行，但 1/2/5 环独立可用；
- 环节 1 的"候选人特殊身份约束"、方向限定、平台黑名单是叙事性规则，无法表单化，复刻者需按 docs 附A 人工改写；
- 评分与闸门判定由 LLM 执行，规则已尽量结构化（序数/词表/枚举），但结论仍具概率性——统计摘要 sheet 用于人工审计每天的剔除决策。
