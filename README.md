# C6A 提交数据仪表盘

把学习平台上的真实数据（挑战清单 + 我的提交记录）落成一份**可重算**的数据集，再渲染成一个**单文件、不依赖网络、双击即可打开**的仪表盘。

不是手画一张图交作业：数据来自平台导出，指标由脚本计算，任何人可以用仓库里的原始输入重跑出同样的数字。

## 它回答三个问题

1. **我总共要做多少、已交多少？** 21 个挑战（其中 1 个是平台测试挑战，实际有效 20 个），已提交 16 个，覆盖率 80.0%。
2. **哪些还卡着、卡了多久？** 14 条待终审、2 条需返修；最久的一条从 2026-09-28 起算已 56 天。
3. **我的提交节奏是什么样？** 4 个自然周，最忙的一天 2026-11-19 提交 7 条，最近 6 天 12 条。

## 目录

```
C6A/
├── 仪表盘.html              # 自包含仪表盘（打开即用，无外链/CDN）
├── data/
│   ├── raw/                 # 平台原始导出，未改一字节
│   │   ├── audit_challenges.json
│   │   └── audit_subs.json
│   ├── challenges.json      # 规范化后的挑战表
│   ├── submissions.json     # 规范化后的提交表
│   ├── derived.json         # 派生指标（覆盖率/状态分布/周桶/最长等待）
│   └── payload.json         # 注入仪表盘的最终数据载荷
├── scripts/
│   ├── build_dataset.py     # 原始导出 → 规范化表 + 派生指标
│   ├── render_dashboard.py  # 载荷 + 模板 → 单文件仪表盘
│   └── verify_metrics.py    # 独立重算 33 项断言，与产物对账
├── template/dashboard.template.html
├── output/dashboard.html    # 渲染产物（与实际发布的 仪表盘.html 同源）
├── demo.md                  # 真实运行记录（命令 + 原始输出）
├── AI日志.md                # 与 AI 的协作过程，含被推翻的方案
├── AAR.md                   # 复盘
├── 口径说明.md              # 每个数字怎么算出来的
├── 数据字典.md              # 字段含义与取值
└── 评测对照表.md            # 评分维度 → 证据文件
```

## 复现（三条命令）

```bash
python scripts/build_dataset.py --src data/raw --out data
python scripts/render_dashboard.py
python scripts/verify_metrics.py --data data
```

实测结果：`BUILD=0` → `RENDER=0` → `VERIFY=0`，`OK all metrics recomputed and matched (33 checks)`。

## 可复现性的边界（如实说明）

- `data/derived.json` 是**确定性**的：同一份 `data/raw` 重跑，SHA256 不变（实测 `15EBDEDF…D92F265F`）。
- `output/dashboard.html` 与 `仪表盘.html` **不是**逐字节确定：载荷里写入 `generated_at` 生成时刻，每次渲染都会变。除该时间戳外其余内容一致。
- `data/raw` 是平台在 **2026-11-23** 的快照。因此仪表盘里 C6A 自己显示为"未提交"——快照早于本次提交动作，这是快照口径而非错误。

## 已知限制

- 数据只覆盖**本人**账号。挑战原文设想"管理所有人作业"，但学生侧 `list-my-submissions` 只返回自己的记录，全班数据不可得，仓库内没有伪造任何他人数据。
- 平台存在最终一致性延迟，快照时刻可能与提交动作有几秒错位。
- 指标口径绑定了本平台的状态枚举（`checked` / `needs_revision` / `task_state`）；换平台需改 `build_dataset.py` 的映射段。
