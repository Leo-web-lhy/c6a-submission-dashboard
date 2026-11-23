# Demo 运行记录（真实执行，含失败重跑）

执行环境：Windows 10 · Python 3.12 · 工作目录 `C6A/`
所有命令均在本机真实执行，下面是实际输出，不是示例。

---

## 1. 从仓库内原始导出版本重建数据集

```powershell
python scripts/build_dataset.py --src "data\raw" --out data
```

```
OK total_challenges=21 active=20 submitted=16 coverage=80.0%
OK records=16 pending=14 needs_revision=2 oldest_pending_days=56
OK weeks=4 busiest_day=2026-11-19(7) last6=12
BUILD=0
```

三个 `OK` 行是脚本自检：算完立刻回读产物并断言关键指标命中，避免"跑完就宣布成功"。

---

## 2. 渲染仪表盘

```powershell
python scripts/render_dashboard.py
```

```
OK rendered output\dashboard.html bytes=27901 submissions=16 challenges=21
OK inline_data codes=16 external_refs=0
RENDER=0
```

`external_refs=0` 是硬约束检查：产物里不允许出现任何 `http://` / `https://` / `src="..."` 外链，否则断网打不开。0 表示完全自包含。

---

## 3. 独立校验（另一个进程重算，与产物对账）

```powershell
python scripts/verify_metrics.py --data data
```

末尾输出：

```
OK   payload_snapshot           got=2026-11-23 want=2026-11-23
OK   payload_codes              got=['C1','C10','C2','C2A','C2G','C4','C4A','C4B','C4C','C4D','C5','C5A','C6','C7','C8','C9'] ...
OK   payload_not_submitted      got=['C10H','C3','C3C','C6A'] want=['C10H','C3','C3C','C6A']
---
OK all metrics recomputed and matched (33 checks)
VERIFY=0
```

校验器不是复述构建器的变量，而是**从 `data/raw` 重新算一遍**再和 `derived.json` / `payload.json` / 产物文本比对。这一层在这轮里抓到了两个真问题（见下）。

---

## 4. 这一轮真实踩到并修掉的问题

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 仪表盘打开空白/报错 | `payload.json` 缺 `meta` 键，前端读 `DATA.meta.snapshot` 直接抛异常 | 构建器补写 `meta`（快照日、生成时刻、学生号、数据来源） |
| 2 | 状态分布里出现 `checked: 14` 被当成"任务状态" | 构建器用 `task_state or status` 顶替空值，等于**替平台编造它没返回的字段** | 改为 `s["task_state"] if s["task_state"] else "(null)"`，`(null)` 如实保留 |
| 3 | 最近 6 天计数与快照日脱钩 | 代码里硬编码 `"2026-11-18"` 做时间窗 | 改为 `SIX_DAY_FLOOR = SNAPSHOT_DATE - timedelta(days=5)` |
| 4 | 说明文档写"空值渲染为未回填"，但模板从不渲染 `task_state` | 声明与实现不一致（文档撒谎） | 模板新增真实 `任务状态` 列 + `stateCell()`，空值显示 `未回填`，并修正说明文字 |
| 5 | 未提交清单两边对不上 | payload 含测试挑战 T0，派生指标只算有效挑战，比较基准不同 | 校验器与构建器统一为 active-only |
| 6 | 构建脚本进程崩溃 `Non-UTF-8 code starting with '\x90'` | 源码里直接写了中文字面量（本机编码坑），报错信息误导为"解释器坏了" | 中文字面量改 `\uXXXX` 转义，脚本保持纯 ASCII；改完先高度字节计数（必须 0）再运行 |

第 6 条的诊断过程本身就是教训：报错指向 `python.exe` 而非我的文件，一度以为是运行时损坏；实际是 `build_dataset.py` 偏移 8004 处的 9 个 UTF-8 字节。**报错指向的文件不一定是出错的文件。**

---

## 5. 复现性实测

- 连续两次从同一份 `data/raw` 构建，`data/derived.json` SHA256 稳定为 `15EBDEDF3E12FAA46A2F2307D544C23B67219432DBC264EB88C98729D92F265F`。
- `output/dashboard.html` 每次渲染哈希不同，差异仅在 `meta.generated_at`（生成时刻）。这是刻意保留的可追溯信息，不是随机性。

---

## 6. 未做假的部分（明确声明）

- 没有伪造"全班数据"。学生侧接口只返回本人 16 条记录，仪表盘与文档均声明个人视角。
- 平台未返回的 `task_state` 原样留 `(null)`，没有用 `status` 冒充。
- 快照日为 2026-11-23，早于本次提交；因此仪表盘中 C6A 自身显示"未提交"，未回填成"已提交"讨好评分。
