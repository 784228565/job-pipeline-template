# 求职投递管道（Job Application Pipeline）

一套由 5 个定时 AI Agent 组成的求职自动化管道：每日搜索岗位 → 筛选排序 → 登录预检 → 浏览器自动投递 → 邮件推送待办。本仓库是**脱敏后的可复刻模板**，不含任何真实个人数据。

## 管道概览

```
06:00 搜索 Agent  → 扫描各平台，产出岗位池 Excel（~100 岗）
11:37 筛选 Agent  → 去重/已投递排除/四道闸门/五维评分 → 当日投递队列
12:30 预检 Agent  → 检查各平台登录态，产出登录契约 JSON
13:00 投递 Agent  → CDP 控制 Chrome 自动填表投递，写回状态 CSV
15:00 通知 Agent  → 汇总未投岗位，邮件推送今日待办
```

各环节通过**文件契约**解耦：岗位 Excel、画像 JSON、登录态 JSON、状态 CSV。语义归一化（中英技能词表、学历序数、字段映射）全部外置在 `contracts/`，prompt 中不内嵌个人事实。

## 新用户快速开始（3 步）

**前置**：Python 3.8+；一个能调度 prompt 的 Agent 运行环境（如 WorkBuddy）；投递/预检环节需要本机 Chrome 开 CDP 调试端口。

```bash
# 第 1 步：引导式接入 —— 回答问题 + 提供简历 PDF 路径
python setup/onboard.py
```

向导会依次询问：姓名（中/英）→ 邮箱 → 手机号 → 现居城市 → 可到岗时间 → 简历 PDF → 教育经历 → 届次身份 + 社保缴纳情况 → 技能 → 目标行业与求职方向 → 目标城市、公司国籍规则、工作年限、签证规则 → 选填项（GitHub/作品集/LinkedIn/期望薪资口径）。完成后自动生成两个**本地文件**（已被 .gitignore 排除，永远不会提交）：

| 产物 | 作用 |
|---|---|
| `contracts/candidate_profile.json` | 你的筛选画像 IR，含简历 SHA256 新鲜度锚点 |
| `local_tokens.json` | prompt 模板 11 种占位符的替换值 |

生成后立即按 `docs/prompts_template.md` 附B 的契约自动校验（必填字段、邮箱格式、学历序数、技能/地点词表归一化、简历哈希一致性），不通过会逐条说明原因。

```bash
# 第 2 步：生成你的个人版 prompt 文档
python setup/apply_tokens.py        # → build/prompts_personalized.md

# 第 3 步：把 build/ 文档中的 5 段 prompt 粘贴进你的调度器，
#         并按文档附A 改写 3 处结构性段落（身份约束/方向限定/平台黑名单）
```

**换简历后**：重跑 `python setup/onboard.py`（或手动更新 `resume_source.sha256`）。筛选 Agent 每次运行也会自动做哈希校验，发现不一致会提示重建。

## 仓库结构

```
├── docs/prompts_template.md          # 5 个 prompt 全文（占位符化）+ 数据流契约 + 接入/脱敏附录
├── contracts/
│   ├── taxonomy.json                 # 通用词表（技能同义词/学历序数/职级/地点/大厂名单）
│   ├── field_map.json                # 输入 Excel 列名归一化 + URL 标准化规则
│   ├── candidate_profile.example.json # 虚构示例画像
│   └── local_tokens.example.json      # 虚构示例替换表
├── setup/
│   ├── onboard.py                    # 引导式接入向导
│   ├── validate_profile.py           # 画像契约校验器（可单独用）
│   └── apply_tokens.py               # 占位符替换 → 个人版 prompt
└── tests/
    ├── fixtures/tc1~tc5.json         # 5 个虚构候选人测试用例
    └── run_tests.py                  # 端到端测试（创建+校验）
```

## 运行测试

```bash
python tests/run_tests.py
```

5 个虚构用例：完整档案 / 日本签证方向 / 最小档案 / 非法字段（应拒绝）/ 简历 hash 过期（应拒绝）。

## 安全说明

- 真实画像、token 替换表、生成的个人版 prompt 均被 `.gitignore` 排除；
- 提交前可用 `python setup/validate_profile.py contracts/candidate_profile.json` 自检画像；
- 模板文档中所有个人事实均为 `{{占位符}}` 或虚构示例，详见 `docs/prompts_template.md` 附C 脱敏清单。
