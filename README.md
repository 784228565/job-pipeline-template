# job-pipeline-template

**把"每天找工作"变成一条自动化流水线**：早上 6 点搜索岗位，中午筛出今天该投的，下午自动投出去，3 点发邮件告诉你结果。你要做的只有一件事——把简历和你的情况告诉它一次。

## 30 秒开始（推荐）

打开 **Kimi Code** 或 **WorkBuddy**，粘贴这一句：

> 帮我读取并执行 https://github.com/784228565/job-pipeline-template/blob/master/docs/agent_bootstrap_prompts.md

然后 agent 会像填表向导一样逐条问你问题，问完自动完成安装、校验和部署清单。**信息采集不齐它不会继续**，不会替你瞎编。

### 开始前请准备好这些（约 10 分钟）

- [ ] 一份简历 PDF 放在电脑上（记住路径）
- [ ] 你的中英文姓名、邮箱、手机号
- [ ] 学历情况（学校/专业/年份/是否毕业）
- [ ] 一句话身份状态（如"2026届应届，未缴过社保"）
- [ ] 会哪些技能（至少 3 个，如 Python、SQL）
- [ ] 想去的行业/城市/公司类型，以及工作年限（应届填 0）
- [ ] 是否考虑海外岗位（考虑的话说明国家/地区与签证需求）

### 运行结束后你会得到

| 产物 | 是什么 |
|---|---|
| `contracts/candidate_profile.json` | 你的候选人画像（本机保存，不会上传） |
| `build/prompts_personalized.md` | 5 段已填好你信息的 prompt，按提示粘进调度器即可 |
| 部署清单 | 每个任务设几点、哪里需要人工确认，agent 会打印给你 |

**部署是否成功以验证器为准**：agent 会运行 `python setup/verify_deployment.py`，它直接读调度器数据库核对 5 个定时任务是否真实存在、时间是否正确——只有输出「定时任务 ✅ 5/5」才算装好。

**以后换了简历**：对 agent 说"我换了简历"或手动重跑 `python setup/onboard.py`，画像会自动重建（系统用 SHA256 检测简历是否变动）。

<details>
<summary>不用 AI agent？点这里看手动安装（4 条命令）</summary>

```bash
git clone <this-repo> && cd job-pipeline-template
python setup/onboard.py            # 回答问卷（13 组必填 + 6 项选填）
python setup/apply_tokens.py       # 生成 build/prompts_personalized.md
python tests/run_tests.py          # 应输出 5/5 通过
python setup/verify_deployment.py  # 建完定时任务后跑：核对 5 个任务存在且时间正确
```

然后把 `build/prompts_personalized.md` 中的 5 段 prompt 分别建为每日定时任务：
06:00 搜索 / 11:37 筛选 / 12:30 预检 / 13:00 投递 / 15:00 通知。

</details>

---

## 它是怎么工作的

### 一天的时间线

```
06:00  搜索 Agent   扫各平台/官网，整理 ~100 个岗位到一个 Excel
11:37  筛选 Agent   去重 → 排除已投过的 → 四道硬闸门 → 按"上岸容易度"评分排序
12:30  预检 Agent   检查各平台登录还在不在（掉登录/验证码/区域封锁），写一份状态契约
13:00  投递 Agent   按契约跳过异常平台，其余用浏览器自动化逐个投递，边投边记状态
15:00  通知 Agent   汇总"没投成的+原因"，发邮件给你，附今日/累计投递数
```

### 为什么这样设计

四个关键决策，每条都踩过坑：

1. **环节之间只通过文件传话，不通过 prompt 传话**。搜索会网络超时、投递会遇验证码、筛选会数据缺失——失败模式完全不同，拆开才能各自重试互不影响。文件即契约，版本化、可审计。
2. **你的信息不进 prompt 正文，进一份画像文件**。早期版本把简历画像复制在 prompt 里，结果换了简历 prompt 里的旧版本还在被用——匹配全靠过期信息。现在画像存在 `contracts/candidate_profile.json`，每次运行先校验简历哈希，变了才重建。
3. **"能不能投"和"值不值得投"分开**。硬性门槛（学历/经验/签证/届次）走闸门，剔除必须写明原因；通过的才打分排序。避免"分很高但根本不符合条件"的推荐。
4. **个人事实全部是占位符**。姓名、邮箱、登录检测正则、路径都是 `{{TOKEN}}`，由 `apply_tokens.py` 统一注入——复刻者不用在几十个文件里找替。

### 目录速览

| 路径 | 干什么 |
|---|---|
| `docs/agent_bootstrap_prompts.md` | 给 AI agent 的引导 prompt（你 30 秒开始用的就是它） |
| `docs/prompts_template.md` | 5 段管道 prompt 全文 + 契约附录（替换表/接入契约/脱敏清单） |
| `contracts/` | 词表 `taxonomy.json`、字段映射 `field_map.json`、示例画像 |
| `setup/` | `onboard.py` 接入向导 / `validate_profile.py` 画像校验 / `apply_tokens.py` 占位符替换 / `verify_deployment.py` 部署验证 |
| `tests/` | 5 个虚构候选人测试（含 2 个"应该被拒绝"的反面用例） |

---

## 深入阅读（开发者向）

### 环节间数据契约

| 生产者 → 消费者 | 契约文件 | 关键约束 |
|---|---|---|
| 搜索 → 筛选 | `搜索agent/YYYYMMDD_HHMMSS.xlsx` | 表头固定为 field_map 规范列名；多 sheet，元数据 sheet 跳过 |
| 筛选 → 投递 | `筛选agent/队列YYYY-MM-DD.xlsx` | 4 个 sheet（队列/剔除说明/统计摘要/行动建议）；当日唯一主文件，历史归档 |
| 筛选内部 | `delivery_log.csv` 回读 | 只认 `result` 非空的行；URL 标准化与去重同一套函数 |
| 预检 → 投递 | `投递状态记录/platform_login_status.json` | `version:1` + `checked_at` 当天时效 + **读写职责隔离** + 过期/缺失时投递端降级为自行探测 |
| 投递 → 全局 | `delivery_status.csv` / `delivery_log.csv` | 唯一真源，每次状态变更立即写回 |
| 筛选自身 | `contracts/candidate_profile.json` | 简历 SHA256 == `resume_source.sha256` 才直接用，否则从 PDF 重建 |

### 筛选环节的闸门与评分

```
原始岗位 → [去重] → [已投递排除] → [闸门4.1 硬性匹配] → [闸门4.2 时效≤30天]
        → [闸门4.3 竞争度] → [闸门4.4 链接有效性] → [五维评分0-100] → 排序入队
```

- 硬闸门（学历/技能交集/经验年限/届次/签证地点）**先于**评分，剔除必进"剔除说明" sheet，禁止静默丢弃；
- 增量模式（当日队列已存在）只对新输入文件跑闸门，已有岗位只重算时效分，不踢出队列；
- 经验门槛自动适配：`exclude_experience_years_min = 本人年限 + 1`。

### 关键机制

- **新鲜度锚点**：每次运行先 `certutil -hashfile` 比对简历 SHA256，不一致才重新解析 PDF 并重写画像。
- **幂等与防重**：投递地址标准化（去 tracking 参数、统一末尾斜杠、域名小写）是去重和已投递排除的同一套主键；通知邮件以 `notified_<date>.json` 的 rank_list 做幂等防重。
- **降级规则**：预检契约过期/缺失 → 投递端回退自行探测；筛选读不到 delivery_log → 跳过已投递排除并报告；增量合并读旧队列失败 → 降级全量生成。
- **写入职责隔离**：预检只写 `platform_login_status.json`、投递只读；投递只写 `delivery_*.csv`、通知只读。

### 测试

```bash
python tests/run_tests.py
```

| 用例 | 场景 | 期望 |
|---|---|---|
| tc1 | 完整档案（含选填） | 创建成功 |
| tc2 | 海外岗位（日本签证示例） | 创建成功 |
| tc3 | 最小档案（选填全空） | 创建成功 |
| tc4 | 非法字段（学历序数=5、届次缺年份、词表外技能、空 overseas_rule 等 8 项） | **拒绝**并逐条列出原因 |
| tc5 | 简历已更换但 hash 未更新 | **拒绝**并报"哈希不匹配" |

### 自定义与扩展

- **加技能词/地点/大厂**：只改 `contracts/taxonomy.json`，prompt 不用动；
- **接新的搜索来源**：来源 Excel 表头变体加进 `contracts/field_map.json` 的 `column_aliases`；
- **换通知渠道**：环节 5 是唯一纯下游消费者，改它的 prompt 即可；
- **新增环节**：定义输出契约文件（带 `schema_version`）→ 下一环节 prompt 声明消费规则与降级行为 → 在数据流契约里补一条边。

### 安全模型

- 真实画像 / token 替换表 / 生成的个人版 prompt / 简历 PDF 全部被 `.gitignore` 排除，仓库只含模板与虚构数据；
- 刻意**不采集**身份证号与详细住址——管道无任何环节消费它们，采集只会扩大泄露面；
- 发布前自检：对仓库 grep 真实邮箱/手机号/身份证/姓名，应为零命中（详见 docs/prompts_template.md 附C）。

### 已知边界

- 投递/预检环节依赖本机 Chrome 以调试模式（CDP 9222 端口）运行且各平台已登录，无此环境时这两环不可用（搜索/筛选/通知三环独立可用）；
- 环节 1 的"候选人特殊身份约束"、方向限定、平台黑名单是叙事性规则，无法表单化，需按 docs 附A 人工改写；
- 岗位评分由 LLM 执行，是"概率性判断"而非"确定性规则"——每日队列附剔除审计表，建议抽查；遇图形验证码一律标记人工处理，不绕过。
