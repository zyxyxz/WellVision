# WellVision 钻井工程多源数据对齐知识库

- 文档定位：钻井工程数据对齐的长期维护文档（背景资料 + 专业资料 + 算法与工程方案）
- 适用范围：同一井次（`well_run`）下多来源异步数据（随钻、测井、录井、人工事件、报告）
- 首次整理日期：2026-02-19
- 维护原则：持续追加，不覆盖历史结论；结论变更需记录“变更原因 + 影响范围”

---

## 1. 问题背景与目标

### 1.1 现场真实问题

同一口井的不同数据源，常见以下不一致：

1. 采样率不同
   随钻地面参数可秒级，MWD/LWD 受遥测链路限制更稀疏，录井可能按关键点或样品深度记录。
2. 索引体系不同
   有的以时间为主（`ts`），有的以深度为主（`md`），还有事件点（`event marker`）。
3. 物理延迟与空间延迟
   录井存在返速导致的 lag；不同传感器到井底/井口的物理距离不同。
4. 作业工况变化导致统计特性突变
   钻进、接单根、起下钻、循环、测井阶段的数据分布不同，不能混合直接建模。

### 1.2 本文档目标

1. 给出可落地的井次级数据契约。
2. 给出时间轴/深度轴双主轴对齐方案。
3. 明确可在时序数据库侧完成的处理，和必须在应用层完成的算法。
4. 形成可维护的“资料与结论库”，支持后续持续迭代。

---

## 2. 钻井现场操作对数据处理的影响

### 2.1 作业阶段（必须分段）

建议至少区分以下 `op_segment`：

1. 钻进（On-bottom drilling）
2. 接单根（Connection）
3. 起钻（POOH）
4. 下钻（RIH）
5. 循环（Circulation）
6. 测井/特殊作业（Wireline / Others）

原因：不同阶段在力学负载、泵压、转速、井深变化速率上的机制不同；混合后会显著降低异常检测和趋势分析有效性。

### 2.2 数据源特征（工程视角）

| 来源 | 典型通道 | 主索引 | 采样特征 | 关键处理点 |
|---|---|---|---|---|
| 随钻地面参数 | WOB/扭矩/RPM/泵压/排量 | 时间 | 高频、连续 | 时间网格对齐 + 去毛刺 |
| MWD/LWD 实时 | 井斜/方位/伽马等 | 时间（常稀疏） | 受遥测带宽限制 | As-of 匹配 + 较大容差 |
| LWD 记忆数据回放 | 曲线全集 | 深度 | 回放/补全 | 作为深度域高精度基准 |
| 录井 | 气测/岩屑/描述 | 深度+事件 | 关键点/间隔采样 | lag 修正后再合并 |
| 井上测井（Wireline/LAS） | 电阻率/声波/密度等 | 深度 | 固定深度步长 | 深度轴主数据，不强制秒级化 |

---

## 3. 背景资料与专业资料（可持续追加）

以下资料用于支撑本方案，建议后续按主题继续补充。

### 3.1 标准与行业结构

1. Energistics WITSML 结构概览
   https://docs.energistics.org/WITSML/WITSML_TOPICS/WITSML-000-292-0-C-sv2000-structural-overview.html
2. WITSML v2.0 schema 索引
   https://energistics.org/sites/default/files/schema/WITSML_v2.0/Index.html
3. Energistics ETP（传输协议体系）
   https://energistics.org/etp/
4. IADC DDR Plus 代码集
   https://ddrplus.info/codeset/

### 3.2 专业术语与现场机制

1. Mud logging
   https://glossary.slb.com/terms/m/mud_logging
2. Lag time
   https://glossary.slb.com/terms/l/lag_time
3. Depth of samples
   https://glossary.slb.com/terms/d/depth_of_samples
4. Distance to sensor
   https://glossary.slb.com/terms/d/distance_to_sensor
5. Formation exposure time
   https://glossary.slb.com/terms/f/formation_exposure_time

### 3.3 数据格式与工具生态

1. LAS 格式说明（USGS）
   https://www.usgs.gov/programs/national-geological-and-geophysical-data-preservation-program/las-format

---

## 4. 统一数据契约（井次级）

### 4.1 核心实体

1. `well_runs`：井次主实体（井号、井段、作业起止时间、深度基准）
2. `channels`：通道字典（语义、单位、索引类型、插值策略、容差）
3. `samples_raw`：原始长表（多来源统一承载）
4. `op_segments`：工况分段表
5. `depth_time_map`：时间-深度映射（双轴桥）
6. `markers`：关键事件点（录井关键时刻、作业事件、人工标记）
7. `aligned_series`：按请求生成的对齐数据（可缓存/物化）

### 4.2 `samples_raw` 建议字段

1. `well_run_id`（UUID）
2. `source`（text：mwd/lwd/mudlog/wireline/surface/manual）
3. `channel`（text）
4. `ts`（timestamptz，可空）
5. `md`（double precision，可空，单位 m）
6. `value`（double precision）
7. `uom`（text）
8. `quality_code`（smallint）
9. `provenance`（jsonb：原始文件、版本、设备、算法版本）
10. `ingest_seq`（bigint：同源顺序号）
11. `version`（int：数据版本）

### 4.3 关键约束

1. 所有数据必须带 `well_run_id`。
2. 时间统一 UTC 存储，展示层再转换时区。
3. 深度必须带基准说明（例如井口参考/转盘面等）并统一单位。
4. 通道定义与单位换算必须由 `channels` 字典驱动，不允许在查询时临时猜测。

---

## 5. 对齐总方案：双主轴 + 分段 + 质量标记

### 5.1 双主轴原则

1. 时间轴对齐（`axis=time`）：用于实时监控、告警联动、设备关联分析。
2. 深度轴对齐（`axis=depth`）：用于地层对比、井段分析、测井/录井融合。

### 5.2 时间轴对齐（推荐规则）

1. 建固定网格：1s/5s/10s（按场景配置）。
2. 采用 As-of join（最近值匹配）+ 最大容差（`max_gap`）。
3. 连续量可线性插值；离散量仅最近邻或不插值。
4. 超过容差必须标记缺失，不允许“无限前向填充”。

### 5.3 深度轴对齐（推荐规则）

1. 建固定深度网格：0.1m/0.5m/1m（按井段与目标任务配置）。
2. Wireline/LAS/LWD 记忆数据作为深度域基准层。
3. 时间域数据通过 `depth_time_map` 投影到深度轴再合并。

### 5.4 录井 lag 修正（必做）

1. 先做 lag 修正，再进入对齐流程。
2. lag 估计输入建议：返速、环空体积、泵工况、井眼几何、样品流程。
3. lag 修正结果写回 `provenance`，并给 `quality_code` 标记“lag-corrected”。

### 5.5 工况分段后再对齐/建模

1. 先按 `op_segments` 切段，再在段内做对齐和特征。
2. 禁止跨工况直接计算窗口特征（如连接段和钻进段混算）。

### 5.6 质量码建议（示例）

1. `0` = 原始点（raw）
2. `1` = 最近邻匹配（asof）
3. `2` = 线性插值（interpolated）
4. `3` = 前向填充（forward-fill）
5. `4` = 外推（extrapolated，不推荐默认开启）
6. `5` = lag 修正点（lag-corrected）
7. `9` = 缺失（missing）

---

## 6. 算法清单（数据库侧 vs 应用层）

### 6.1 优先数据库侧执行（实时概览）

1. 重采样与聚合：`AVG/MIN/MAX/COUNT/SUM`
2. 滚动统计：`moving_average`、`rolling_std`、`rolling_range`
3. 一阶变化率：`rate_of_change`
4. 简易异常：`zscore_anomaly`
5. 线性趋势：`linear_trend`
6. 分位统计：`p50/p95`

适用目标：海量数据“概览”、快速看板、低延迟 API。

### 6.2 需要应用层执行（复杂业务语义）

1. 录井 lag 动态估计（多变量/物理约束）
2. 工况识别与状态机推断
3. 多通道耦合异常诊断（规则引擎 + ML）
4. 井段级特征工程与模型推理
5. 置信度融合与解释生成

适用目标：智能分析、工程诊断、报告生成。

### 6.3 对齐核心算法建议

1. As-of Join（最近点匹配 + 容差）
2. Piecewise Linear Interpolation（连续量）
3. Forward Fill / Nearest（离散量）
4. Hampel/Median Filter（抗毛刺）
5. Cross-correlation（lag 辅助估计）
6. Segmented Window Features（分段窗口特征）

---

## 7. 时序数据库实现建议（Postgres/Timescale）

### 7.1 表与索引建议

1. `samples_raw`：hypertable（time 维分块）
2. 关键索引：
   - `(well_run_id, channel, ts DESC)`
   - `(well_run_id, channel, md DESC)`
   - `BRIN(ts)` / `BRIN(md)`（大表场景）
3. 预聚合层：
   - `time_rollup_1s/10s/1m`
   - `depth_rollup_0_1m/0_5m`

### 7.2 查询层设计

1. `/aligned?axis=time` 优先读 time rollup，再按需回源。
2. `/aligned?axis=depth` 优先读 depth rollup，再按需回源。
3. 返回结果携带 `quality_code` 与 `provenance`，避免“黑箱曲线”。

---

## 8. WellVision 落地路线（分阶段）

### P0：数据契约与主数据

1. 引入 `well_run_id` 与通道字典。
2. 固化单位换算与深度基准规则。

### P1：对齐底座

1. 新增 `depth_time_map`、`op_segments`。
2. 实现时间轴/深度轴基础对齐 API。

### P2：录井与质量体系

1. 上线 lag 修正流水线。
2. 完整输出质量码和数据溯源信息。

### P3：智能分析增强

1. 分段特征 + 工程规则引擎。
2. 应用层复杂算法与报告自动化。

---

## 9. 验证指标（上线验收）

1. 对齐完整率：`aligned_points / expected_grid_points`
2. 可用率：`quality_code in {0,1,2,3,5}` 占比
3. lag 修正前后误差变化（与人工/基准对照）
4. 不同工况下算法稳定性（误报率、漏报率）
5. 查询性能：P95 延迟、回源比例、吞吐

---

## 10. 待确认工程问题（持续补充）

1. 井深基准是否统一到同一参考面？
2. 录井 lag 参数是否可稳定实时获取？
3. 同通道多设备冲突时，优先级与融合规则如何定义？
4. 不同业务页面默认轴（时间/深度）如何选？
5. 回灌历史数据时，版本冲突与重算策略如何固化？

---

## 11. 维护机制

1. 本文档作为单独知识库维护，不和 README 混写。
2. 每次新增规则，必须记录“来源、结论、影响模块、实施状态”。
3. 涉及现场工艺变化时，优先更新“工况分段规则”和“lag 模型参数”。

## 12. 系统实现状态（WellVision）

> 本节记录“已落地代码能力”，避免方案与实现脱节。

### 12.1 已落地的数据实体

1. `well_runs`：井次实体（名称、井名、井段、状态、起止时间、详情）。
2. `events` 增加：`well_run_id`。
3. `event_metrics` 增加：`well_run_id`、`channel`、`source`、`md`、`quality_code`。
4. `import_jobs` 增加：`well_run_id`、`source_label`。
5. `op_segments`：井次工况分段实体（`segment_type`、时间/深度范围、来源与置信度）。
6. `event_metrics_rollup_1m_v2`：分钟级预聚合（按 `tenant/warehouse/well_run/source/field` 维度）。

### 12.2 已落地 API

1. 井次管理：
   - `GET /api/well-runs`
   - `POST /api/well-runs`
   - `GET /api/well-runs/{well_run_id}`
   - `PATCH /api/well-runs/{well_run_id}`
2. 井次通道与对齐：
   - `GET /api/well-runs/{well_run_id}/channels`
   - `GET /api/well-runs/{well_run_id}/axis-map`
   - `POST /api/well-runs/{well_run_id}/align`
3. 工况分段与 lag：
   - `GET /api/well-runs/{well_run_id}/segments`
   - `POST /api/well-runs/{well_run_id}/segments`
   - `PATCH /api/well-runs/{well_run_id}/segments/{segment_id}`
   - `POST /api/well-runs/{well_run_id}/segments/detect`
   - `POST /api/well-runs/{well_run_id}/lag-correction`
4. 采集与导入链路：
   - `POST /api/ingestion/events` 支持 `well_run_id`
   - `POST /api/ingestion/import-jobs` 支持 `well_run_id`、`source_label`
5. 分析接口扩展：
   - `SeriesQuery` 支持 `well_run_id`
   - `/api/analysis/fields` 支持 `well_run_id` 过滤

### 12.3 对齐算法实现（当前版本）

1. 双轴：`axis=time` / `axis=depth`
2. 方法：`nearest` / `linear`
3. 质量码输出：
   - `0` 精确原始点
   - `1` 最近邻匹配
   - `2` 线性插值
   - `9` 缺失
4. 支持每通道配置：
   - `source`
   - `native_axis`（`auto` / `time` / `depth`）
   - `method`
   - `max_gap_seconds` / `max_gap_meters`
   - `alias`
5. 支持网格模式：
   - `grid_mode=fixed`（固定步长）
   - `grid_mode=anchor`（以锚点通道采样点作为对齐网格）
6. 支持时间-深度轴映射（axis map）：
   - 自动选择或指定 `source+channel` 构建 `time<->md` 映射
   - 跨轴投影支持 `time->depth`、`depth->time`
7. 对齐统计增强：
   - `coverage`（各通道有效覆盖率）
   - `axis_map`（映射来源与点数）
   - `anchor_alias`（锚点网格所用通道）
8. 支持分段过滤对齐：
   - `segment_ids` / `segment_types` 可直接用于对齐请求
   - 对齐统计返回 `segment_filter` 选择摘要
9. 支持 lag 修正流水线：
   - 按来源与通道执行固定 lag（前移/后移）
   - 可选基于 axis-map 重映射 `md`
   - 标记 `quality_code = 5`（lag-corrected）
10. 高规模导入优化：
   - 导入作业支持 `import_mode=metrics_only`（仅写 `event_metrics`，跳过 `events`）
   - 导入 worker 支持并发 claim（`FOR UPDATE SKIP LOCKED`）
   - CSV/Parquet 均采用流式处理，不再一次性加载全量文件
   - 分钟概览优先使用 `event_metrics_rollup_1m_v2`

### 12.4 变更记录

1. 2026-02-19：初版建立，完成背景资料、工程结论、数据契约、对齐策略与算法分层。
2. 2026-02-19：新增系统实现状态，记录已落地模型、API 与对齐算法能力。
3. 2026-02-19：对齐服务升级，新增 `native_axis`、`axis-map` 与 `anchor grid`，支持多采样率/关键点数据更稳健合并。
4. 2026-02-19：新增 `op_segments` 与 `lag-correction` 流程，支持自动工况分段、分段过滤对齐、录井 lag 批量修正。
5. 2026-02-19：导入链路升级（并发 worker + metrics-only + 流式 parquet/csv），新增井次维度分钟聚合表 `event_metrics_rollup_1m_v2` 支撑海量实时概览。
