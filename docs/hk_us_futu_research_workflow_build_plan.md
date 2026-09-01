# 港股与美股 9 个研究 Skill 的 Futu 兼容化与 QuantSpace 工作流构建方案

> 状态：只读研究后的完整构建方案  
> 研究日期：2026-08-27  
> 适用项目：`D:/Code/agent-quantspace`  
> 数据源前提：Futu OpenD/Futu OpenAPI 为港股、美股的主证券数据源；其他来源仅用于 Futu 不覆盖的能力，并必须显式标注来源和时点。

> **最终审核修订（2026-08-27）**：第 17—26 节定义最终目标架构与执行门禁；前文的需求说明已同步为该目标架构。修订重点是把“可替换 provider”落成“可验证的独立 Skill 插件”，并把 Futu 的数据完整性、时区、复权、分页、权限和 provenance 约束变成实现门禁。

## 1. 执行摘要与最终决策

### 1.1 决策

本项目适合接入上游“03 市场与标的分析 → 港股与美股（9）”的研究能力，但不适合把 9 个仓库原样复制后直接运行。推荐采用：

```text
上游 Skill 规则/报告结构
        ↓ 兼容性改造
QuantSpace provider-neutral 数据契约
        ↓
Futu/OpenD 只读适配器 + 本地缓存/manifest
        ↓
QuantSpace research / compute / analyze / report
        ↓
港美股研究 workflows
        ↓
可选的、经过验证的 Factor / target weights
```

结论分为三层：

| 目标 | 结论 | 说明 |
|---|---|---|
| 用 Futu 替换 9 个 Skill 的 Pandadata 数据访问 | **部分可行** | 行情、快照、财务、估值、分红、板块和部分共识/股东数据可以适配；不是字段级一比一替换 |
| 将 9 个能力整合成 QuantSpace 研究工作流 | **可行** | 通过标准化数据对象、研究 artifact、报告工作流和能力降级实现 |
| Futu-only 完整复现全部 9 个能力并用于历史回测 | **不可行** | 主要阻断是历史共识修订、港股完整 Insider、产业链/SEC/IR 资料、FX 时间序列和 PIT 语义 |

### 1.2 推荐交付范围

第一阶段不应追求“9 个全量完成”，而应交付三个可验证的 vertical slice：

1. Futu 港美股日线 → 标准化 Parquet → 技术特征 → `quote-scan` 研究 artifact/报告；只有另行实现并通过策略、PIT、执行与 OOS 门禁的具体策略，才可产生 `StrategyResult.target_weights` 并进入 `VectorBacktester`。
2. Futu 快照/估值/分红/板块 → 结构化研究 artifact → `quote-scan`、`dividend-events`、`sector-rotation` 报告。
3. Futu 财务/共识/股东 → point-in-time 受限的基本面/共识快照 → 研究报告；没有 PIT 历史时禁止进入历史回测。

完整的 9 项能力应按以下状态管理：

- **原生适配**：`skill-hk-us-quote-scan`、`skill-hk-us-dividend-events` 的大部分功能。
- **衍生适配**：`skill-cross-listing-parity`、`skill-us-sector-rotation`、美股版 `skill-hk-us-insider-radar`、当前共识快照。
- **多源或受限适配**：`skill-hk-stock-dossier`、`skill-stock-memory-analyzer-usa`。
- **Futu-only 阻断/降级**：`skill-hk-us-consensus-revision-radar`、港股完整 Insider Radar，以及存储芯片产业链研究的外部资料部分。

## 2. 研究范围、证据与现状基线

### 2.1 上游目录与 9 个仓库

9 个目标项目由上游目录 README 列出：[quantskills/quantskills README](https://github.com/quantskills/quantskills/blob/main/README.md#L156-L224)。上游目录中的“无公开端点/待维护者审核”只能作为目录状态，不能作为实现成熟度判断；实际仓库中既有文档型 Skill，也有真实 Python 代码。

目标仓库：

1. [`skill-cross-listing-parity`](https://github.com/quantskills/skill-cross-listing-parity)
2. [`skill-hk-stock-dossier`](https://github.com/quantskills/skill-hk-stock-dossier)
3. [`skill-hk-us-consensus-radar`](https://github.com/quantskills/skill-hk-us-consensus-radar)
4. [`skill-hk-us-consensus-revision-radar`](https://github.com/quantskills/skill-hk-us-consensus-revision-radar)
5. [`skill-hk-us-dividend-events`](https://github.com/quantskills/skill-hk-us-dividend-events)
6. [`skill-hk-us-insider-radar`](https://github.com/quantskills/skill-hk-us-insider-radar)
7. [`skill-hk-us-quote-scan`](https://github.com/quantskills/skill-hk-us-quote-scan)
8. [`skill-stock-memory-analyzer-usa`](https://github.com/quantskills/skill-stock-memory-analyzer-usa)
9. [`skill-us-sector-rotation`](https://github.com/quantskills/skill-us-sector-rotation)

### 2.2 上游实现成熟度

| Skill | 上游实现形态 | 主要依赖假设 | 迁移策略 |
|---|---|---|---|
| `skill-cross-listing-parity` | 以 `SKILL.md`、参考配对 CSV、报告校验为主 | Pandadata 行情、汇率、换股比例 | 复用配对规则和公式，重写数据输入和 FX/比例校验 |
| `skill-hk-stock-dossier` | 有 `src/hk_dossier` Python 实现 | `panda-data`、港股财务/行情/股东/内幕/共识/事件接口 | 不直接 vendoring；拆成 Futu provider + QuantSpace 报告模块 |
| `skill-hk-us-consensus-radar` | Docs-only/报告规则为主 | Pandadata 共识、目标价、增长预期 | 建立共识快照 schema；不承诺历史修订 |
| `skill-hk-us-consensus-revision-radar` | 有 Python/HTML 工作流 | Pandadata 多窗口共识和事件数据 | 先做外部 sidecar 或历史快照积累，不能立即 Futu-only |
| `skill-hk-us-dividend-events` | Docs-only/接口映射和校验 | Pandadata 港美分红事件 | 用 Futu 分红历史/日历重写，保留市场币种和日期语义 |
| `skill-hk-us-insider-radar` | Docs-only/规则和校验 | Pandadata 港美 Insider 字段 | 美股优先；港股降级为股东/机构持仓变化，不伪装成 Insider |
| `skill-hk-us-quote-scan` | Docs-only/扫描规则和校验 | 行情、复权、流动性、估值、行业中位数 | 第一优先级，直接映射 Futu 行情/快照/估值/板块 |
| `skill-stock-memory-analyzer-usa` | 有 `analyze.py`、`utils/`、HTML 报告和回测辅助 | Pandadata + SEC/IR/产业链资料/模型估计 | Futu 仅提供证券数据层；行业叙事作为外部 evidence provider |
| `skill-us-sector-rotation` | Docs-only/行业轮动规则和校验 | Pandadata 行业字段、行情、sector median | 先做显式美股股票池，维护行业快照版本 |

上游代码和文档的许可证元数据并不完全一致。正式复制任何源码、参考文档、配对表或第三方资料前，必须逐仓库核对 `LICENSE`、依赖许可证和数据供应商条款；不能自动假设全部内容继承父仓库 GPL-3.0。

### 2.3 当前 QuantSpace 基线

当前项目已经具备 Futu 历史行情底座：

- [`skills/ingest/futu.py`](../skills/ingest/futu.py)：Futu/OpenD 只读历史 K 线、符号转换、分页、额度查询、OHLCV 规范化。
- [`scripts/import_futu_data.py`](../scripts/import_futu_data.py)：调用 Futu client 并将历史数据写入 DataManager 的本地 Parquet。
- [`.agents/skills/futuapi`](../.agents/skills/futuapi)：已有大量 CLI 级别的 Futu 行情、财务、分红、股东、共识、估值和板块包装器。
- `skills/store.DataManager`：已有单标的 Parquet、MultiIndex panel、factor/backtest/artifact 命名空间。
- `skills/compute`、`skills/analyze`、`skills/research`、`skills/ml`、`skills/backtest`、`skills/report`：已有技术指标、因子、研究、模型、回测和 HTML/PNG 报告能力。
- `skills/factor_mining` 和 walk-forward 代码已有 sealed OOS、数据版本、内容哈希和时间切分约束，可作为新研究因子的安全基线。

当前底座的边界不能被误读为“港美股研究已完成”：

- `FutuClient` 目前的公共可复用 API 主要还是历史 OHLCV 和 quota。
- `.agents/skills/futuapi/scripts/quote` 中的 CLI 包装器尚未形成统一的 `skills.ingest` 类型化 provider API。
- `DataManager.save_symbol(source=...)` 不足以保存完整来源、请求参数和数据快照血缘。
- 当前 `eob` 为无时区时间，不能自动表达香港和美东的原始时区、交易日历及盘前盘后语义。
- 当前前复权/后复权导入存在共用 `1d_adj` 目录语义的风险，必须在新实现中区分数据集身份。
- `skills/analyze/factor_analysis.py` 仍存在旧 `rqdatac`/provider-specific 逻辑，应在引入新研究数据前隔离或重写。
- 项目 README、`pyproject.toml` 和报告脚本仍有 PandaData-first 文案/兼容路径；迁移完成后应清理或明确其保留用途。

### 2.4 本轮前置基线（仅澄清阻断矛盾，不提前实现 P0/P1）

以下约定优先于后文的目标目录和阶段描述：

- **正式报告为 HTML-only**：`skills.report` 的正式 research archive 只以
  `index.html` 作为报告格式；Markdown、PDF 和 JSON 不是正式报告替代品。
  `manifest`、参数和指标 JSON/CSV 只属于机器可读的 artifact/provenance 或
  兼容性 sidecar，不改变正式报告格式。当前 `write_research_bundle` 产生的
  `params.json`/指标 sidecar 也按此解释。
- **保留 legacy US symbol**：目标态的 canonical symbol 是 `US.<ticker>`，但现有
  ingest API 已接受 `NASDAQ.<ticker>`，且 `US.<ticker>` 的 legacy 反向转换仍返回
  `NASDAQ.<ticker>`。在完成迁移和 round-trip 测试前，读路径、fixture 和公共 API
  必须兼容该 legacy alias；`NASDAQ` 不能据此推断 venue，也不得静默重命名或覆盖
  旧数据。
- **分离 snapshot 与 cache identity**：`request_hash`/`query_hash` 是确定性的逻辑
  请求/缓存身份；`snapshot_id` 是不可变的 provider 原始观察身份，
  `dataset_id`/`artifact_id` 是规范化或发布产物身份。缓存记录可以指向具体
  snapshot/artifact 并记录 TTL，但不能把 cache key 当 snapshot、用刷新覆盖旧
  snapshot，或把 cache hit 伪装成新的 snapshot。

## 3. Futu API 能力与限制

### 3.1 经过适配可覆盖的能力

| 能力 | 港股 | 美股 | 主要 Futu 接口 | 可支持的上游 Skill | 关键限制 |
|---|---:|---:|---|---|---|
| 历史 K 线 | ✓ | ✓ | `request_history_kline` | quote scan、parity、sector、technical | 单次请求数量和历史额度限制；需保留市场时区、session、复权身份 |
| 最新快照 | ✓ | ✓ | `get_market_snapshot` | quote scan、dossier、dividend | 只代表当前/查询时点，不能替代历史时间序列 |
| 实时行情 | ✓ | ✓ | `subscribe` + `get_stock_quote` | 实时研究预览 | 需要订阅和相应行情权限；默认不进入回测路径 |
| 复权/公司行动基础数据 | ✓ | ✓ | `get_rehab`、K 线复权参数 | quote scan、dividend、回测 | 当前 adapter 没有持久化完整调整因子和公司行动版本 |
| 财务报表 | ✓ | ✓ | `get_financials_statements` | dossier、memory analyzer、fundamental factor | 报告期不等于披露/可用时间；需自行建立 PIT 语义 |
| 收入拆分 | ✓ | ✓ | `get_financials_revenue_breakdown` | dossier、memory analyzer | 维度名称和行业分类需要标准化 |
| 估值 | ✓ | ✓ | `get_valuation_detail`、快照 PE/PB/PS | quote scan、sector、dossier | 估值字段要处理无效值和口径；不是现成的 date × symbol 因子面板 |
| 分析师共识 | ✓ | ✓ | `get_research_analyst_consensus` | consensus radar、dossier | 接近三个月聚合快照；不等价于完整历史共识轨迹 |
| 评级摘要 | ✗ | ✓（正股/REIT） | `get_research_rating_summary` | 美股 consensus radar | 仅返回 Buy/Hold/Sell 聚合；港股不得作为输入，覆盖与分页按 endpoint capability 登记 |
| 评级变化 | ✗ | ✓ | `get_rating_change` | 美股 consensus radar/revision 的有限版本 | 仅美股；不能视为港美两地统一的历史评级事件流 |
| 分红历史/事件 | ✓ | ✓ | `get_corporate_actions_dividends` | dividend events、dossier | 结构化日期可用；金额、币种和非现金分派可能只在 `statement` 文本中，不能假定可解析 |
| 分红日历 | ✓ | ✓ | `get_dividend_calendar` | dividend events | 适合按日期查询，不能替代长期事件快照库 |
| 主要股东/持仓变化 | ✓ | ✓ | `get_shareholders_overview`、`get_shareholders_holding_changes` | dossier、insider 的替代输入 | 报告期/披露频率不统一，不等价于公司 Insider |
| 美股 Insider | 主要不适用港股 | ✓ | `get_insider_trade_list`、`get_insider_holder_list` | 美股 insider radar | 交易类型需保留原枚举；Futu 响应不提供可靠披露可用时点，Futu-only 数据不得进入 PIT Insider 因子 |
| 公司资料/高管 | ✓ | ✓ | `get_company_profile`、executives、operational efficiency | dossier、memory analyzer | 文本和标签型数据需要统一 schema |
| 行业/概念/板块 | ✓ | ✓ | `get_plate_list`、`get_plate_stock`、`get_owner_plate` | sector rotation、quote scan | 当前板块关系需保存 as-of，否则会产生历史成分股生存偏差 |
| 独立 FX 历史序列 | 不应假定 | 不应假定 | 无明确可依赖的统一 FX time-series 入口 | cross-listing parity | 必须引入单独 FX provider 或固定可信数据集 |

官方文档入口：

- [历史 K 线](https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html)
- [历史 K 线额度](https://openapi.futunn.com/futu-api-doc/en/quote/get-history-kl-quota.html)
- [市场快照](https://openapi.futunn.com/futu-api-doc/en/quote/get-market-snapshot.html)
- [财务报表](https://openapi.futunn.com/futu-api-doc/en/quote/get-financials-statements.html)
- [估值详情](https://openapi.futunn.com/futu-api-doc/en/quote/get-valuation-detail.html)
- [分析师共识](https://openapi.futunn.com/futu-api-doc/en/quote/get-research-analyst-consensus.html)
- [评级摘要](https://openapi.futunn.com/futu-api-doc/en/quote/get-research-rating-summary.html)
- [分红历史](https://openapi.futunn.com/futu-api-doc/en/quote/get-corporate-actions-dividends.html)
- [分红日历](https://openapi.futunn.com/futu-api-doc/en/quote/get-dividend-calendar.html)
- [股东持仓变化](https://openapi.futunn.com/futu-api-doc/en/quote/get-shareholders-holding-changes.html)
- [内幕交易](https://openapi.futunn.com/futu-api-doc/en/quote/get-insider-trade-list.html)
- [板块归属](https://openapi.futunn.com/futu-api-doc/en/quote/get-owner-plate.html)

### 3.2 已核对的运行限制

计划中的 adapter 必须把以下限制作为 provider capability 和运行预算，而不是散落在 workflow 中：

- 历史 K 线单页不超过 Futu 接口允许的数量，使用 opaque `page_req_key` 分页；首请求与续页的限频、可回溯年限、字段历史覆盖和额度释放窗口必须由版本化 endpoint policy 管理，不能只靠统一 token bucket。
- 历史 K 线额度是账号/权限相关的 advisory 状态；导入前必须 quota preflight，分页失败、历史范围不足、权限不足、额度不足和真正无数据必须分型，不能无限重试或返回空成功。
- `RTH/ETH/ALL` 和 `extended_time` 只在 Futu 明确支持的美股分时周期组合中开放；日线及非美股不得虚构 `ETH` 数据集，且 `extended_time` 必须纳入请求、manifest 与数据集身份。
- 市场快照有 endpoint × market 的批量、订阅和短时间调用限制；需要按 capability policy 分批、预算和限流。
- 多数 F10/财务/估值/共识/股东接口使用 `next_key` 或分页参数；必须防止重复页、游标不前进和部分成功被误判为完整。
- `get_stock_quote` 依赖订阅和权限；实时能力必须和 EOD/回测数据集分开。
- Futu 返回的香港、美国时间语义不同；不能把时间直接无条件 `tz_localize(None)`。
- Futu `NONE/QFQ/HFQ` 复权模式必须成为数据集身份；在严格 PIT 下，当前拉取的 QFQ/HFQ 序列或复权因子不能仅凭模式隔离就进入回测。

### 3.3 实时测试结论

本轮只读研究没有连接真实 OpenD，也没有调用任何交易接口。独立子代理在 mock SDK 环境验证了当前 Futu ingest 专项测试，结果为 `6 passed`，覆盖符号转换、OHLCV 标准化、去重排序、分页、错误处理和 context 生命周期。更宽的 ingest 测试中出现了 PandaData 相关 Windows 临时目录权限错误，这不能作为 Futu 适配器失败结论；正式实现前仍需在主工作树重新执行完整测试。

## 4. 目标架构

### 4.1 分层架构

```text
┌─────────────────────────────────────────────────────────────┐
│ Workflow / CLI                                              │
│ run_quote_scan / run_dividend_events / run_dossier / ...    │
└──────────────────────────┬──────────────────────────────────┘
                           │ typed WorkflowRequest
┌──────────────────────────▼──────────────────────────────────┐
│ Research & Analysis                                          │
│ quote metrics / event transforms / peer ranking / reports    │
└──────────────────────────┬──────────────────────────────────┘
                           │ provider-neutral observations
┌──────────────────────────▼──────────────────────────────────┐
│ Storage & Provenance                                         │
│ DataManager / ArtifactStore / DatasetManifest / cache       │
└──────────────────────────┬──────────────────────────────────┘
                           │ normalized contract
┌──────────────────────────▼──────────────────────────────────┐
│ Ingest adapters                                              │
│ FutuProvider / FXProvider / LocalFixtureProvider / optional  │
│ external evidence providers                                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ read-only calls
┌──────────────────────────▼──────────────────────────────────┐
│ Futu OpenD / local Parquet / external evidence sources       │
└─────────────────────────────────────────────────────────────┘
```

原则：

1. Provider 只负责取数、分页、错误分类和字段映射。
2. `skills/` 负责可复用契约、标准化、指标、质量和报告基础设施。
3. `strategies/` 负责具体港美股规则、因子、标签、选择和权重生成。
4. `scripts/` 只做参数解析、配置加载、调用 workflow、输出 artifact 路径。
5. `skills` 和研究 workflow 不得直接导入 Futu 交易 context、下单方法或账户连接。
6. 在线抓取和回测读取必须分离：回测只读取已发布的本地快照。

### 4.2 建议目录布局

以下为目标布局，不要求一次性全部创建：

```text
skills/
  ingest/
    contracts.py                 # provider-neutral records, protocols and provenance
    errors.py                    # CONFIG/AUTH/QUOTA/RATE/PARTIAL 等错误
    normalize.py                 # symbol/timezone/currency/adjustment
    calendars.py                 # HK/US session/calendar helper
    futu.py                      # transport、分页、只读 SDK 边界
    providers/                   # futu_quote/fundamental/events/research；按能力拆分
    fake.py                      # offline fixture/cache replay

  store/
    data_manager.py              # 既有 OHLCV 边界，扩展结构化 dataset key
    research_store.py            # artifact、manifest、current pointer、atomic publish
    cache.py                     # request fingerprint、TTL、raw response cache
    workspace.py

  compute/
    indicators.py                # 复用现有技术指标
    wrappers.py                  # Factor wrapper
    feature_frames.py            # date × symbol 特征

  analyze/
    factor_analysis.py           # provider-neutral；隔离 rqdatac 遗留
    risk.py
    attribution.py
    robustness.py

  research/
    contracts.py                 # ResearchArtifact/WorkflowRequest/Result
    market_analysis/
      contracts.py
      protocols.py
      registry.py
      planner.py
      plugins/
        <module_name>/           # Python-safe module；manifest 声明稳定 skill_id

  report/
    contracts.py                 # pure report/provenance contract；导入时不解析 workspace
    research_report.py           # render/write runtime boundary
    renderer.py

strategies/
  cross_sectional/
    us_hk/                       # 仅经验证的因子、规则和 target weights

scripts/
  import_futu_data.py            # 现有入口，后续仅保留薄编排
  run_market_analysis.py         # 参数、registry、provider plan、报告输出

tests/
  contracts/
    test_market_research_contracts.py
    test_provider_capabilities.py
    test_pit_contract.py
  skills/ingest/
    test_futu_provider.py
    test_rate_limit_and_pagination.py
  skills/research/
    market_analysis/<module_name>/
  strategies/cross_sectional/us_hk/
  scripts/
  integration/
  policy/
  regression/
```

不建议把 `.agents/skills/futuapi/scripts/quote` 原样复制到 `skills/`。这些脚本是 CLI/Agent 入口，应提取其 SDK 调用和字段知识，重写成可测试、可复用的 `skills.ingest` adapter；`common.py` 的 import-time OpenD 检查也不应进入库模块。

### 4.3 Provider capability registry

建议使用能力注册，而不是在 workflow 中写大量 `if provider == "futu"`：

```text
ProviderCapability(
    provider_id="futu",
    endpoint="get_insider_trade_list",
    market="US",
    asset_type="equity",
    session_scope="NONE",
    supported=True,
    historical=True/False,
    pit_supported=False,
    required_entitlements=(...),
    pagination="next_key/page",
    batch_limit=...,
    rate_limit_policy="futu-insider@<version>",
    notes=[...],
)
```

workflow 在执行前解析 capability：

- `supported=True`：执行。
- `supported=False`：返回 `UNSUPPORTED_CAPABILITY`，不能自动填充。
- `historical=False`：仅允许描述性快照，不允许进入历史回测。
- `pit_supported=False`：只能用于当前运行或明确的非回测研究；历史 `as_of_utc` 不能回填为当前响应。
- `partial=True`：报告必须展示缺失市场、字段和降级原因。

## 5. 统一数据契约

### 5.1 InstrumentIdentity

标的代码不能作为不可变主键。建议定义：

```text
instrument_id       string       # 内部不可变 ID
canonical_symbol    string       # QuantSpace 规范；US 用 US.<ticker>，不从 Futu 推断 venue
provider             string       # futu
provider_symbol     string       # HK.00700 / US.AAPL
market              enum         # HK / US
venue               string?      # 经 instrument master 核验的 HKEX / NASDAQ / NYSE / ARCA
asset_type          enum         # equity / etf / reit / fund / index
share_class         string?
isin                string?
currency            ISO4217
exchange_timezone   IANA TZ
calendar_id         string
valid_from          timestamp
valid_to            timestamp?
aliases             list[InstrumentAlias]
```

当前 QuantSpace 与 Futu 的转换关系需要固化为单一规则：

```text
QuantSpace HKEX.00700  ↔ Futu HK.00700
QuantSpace US.AAPL     ↔ Futu US.AAPL
```

上面 `US.AAPL` 是目标态 canonical symbol；现有 `NASDAQ.AAPL` 作为 legacy
alias 的兼容规则见 §2.4。Futu 的 `US.<ticker>` 只表达美国市场，不能无损反推出 NASDAQ/NYSE/ARCA。venue 只能由带有效期的 instrument master 解析；无法消歧时拒绝解析，不能默认归为 NASDAQ。

```text
InstrumentAlias:
    instrument_id
    alias
    alias_type/provider?
    valid_from/valid_to
    resolution_source
```

上游 `0700.HK`、`0005.HK` 和纯 `AAPL` 只作为带有效期的输入别名，解析后必须落到 `InstrumentIdentity`；不能直接拿别名作为文件名或主键。

### 5.2 BarRecord

```text
instrument_id
bar_frequency       1m/5m/1d/...
bar_start_utc       UTC-aware timestamp
bar_end_utc         UTC-aware timestamp
eob                 datetime       # 兼容 QuantSpace：交易所本地 wall-clock、tz-naive
source_timezone     IANA TZ        # 必填；由其与 eob 校验/派生 UTC 时间
session_date        date           # 交易所本地日期
session_scope       RTH/ETH/ALL/NONE
extended_time       bool           # Futu 请求语义的一部分
bar_available_at_utc                # 可安全用于信号的最早时点
is_partial          bool
open/high/low/close numeric
volume              numeric
price_currency      ISO4217
volume_unit         string
adjustment_mode     raw/forward/backward
price_factor        numeric?
volume_factor       numeric?
factor_source       string?
adjustment_available_at_utc?
adjustment_snapshot_id?
calendar_id
dataset_id
source_snapshot_id
```

唯一身份建议为：

```text
(dataset_id, instrument_id, bar_frequency, bar_end_utc, session_scope, extended_time, adjustment_mode)
```

OHLCV Parquet 仍可保留现有 QuantSpace 的 `open/high/low/close/volume` 和无时区 `eob` 兼容面板；`eob` 一律为交易所本地墙上时间，跨市场比较一律使用 UTC 字段。上述语义、`source_timezone`、`bar_available_at_utc` 和复权快照必须通过 manifest/metadata sidecar 保存。

### 5.3 QuoteSnapshot

```text
instrument_id
observed_at_utc
market_date
last_price
open/high/low/prev_close
volume/turnover/turnover_rate
market_cap/free_float_cap?
pe/pb/ps
eps/net_asset/dividend_yield?
price_currency
session_scope
provider_update_time
source_snapshot_id
```

快照不得被转换成历史 K 线，也不得默认为历史因子值。若用于研究报告，报告必须显示观察时间和是否为实时/延迟数据。

### 5.4 FundamentalObservation

```text
instrument_id
metric_id
value
unit
currency
period_start
period_end
fiscal_period
report_type
announced_at_utc
filed_at_utc?
available_at_utc
effective_at_utc?
revision_id
is_restated
raw_field_id
source_snapshot_id
pit_supported
```

报告期、发布日期和可用时间必须分开。没有 `available_at_utc` 的财务值只能用于描述性报告，不能进入历史回测。

### 5.5 CorporateAction / DividendEvent

```text
instrument_id
event_type          dividend/split/buyback/other
announce_date?
record_date?
ex_date?
pay_date?
effective_date?
cash_amount?        # 仅在结构化字段或经审核的解析规则可得时填写
cash_currency?      # 同上
ratio?
statement           # 保留 provider 原文
parse_rule_id?
parse_confidence?
process_status
source_available_at_utc?
local_retrieved_at_utc
pit_supported
source_snapshot_id
```

上游的字段拼写、币种和事件日期必须通过显式 mapping，不应在 workflow 中直接读字符串列。Futu 分红响应中金额、币种和非现金分派可能仅见于 `statement`；没有可审核的解析结果时保留 null，并禁止计算 TTM yield 或 PIT 事件因子。

### 5.6 ConsensusObservation

```text
instrument_id
analyst_id?
institution_id?
rating
rating_scale
target_price
target_currency
estimate_period?
coverage_count?
rating_updated_at_utc?
recommendation_date?
available_at_utc
source_url?
source_snapshot_id
historical_scope       snapshot/trajectory
pit_supported
```

`get_research_analyst_consensus` 的当前聚合结果应标记为 `historical_scope=snapshot`；不能把它伪装成逐分析师的历史修订事件流。

### 5.7 InsiderTransaction / HoldingChange

二者必须分开：

```text
InsiderTransaction:
    holder_id/name/title
    transaction_type
    transaction_date
    disclosed_at?                # provider 未提供时必须为 null，不能用抓取时间代替
    source_available_at_utc?
    local_retrieved_at_utc
    shares
    price_min/price_max
    holding_after
    market_scope
    is_open_market
    pit_supported
    source_snapshot_id

HoldingChange:
    holder_id/name
    holder_type
    report_period
    holding_date
    shares_before/after/change
    ownership_ratio
    disclosed_at?                # provider 未提供时必须为 null
    source_available_at_utc?
    local_retrieved_at_utc
    pit_supported
    source_snapshot_id
```

港股股东持仓变化不能自动命名为港股 Insider Trade。没有独立披露源时，Futu-only Insider/HoldingChange 仅作描述性研究，不得进入严格 PIT 因子。

### 5.8 SectorMembership / CrossListingPair / FxRateObservation

```text
SectorMembership:
    instrument_id
    taxonomy
    sector_code/name
    industry_code/name
    as_of_date
    valid_from/valid_to
    source_snapshot_id

CrossListingPair:
    pair_id
    left_instrument_id
    right_instrument_id
    share_ratio                    # 明确 left/right 的换算方向
    ratio_source
    fx_pair
    fx_source
    valid_from/valid_to
    verification_status

FxRateObservation:
    base_currency
    quote_currency
    quote_per_base                 # 固定方向，避免倒数混用
    observed_at_utc
    available_at_utc
    source_snapshot_id
    max_staleness
    pit_supported
```

跨市场平价公式可以复用上游规则，但必须把股数比方向、FX 汇率与方向、价格币种、交易所收盘时间、FX 最大陈旧度和观察/可用时点都记录在数据里。报告币种换算也必须留下原币种、汇率、FX snapshot 与转换时间的血缘。

### 5.9 DatasetManifest

每次抓取和每次发布都生成 immutable manifest：

```text
snapshot_id                 # 不可变抓取快照 ID；与 raw/content hash 可追溯
artifact_id                 # 不可变规范化/发布产物 ID
dataset_id                  # 结构化 dataset key 的稳定标识
schema_version
provider
capability
endpoint
request_params
request_hash
canonical_symbols
provider_symbols
requested_start/end
actual_start/end
as_of_utc?
source_timezone
market_timezone
calendar_id
session_scope
extended_time
adjustment_mode
adjustment_snapshot_id?
price_currency
retrieved_at_utc
sdk_version
opend_version?
page_count
row_count
expected_row_count?
missing_intervals?
coverage_ratio
coverage_definition
complete
status
failure_reason?
retry_after?
pit_supported
raw_payload_hash?
code_commit
lockfile_hash
parent_artifacts
```

`DataManager.save_symbol(source=...)` 不能替代该 manifest；应增加 sidecar 或通过 `ArtifactStore` 发布。`coverage_definition` 必须以 `calendar_id + session_scope + extended_time` 定义预期 bars/标的分母，并声明 IPO、停牌、退市和允许的连续缺口；每个 workflow/回测入口应有明确最小覆盖阈值。

## 6. 存储、缓存与发布策略

### 6.1 目录约定

兼容现有 QuantSpace 的市场文件，同时避免复权/会话覆盖：

```text
data/
  market/
    futu/{frequency}/{adjustment_mode}/{session_scope}/{extended_time}/{dataset_id}/
      {canonical_symbol}.parquet
  raw/
    providers/futu/{capability}/{request_hash}.json
  artifacts/
    {skill_id}/{artifact_type}/{artifact_id}/data.parquet
    {skill_id}/{artifact_type}/{artifact_id}/manifest.json
  current/
    {skill_id}/{artifact_type}/{query_hash}.json
  universes/
    {market}/{universe_id}/{as_of}.parquet
reports/
  {skill_id}/{skill_version}/{run_id}/index.html
```

`index.html` 是 HTML-only 正式报告；报告 provenance manifest 留在
`data/artifacts/.../manifest.json`，不另设 Markdown/PDF/JSON 正式报告。

现有 `1d_adj` 数据可以保留为 legacy 数据，但新实现必须使用完整的结构化 dataset key：provider、frequency、adjustment、session、extended-time 语义、calendar、schema/content 版本均不可省略；仅 `1d_qfq` 或 `1d_rth` 都不足以避免混写。Futu 未支持的组合（例如日线 `ETH`）不得创建。迁移时不应静默覆盖旧文件。

### 6.2 请求指纹

缓存 key 至少包含：

```text
provider
capability
canonical_symbols（排序后的规范序列）
provider_symbols（排序后的规范序列）
start/end
as_of_utc
frequency
adjustment_mode
session_scope
extended_time
calendar_id
fields
currency_mode
api_version
schema_version
request_semantics_version
```

`request_hash` 是逻辑请求/缓存身份，`snapshot_id` 是某次不可变源响应身份；
一次缓存刷新可以产生新的 snapshot 和 artifact，但不得覆盖旧 snapshot。`query_hash`
只用于 workflow/current 指针的逻辑查询身份；cache hit 必须保留其实际指向的
snapshot/artifact 与 freshness，不得互相替代。

以下变化必须生成新 artifact，而不是覆盖旧缓存：

- `raw` / `forward` / `backward`；
- RTH / ETH / ALL；
- 不同币种转换；
- 不同报告期或 as-of；
- 不同字段集；
- 不同 provider/API 版本。

### 6.3 缓存 TTL

| 数据 | 建议缓存 | 回测可用性 |
|---|---|---|
| EOD K 线 | 持久 Parquet，按不可变数据集版本刷新 | raw bars 可在明确下一可交易时点后使用；严格 PIT 下 QFQ/HFQ 还须有当时可见的复权/公司行动快照 |
| 实时快照 | 秒级至分钟级 | 不可直接用于历史回测 |
| 财务报表 | 公告事件或日级刷新 | 只有有 `available_at`/历史版本才可用于回测 |
| 分红事件 | 日级或事件触发 | 只有 source available time 与可审核金额/币种齐全时才可用于事件研究 |
| 共识 | 日级快照 | 当前聚合只用于描述性研究 |
| Insider/股东 | 日级/披露事件 | 没有披露/可用时间时只作描述性研究；需区分 transaction/disclosed/report period |
| 行业归属 | 按版本/as-of 刷新 | 历史研究必须使用当时的 universe |
| 期权链 | 短 TTL | 没有历史链时禁止伪造历史 IV/Greeks |
| 账户数据 | 默认不持久化或单独加密 | 不进入本期研究核心 |

### 6.4 原子发布与 last-known-good

所有刷新都采用：

```text
preflight
  → fetch
  → normalize
  → validate
  → stage/{run_id}
  → manifest/hash complete
  → atomic publish current pointer
  → report
```

失败时：

- 保留上一次完整快照；
- 新快照标记 `failed` 或 `partial`；
- 当前生产指针不变；
- 报告若使用旧数据，必须标记 `stale=true` 及年龄；
- 不允许先删除旧报告再写新报告；
- 只在 staging 完整校验后原子替换报告目录。

## 7. 9 个 Skill 的工作流设计

### 7.1 统一 WorkflowRequest / WorkflowResult

```text
WorkflowRequest:
    workflow_name
    market: HK/US/BOTH
    canonical_symbols
    universe_id?
    start_date?
    end_date?
    as_of_utc?                    # timezone-aware cutoff；当前能力不能伪装成过去 as-of
    data_source_plan              # §18.3 的多 provider binding
    currency_mode
    adjustment_mode
    session_scope
    extended_time
    pit_policy: descriptive/strict
    decision_time_utc?
    execution_rule?               # next tradable bar / explicit lag；仅策略路径使用
    allow_stale: bool
    output_namespace
    report_format: html                  # 正式报告唯一格式；机器数据走 artifact

WorkflowResult:
    status: complete/partial/unsupported/blocked/stale/failed
    run_id
    artifacts
    manifests
    coverage
    warnings
    unsupported_fields
    provenance
```

### 7.2 `skill-hk-us-quote-scan`

**优先级：P2；Futu 适配度最高。**

入口：`skills/research/market_analysis/plugins/hk_us_quote_scan/workflow.py`

输入：

- HK/US 显式标的列表；
- 观察区间：若展示 1Y/YTD，默认从所需最早观察日（至少 1 年）抓取；仅在显式关闭 1Y/YTD 后才可使用约 120 个交易日的轻量窗口；
- timezone-aware `as_of_utc`；
- `adjustment_mode`；
- `session_scope`；
- 可选行业/同业 universe。

Futu 数据：历史 K 线、快照、估值详情、所属板块、必要时公司资料。若 `as_of_utc` 早于本次运行，快照、估值和板块只能读取当时已发布的 archived artifact；没有 archive 时必须标记 `unsupported`，不得回填当前响应。

计算：

- 1D/1W/1M/3M/YTD/1Y 收益；
- 波动率、最大回撤、成交量/成交额、换手率；
- PE/PB/PS 当前值、历史区间和分位数；
- 行业相对排名；
- 价格币种和报告币种分开显示。

产物：

```text
data/artifacts/hk-us-quote-scan/quote-scan/{artifact_id}/data.parquet
data/artifacts/hk-us-quote-scan/quote-scan/{artifact_id}/manifest.json
reports/hk-us-quote-scan/{skill_version}/{run_id}/index.html
```

正式报告为 HTML-only；结构化 provenance 仍由上面的 artifact manifest 提供。

不直接生成 target weights。若后续提取动量/波动率/流动性因子，必须另建 `strategies/cross_sectional/us_hk` 的具体因子模块，并通过 `Factor`/`StrategyResult` 输出。

### 7.3 `skill-hk-us-dividend-events`

**优先级：P3；Futu 适配度高。**

入口：`skills/research/market_analysis/plugins/hk_us_dividend_events/workflow.py`

输入：标的、过去/未来窗口、币种报告方式、是否计算 TTM yield。

Futu 数据：`get_corporate_actions_dividends`、`get_dividend_calendar`、快照和历史价格。

规则：

- 单独处理 HKD/USD；
- 分离公告日、登记日、除息日和派息日；
- 现金股息金额、币种、每股/总额语义必须来自结构化字段或经审核的解析规则；否则标记 `unsupported`；
- TTM yield 的分母必须是明确的价格观察日，且只有金额与币种均可审核时才计算；
- 不把 DRIP 示例直接当成账户可执行策略；
- 不推断税费、零股、汇率和账户结算规则。

产物：事件表、未来分红日历、TTM yield 快照和 HTML-only 正式报告。

默认只生成研究 artifact。若生成分红因子，必须使用除息日前已知数据和明确的事件可用时间。

### 7.4 `skill-cross-listing-parity`

**优先级：P3；公式可复用，数据层需要改造。**

入口：`skills/research/market_analysis/plugins/cross_listing_parity/workflow.py`

输入：A/H 或 ADR 配对表、观察日、股数/存托比例、FX provider、市场时段策略。

Futu 数据：HK/US 价格、历史 K 线、必要时公司行动。

外部必需数据：

- CNY/HKD/USD FX 历史序列；
- 经过核验的股数比/存托比例；
- HK/US 交易日历和观察时点。

输出：

- parity price；
- premium/discount；
- FX-adjusted spread；
- pair data-quality status；
- 观察报告。

严禁：

- 将价差观察直接解释为无风险套利；
- 忽略借券、税费、结算、资金跨境、市场时差和容量；
- 使用当前配对关系回填历史；
- 将价差直接转成交易权重而不经过策略和执行模型。

### 7.5 `skill-us-sector-rotation`

**优先级：P3；先做有限显式股票池。**

入口：`skills/research/market_analysis/plugins/us_sector_rotation/workflow.py`

输入：固定 universe 快照、行业 taxonomy、1D/1W/1M/3M/YTD 窗口、估值字段、timezone-aware `as_of_utc`。

Futu 数据：历史 K 线、快照、估值详情、plate/owner plate。

第一版限制：

- 不扫描全市场；
- 不使用当前行业关系回填历史；
- 使用显式 `universe_id + as_of_date`；
- 先采用 Futu 可取得的板块分类，后续再接 GICS/外部 taxonomy；
- 计算行业收益中位数、估值快照和排名变化，不宣称预测有效性。

产物：sector membership snapshot、sector metrics、ranking report、quality manifest。

若转为行业轮动因子，需在 `strategies/cross_sectional/us_hk/sector_rotation.py` 单独实现，并做 IC/稳健性验证。

### 7.6 `skill-hk-us-insider-radar`

**优先级：P3；拆成 US complete-ish / HK limited。**

入口：`skills/research/market_analysis/plugins/hk_us_insider_radar/workflow.py`

美股路径：

- `get_insider_trade_list`；
- `get_insider_holder_list`；
- 区分公开市场买卖、期权、赠与和其他交易类型；
- 保存交易日、持股后数量和角色；provider 未提供披露日时必须明确为 null。

港股路径：

- 不宣称拥有等价 Insider Trade；
- 可使用股东持仓变化/机构持仓作为单独的 `holding_change` 报告；
- 报告标题和 schema 必须明确“股东/机构持仓变化”，不能叫“港股内部人交易”。

输出：交易分类、净方向、金额/股数、集群标记、持仓轨迹、缺失字段诊断。

默认只做描述性研究；即便未来做 Insider 因子，也必须以公开市场交易、来自独立披露源的披露时间和可用时间为条件。

### 7.7 `skill-hk-us-consensus-radar`

**优先级：P4；先做 snapshot，不承诺完整成长预期。**

入口：`skills/research/market_analysis/plugins/hk_us_consensus_radar/workflow.py`

Futu 数据：

- `get_research_analyst_consensus`；
- 仅美股正股/REIT 使用 `get_research_rating_summary`；港股标记 `unsupported`；
- 仅美股有限使用 `get_rating_change`；
- 快照/市场价格作为目标价 upside 基准。

输出：覆盖人数、评级分布、目标价上下限/均值、当前价格 upside、评级明细和来源时间。

明确限制：

- 聚合共识是当前快照，不是逐分析师历史数据；
- 没有历史记录积累时，不生成“过去一周/一月修订”结论；
- 没有统一的 LTGROWTH 字段时，显示 `unsupported`，不使用替代值伪装；
- 目标价币种和当前价格币种必须一致或明确 FX 转换。

### 7.8 `skill-hk-stock-dossier`

**优先级：P4；拆成基础档案和增强档案。**

入口：`skills/research/market_analysis/plugins/hk_stock_dossier/workflow.py`

基础档案模块：

- 公司简介、高管、上市信息；
- 行情和估值；
- 财务三表和关键指标；
- 分红；
- 主要股东；
- 共识快照；
- 数据质量和缺失字段。

增强模块：

- Insider/事件；
- IR/公告；
- 竞争格局；
- 业务和产业链 evidence。

Futu 能力不足的字段必须落入 `unsupported_fields`，而不是由模型推测。报告应分辨：

- provider fact；
- derived metric；
- external evidence；
- analyst interpretation。

该 workflow 默认只产出研究报告，不产出权重。

### 7.9 `skill-hk-us-consensus-revision-radar`

**优先级：P5；Futu-only 不能立即完整实现。**

入口：`skills/research/market_analysis/plugins/hk_us_consensus_revision_radar/workflow.py`

上游的关键价值是多窗口目标价/评级轨迹和状态机，而不是当前共识快照。安全实现需要：

1. 逐次抓取并保存不可变 consensus snapshot；
2. 保存 `available_at`、评级更新时间、分析师/机构身份；
3. 通过 snapshot diff 生成 revision event；
4. 按 1W/1M/3M/6M/12M 计算轨迹；
5. 以 PIT policy 检查历史可见性。

在历史快照库积累前，可提供：

- 当前评级明细；
- 有限的 US rating change；
- `revision_history=unavailable` 的报告。

不能做：

- 用今天的聚合共识重建过去；
- 把接口更新时间当成逐分析师事件；
- 将当前快照直接用于历史回测。

### 7.10 `skill-stock-memory-analyzer-usa`

**优先级：P5；作为多源研究 sidecar。**

入口：`skills/research/market_analysis/plugins/stock_memory_analyzer_usa/workflow.py`

Futu 负责：

- MU、SKHY、SNDK、WDC、STX 等主题标的行情；
- 财务报表、收入拆分、估值、共识、股东/Insider（可用时）。

外部 evidence provider 负责：

- SEC/IR/公司公告；
- DRAM/NAND/HBM 产业周期；
- CapEx、供给、需求、价格节点；
- 外部行业报告和引用来源。

每个外部事实必须有 URL、发布时间、抓取时间、引用片段标识和 source license/terms 状态。模型估计必须单独标记 `estimated=true`，不能伪装为 Futu 事实。

该 workflow 可生成 HTML 研究报告和研究评分，但只有在每个特征满足 PIT 和可复现要求后才允许进入策略因子。

## 8. Workflow 执行控制流

### 8.1 标准执行步骤

```text
1. parse WorkflowRequest
2. resolve canonical symbols/universe
3. resolve provider capabilities
4. OpenD readiness / permission / quota preflight
5. compute deterministic request hash
6. load valid cache or fetch missing pages
7. normalize timezone/currency/adjustment/fields
8. validate schema, coverage, dates and quality
9. write staging artifact and manifest
10. publish atomically as current snapshot
11. run research transformations
12. validate PIT and unsupported fields
13. render ResearchReport/write_research_bundle
14. write run summary, warnings and quality metrics
```

### 8.2 错误分类

统一错误码：

```text
CONFIG_ERROR
AUTH_ERROR
OPEND_UNAVAILABLE
OPEND_TIMEOUT
PERMISSION_DENIED
RATE_LIMITED
QUOTA_EXCEEDED
INVALID_SYMBOL
UNSUPPORTED_CAPABILITY
PARTIAL_RESPONSE
PAGINATION_ERROR
SCHEMA_ERROR
CALENDAR_ERROR
STALE_DATA
PIT_UNAVAILABLE
PROVENANCE_ERROR
PROVIDER_ERROR
```

处理规则：

- 连接重置、短暂超时、OpenD 重启：有限次数指数退避加 jitter。
- 鉴权、权限、非法标的、非法参数、能力不支持：不重试。
- quota exhausted：停止该标的/批次并发布明确失败状态。
- 分页游标重复或不前进：立即失败，不进入“完整数据”状态。
- 部分响应：保留已完成页，但 manifest 标记 `complete=false`。
- provider fallback：只有字段语义完全相容时才允许，并记录来源变更。
- 没有 PIT：报告可继续，但回测入口必须 fail closed。

### 8.3 只读和交易隔离

本期研究系统必须：

- 只创建 Futu `OpenQuoteContext`，并只允许 research provider 的 SDK 方法 allowlist；`OpenQuoteContext` 自身也不得调用自选股、价格提醒等写操作；
- 不创建 `OpenSecTradeContext`，也不导入或调用 `place_order`、`modify_order`、`cancel_order`、`unlock_trade`；
- 不读取账户余额、订单和交易凭证；
- research provider 不得通过动态 import、反射或 `subprocess` 绕过 allowlist；
- 研究报告中的 target weights 只能是建议数据，不自动转换为订单；
- 交易 API policy 只扫描本方案的 `skills/ingest`、`skills/research`、`strategies/cross_sectional/us_hk` 和 `scripts/run_market_analysis.py`；已有 `.agents/skills/futuapi` 交易 CLI 不属于 research package，且不得被其导入或执行；
- 交易能力未来若需要，另设 `skills/execution`，不与本方案混合。

## 9. 因子、target weights 与报告边界

### 9.1 Research artifact

以下都属于 artifact：

- 快照、历史 K 线和覆盖率；
- 财报、估值、公司资料；
- 分红、股东、Insider、共识事件；
- 行业归属和 universe snapshot；
- 跨市场配对和 FX 数据；
- peer matrix、评级报告、dossier、memory report；
- IC/IR、稳健性、回测、模型元数据；
- manifest、质量诊断和运行日志摘要。

### 9.2 Factor

Factor 必须是：

- 数值型 date × symbol 序列；
- 已经过时间、币种、行业和可用时间对齐；
- 有明确缺失策略；
- 有数据快照和 schema 版本；
- 能通过离线 fixture 重算；
- 不含未来数据和当前快照倒灌。

例如，quote scan 中的 3M momentum 可以成为候选 factor；但整份 quote scan HTML 不是 factor。

### 9.3 Target weights

只有具体策略决策才能生成 `StrategyResult.target_weights`：

```text
研究数据
  → 经过时间对齐的 Factor/Feature
  → strategies/cross_sectional/us_hk 或既有 cross_sectional/time_series 规则
  → StrategyResult.target_weights
  → VectorBacktester
```

以下不能冒充 target weights：

- 目标价 upside；
- Insider 净买入；
- 原始共识评分；
- 原始期权链；
- 报告排序；
- 组合诊断建议；
- 账户/订单数据。

## 10. 初版能力依赖说明

> 本节只保留能力依赖说明；权威实施顺序、阶段编号和 Go/No-Go 门禁以第 24 节 P0—P6 为准。

### 初版依赖项：契约冻结与安全基线

交付：

- `InstrumentIdentity`/`InstrumentAlias`、`BarRecord`、`QuoteSnapshot`、`FundamentalObservation`、`DividendEvent`、`ConsensusObservation`、`InsiderTransaction`、`SectorMembership`、`FxRateObservation`、`DatasetManifest`。
- provider capability registry。
- 统一错误码、request fingerprint、缓存和 manifest。
- HK/US timezone/calendar helper。
- raw/qfq/hfq 与 Futu 实际支持的 session/extended-time 组合的数据集身份。
- OpenD quote-only 隔离和静态交易 API denylist。
- `LocalProvider` 和最小离线 fixture。

退出标准：

- 不安装 `futu-api` 时核心包仍可导入；
- Futu 不可用时可运行 fixture workflow；
- 所有 artifact 有 `snapshot_id`/`request_hash`/`schema_version`；
- 负 `signal_lag`、未定义的 decision/execution time、同 bar 收盘成交、不完整数据、PIT 缺失能被拒绝；
- 研究模块不依赖 Futu SDK。

### 初版依赖项：Futu 港美股 EOD 与 quote scan vertical slice

交付：

1. 将现有 `FutuClient` 包装为 `FutuMarketProvider`。
2. 完成 HK/US 日线 raw/qfq/hfq 分离。
3. 完成 timezone/calendar/session/provenance。
4. 完成 `run_quote_scan`。
5. 在先抽取纯 `skills.report.contracts`、补齐版本化 report manifest 与原子 bundle writer 后，复用现有 `compute`、`ReportRenderer`、`ResearchReport` 和 DataManager。
6. 输出一份 HK 和一份 US fixture 对比报告。

退出标准：

- OpenD mock → normalize → DataManager → quote metrics → report 全链路通过；
- 实际 OpenD 只读 smoke test 可显式 opt-in；
- 没有真实连接时 CI 不失败；
- 报告能标明 data age、market timezone、adjustment 和 coverage。

### 初版依赖项：事件、板块、跨市场和美股 Insider

按此顺序：

1. `dividend-events`；
2. `us-sector-rotation`，显式股票池；
3. `cross-listing-parity`，先接入独立 FX fixture/provider；
4. US `insider-radar`；
5. HK shareholder-change 报告作为独立降级能力。

退出标准：

- 每种事件都有 typed schema 和 manifest；
- 港美币种、日期和市场时区不混淆；
- cross-listing 的比例和 FX 来源可追溯；
- 港股 Insider 缺口在报告中显式呈现；
- 行业 universe 有 as-of 版本，不使用当前成分回填历史。

### 初版依赖项：财务、当前共识和基础 dossier

交付：

- Futu financial provider；
- valuation snapshot；
- company profile/executive；
- shareholder overview/holding changes；
- analyst consensus/rating summary；
- `run_hk_stock_dossier` 基础版；
- `run_consensus_radar` 当前快照版。

退出标准：

- 财务字段有稳定的 `field_id` mapping；
- 报告期、公告日、可用日分开；
- 没有 PIT 历史的值不能进入回测；
- 共识报告明确是 snapshot 还是 trajectory；
- missing/unsupported 字段不会被模型静默填充。

### 初版依赖项：历史共识、增强 dossier 和 memory analyzer

交付条件：

- 先积累不可变 consensus snapshots；
- 具备历史 available_at 和 source timestamp；
- 引入可审计的 SEC/IR/行业 evidence provider；
- 许可证和第三方数据授权审核完成；
- 外部 evidence 与 Futu facts 分层渲染。

如果这些条件不满足，P4 只提供 sidecar 报告，不提供回测因子。

### 初版依赖项：生产化调度与运维

交付：

- Windows Task Scheduler 或 CI 调度入口；
- preflight、quota budget、rate limiter、重试和熔断；
- staging/atomic publish/last-known-good；
- structured logs、metrics、run ledger；
- schema drift、coverage drift、stale data 告警；
- SBOM、第三方许可清单和 secret scanning；
- 运维 runbook 和失败恢复演练。

## 11. 依赖、配置与运行方式

### 11.1 依赖策略

继续使用 `uv`：

```bash
uv sync
uv sync --extra futu
uv sync --extra report
uv sync --extra analyze
uv sync --extra ml
```

原则：

- `futu-api` 只在 Futu provider 层 lazy import；
- report/ML/绘图库保持可选依赖；
- 不因为引入上游 dossier 或 memory analyzer 就整体复制其依赖树；
- 上游实现的业务规则和字段映射优先重写为 QuantSpace 原生模块；
- CI 默认只使用 fixture，不访问真实 OpenD。

### 11.2 配置

配置优先级：

```text
命令行参数 > 环境变量 > workspace 配置 > workflow 默认值
```

建议变量：

```text
QUANTSPACE_WORKSPACE_ROOT
QUANTSPACE_DATA_ROOT
QUANTSPACE_REPORTS_ROOT
FUTU_OPEND_HOST=127.0.0.1
FUTU_OPEND_PORT=11111
QUANTSPACE_FUTU_MODE=offline|mock|live_quote_only
QUANTSPACE_ALLOW_STALE=false
QUANTSPACE_PIT_POLICY=strict|descriptive
```

禁止：

- 将 token、密码或完整账户 ID 写入仓库、fixture、manifest 或日志；
- 将 OpenD 远程地址默认写入配置；
- 将交易环境、账户 ID 或 `trd_env` 传给研究 workflow；
- 用 `FUTU_*` 环境变量回显敏感信息。

### 11.3 调度

推荐调度任务：

```text
收盘后：EOD K 线导入 → 质量检查 → 发布 current snapshot
收盘后：quote scan / sector rotation / dividend refresh
公告触发：financial / earnings / dossier refresh
定时低频：consensus snapshot / insider / shareholder refresh
人工触发：cross-listing parity / memory analyzer
```

所有任务必须有 `run_id`、状态、失败原因、开始/结束时间和发布的 snapshot_id。

## 12. 测试与验收方案

### 12.1 `tests/contracts/`

- HK `HK.00700`、US `US.AAPL`、legacy `NASDAQ.AAPL` 与 canonical identity 的映射；Futu US alias 不得反向推断 venue；
- HK leading zero、经核验的 NYSE/NASDAQ/ARCA venue、ADR、class share、ticker rename；
- `InstrumentIdentity` 不可变 ID 和 alias 有效期；
- `BarRecord` 唯一键、字段 dtype、排序和 OHLCV 约束；
- `session_scope`、`extended_time`、`calendar_id`、`adjustment_mode` 和不可变 dataset version 进入数据集身份；
- `price_currency`、`report_currency`、`FxRateObservation.quote_per_base`、FX observed/available time 必填策略；
- `bar_available_at_utc`/事件或财务 `available_at_utc <= decision_time_utc`，且 execution 必须是下一可交易 bar 或明确的安全 lag；
- `pit_supported=false` 的数据禁止进入回测；
- `ResearchReport` 必须绑定 manifest、snapshot、代码版本和 coverage；
- provider 未安装时核心包可导入，调用时返回明确错误。

### 12.2 `tests/skills/ingest/`

- OpenD host/port 默认值和显式值；
- SDK 未安装不产生隐式网络连接；
- 成功、异常、超时路径均关闭 context；
- K 线分页、空页、重复 page key、游标不前进、最大页数；
- quota preflight 和 quota exhausted；
- snapshot 批量拆分；
- 各 endpoint 的声明性分页终止值、重复游标和不前进游标；不得将某一接口的 `next_key=-1` 泛化到全部 F10 接口；
- retryable/non-retryable 错误分类；
- timezone conversion 和 DST；
- raw/qfq/hfq、session、extended-time 和 dataset version 的任意合法组合不覆盖同一 artifact；
- currency/field_id/period 映射；
- raw response redaction；
- offline fixture 与可选 live quote-only smoke test 分离。

### 12.3 `tests/skills/research/market_analysis/`

- quote scan 收益、波动率、流动性和估值计算；
- dividend announce/ex/record/pay 顺序和币种；
- parity 比例、FX、交易日和市场收盘时点；
- sector window 计算和 universe as-of；
- consensus snapshot 与 trajectory 状态区分；
- Insider open-market/option/gift 分类；
- HK holding change 不被转换为 Insider；
- unsupported 字段和 partial status 正确渲染；
- 每个结果可由 fixture + manifest 重建。

### 12.4 `tests/strategies/cross_sectional/us_hk/`

- 显式 universe，不从当前成分回填历史；
- HK/US 非同步交易日；
- 纽约 DST 和香港交易时段；
- 复权/不复权策略输入隔离；
- rolling、lag、label horizon 无 look-ahead；
- 只产生 `StrategyResult.target_weights`，不导入交易 API；
- stop/skip/unsupported 数据不会静默变成 0 权重；
- 跨币种策略明确 FX 和决策时点。

### 12.5 `tests/integration/`

- mock Futu → normalize → Parquet → read → research → report；
- Futu 不可用时使用 last-known-good，并标记 stale；
- stale 超过 TTL 时严格模式 fail closed；
- staging 失败不会破坏 current snapshot；
- 报告生成失败不会删除上一版本；
- report catalog 只指向完整且 hash 通过的 artifact；
- SDK spy 证明没有创建交易 context、调用交易函数或触及 `OpenQuoteContext` 的非 allowlist 写方法；
- quota、OpenD restart、分页中断、单标的失败、批量部分失败。

### 12.6 `tests/policy/`

- 仅在 research package 范围内静态禁止交易 context/import/call、`subprocess` 与动态绕过；不得误扫已有 `.agents/skills/futuapi` 交易 CLI；
- secret scanner 覆盖源码、fixture、报告、stdout/stderr；
- `.env`、token、API key、账户 ID 不进入 Git；
- OpenD 默认 loopback；
- live quote-only 模式必须显式 opt-in；
- 依赖许可证、第三方数据授权和引用 URL 有清单；
- 生成 SBOM/THIRD_PARTY_NOTICES；
- 上游仓库 License 不一致时阻止自动 vendoring。

### 12.7 `tests/regression/`

- 固定 HK/US fixture hash；
- 固定 symbol mapping 和 normalized output；
- 固定 report bundle 文件清单和 manifest hash；
- 固定回测成本、lag、OOS 指标；
- 负向样例：乱序、重复 bar、错误复权、公告前数据、过期快照、错误币种、缺失 calendar；
- 固定失败降级和 rollback 行为。

## 13. 可观测性与运维最低要求

结构化日志字段：

```text
run_id
request_id
snapshot_id
provider
capability
market
canonical_symbol
provider_symbol
endpoint
page/page_key
attempt
latency_ms
sdk_return_code
error_class
quota_before/after
cache_hit
cache_age
coverage_ratio
stale
publish_status
```

指标：

- OpenD readiness/error rate；
- 各 API 延迟、重试次数和失败率；
- quota 使用/剩余；
- HK/US 每市场、每标的覆盖率；
- stale snapshot age；
- partial response 数量；
- report 生成成功率；
- rollback 次数；
- provenance/hash/PIT 校验失败次数；
- unsupported capability 次数。

不得记录：

- 密码、token、API key；
- 完整账户 ID；
- OpenD 登录信息；
- 原始认证响应；
- 未脱敏的完整 Futu payload。

## 14. Go/No-Go 门禁

### 允许进入研究报告

- 有 provider、snapshot、retrieved_at、coverage 和 schema；
- 观察时间、币种、市场和 session 清晰；
- 缺失字段和能力降级可见；
- 报告可离线重建；
- 使用的旧快照明确标记 stale。

### 允许进入历史回测

除以上条件外，还必须：

- bars 有 `bar_available_at_utc`，事件/财务/FX 有可验证的 `available_at_utc`；
- 满足所有 `available_at_utc <= decision_time_utc`，并在下一可交易 bar 或明确安全 lag 执行；
- 有历史 universe/as-of；
- raw 价格或当时可见的版本化复权/公司行动快照；当前 QFQ/HFQ 序列不得直接通过严格 PIT；
- 有可重建的 FX 和币种转换；
- 有明确的 execution time、calendar、lag 和交易成本；
- 通过 sealed OOS/PIT/integration tests。

### 阻止发布的条件

- 当前快照被用于历史数据；
- 财务值只有报告期没有可用时间；
- raw/qfq/hfq、session、extended-time 或 dataset version 混在一个 dataset；
- 港股股东变化被标记为 Insider Trade；
- Futu quota/权限错误被静默转换为“无数据”；
- 报告缺少 provenance/manifest；
- staging 失败破坏 last-known-good；
- research package 范围内存在交易 API 导入、调用、动态绕过或 quote-side 写操作；
- 第三方资料没有来源和授权状态。

## 15. 首批实现组件清单

> 实际依赖顺序和门禁以第 24 节为准；下列组件按该顺序列出。

1. **冻结 canonical symbol 和 provider symbol 规则**，补齐 HK/US/ADR/alias 测试。
2. **建立 ingest contracts/errors/provenance/cache/rate_limit**。
3. **重构 Futu 历史 K 线数据集身份**，拆分 raw/qfq/hfq/session，并修复时区处理。
4. **扩展 DataManager/ArtifactStore manifest**，保存 source、request params、hash、coverage 和版本。
5. **实现 LocalProvider fixture replay**，确保无 OpenD 也能测试全链路。
6. **实现 FutuMarketProvider**：snapshot、valuation、plate 和历史 bars。
7. **实现 `run_quote_scan`**，完成第一个港美股报告 vertical slice。
8. **实现 FutuEventsProvider**：dividend、holding changes、US insider。
9. **先接入 FX fixture/provider**，定义汇率方向、时点与最大陈旧度，再做 parity。
10. **实现 dividend、sector、parity、US insider 四个 workflow**。
11. **实现 FutuFundamentalsProvider/FutuResearchProvider**，先做描述性财务和共识快照。
12. **实现基础 dossier**，所有缺口显式 `unsupported`。
13. **积累 consensus snapshots**，再评估 revision radar；接入外部 evidence provider 后再做 memory analyzer。
14. **补齐报告原子发布、运维指标、SBOM、许可证和安全策略**。

## 16. 最终建议

本方案建议将 9 个上游项目视为“研究规则和报告资产”，而不是可直接安装的 9 个 Python 包。QuantSpace 应以 Futu 为主数据源，以 provider-neutral contract 为稳定边界，先完成可验证的港美股 EOD/报告闭环，再逐步增加非 OHLCV 研究数据。

最终交付目标应表述为：

> **在 QuantSpace 中构建 Futu-first 的港美股只读研究工作流，兼容上游 9 个 Skill 的研究意图；对 Futu 不覆盖的历史共识、港股 Insider、FX 历史序列和产业链资料采用显式降级或多源 provider，并严格隔离报告、因子、回测和交易执行。**

在完成 P0 数据契约和安全门禁前，不应把 Futu 港美股基本面/事件数据直接送入现有 `VectorBacktester`。在 P2 quote scan 和 P3 事件工作流完成后，项目才具备可持续扩展其余 Skill 的可靠基础。

## 17. 二次审查结论：当前是“半可插拔”，不是“完全可插拔”

前述方案已经正确地提出了 provider-neutral contract、只读边界、PIT、provenance 和 artifact manifest，但这些内容仍主要是设计约定。经过对现有目录、Futu 适配器、存储接口和 9 个上游仓库的再次核对，当前状态应准确表述为：

> **provider 可替换，Skill 半可插拔；完成本节所列的正式插件协议和测试门禁后，才可宣称 Skill 可独立增删。**

“可插拔”必须同时满足以下四个可验收条件：

| 维度 | 必须满足的条件 |
|---|---|
| 代码独立 | 新增或删除一个 Skill，不修改其他 Skill 的源码，不修改中央 dispatcher；Skill 不导入具体 Futu 类、交易 API 或 `strategies/`。 |
| 数据独立 | 原始 provider 数据、规范化 artifact、报告和 `current` 指针按 provider/Skill/dataset 隔离，不能互相覆盖。 |
| 运行独立 | Skill 通过 manifest 自动发现；可选依赖按 Skill 隔离；缺少能力时返回 `partial/unsupported/blocked`，不能返回伪造的空成功结果。 |
| 版本独立 | 输入输出 contract、artifact schema、provider adapter 和数据快照都可独立版本化；不兼容时 fail-closed。 |

因此，“把 9 个目录放进项目”不是交付标准。交付标准是：每个插件都能被 registry 验证、单独运行、单独产出 artifact、单独删除；删除后无依赖插件仍通过导入和离线 fixture 测试，直接或间接依赖者必须带 DAG 原因返回 `blocked`。

## 18. 正式插件协议：`SkillManifest + SkillRegistry + DataSourcePlan`

### 18.1 `SkillManifest` 是新增和删除 Skill 的唯一注册入口

建议新增：

```text
skills/research/market_analysis/
  contracts.py
  protocols.py
  registry.py
  planner.py
  plugins/
    hk_us_quote_scan/            # Python-safe module_name
      manifest.py                 # stable skill_id="hk-us-quote-scan"
      workflow.py
      schemas.py
      adapters.py
    ...
```

每个 Skill 必须提供一个可静态检查的 manifest，至少包含：

```python
SkillManifest(
    skill_id="hk-us-quote-scan",       # stable public/artifact identity
    module_name="hk_us_quote_scan",    # Python package/directory name
    skill_version="1.0.0",
    entrypoint="skills.research.market_analysis.plugins.hk_us_quote_scan.workflow:run",
    request_contract="market-analysis.request@1",
    result_contract="market-analysis.result@1",
    required_capabilities=("quote_snapshot", "history_ohlcv"),
    required_artifacts=(),
    produced_artifacts=("hk-us-quote-scan.report",),
    supported_markets=("HK", "US"),
    optional_dependencies=(),
    side_effects="read_only",
)
```

`SkillRegistry` 只负责发现、校验和按 `skill_id` 调度，不包含任何具体分析逻辑。它必须执行：

1. `skill_id` 唯一性检查、入口存在性检查和 manifest schema 校验。
2. capability、artifact 生产者/消费者和版本范围校验。
3. 依赖图拓扑排序和循环依赖拒绝。
4. `side_effects != read_only` 的默认拒绝；研究工作流不得自动获得交易权限。
5. 删除或禁用 Skill 后从 registry 中消失，但不得删除历史 artifact。

新增 Skill 的正常路径应是“新增一个 plugin 目录和测试，registry 自动发现”，而不是在中央 dispatcher 中增加一个 `if skill_name == ...` 分支。

### 18.2 provider 必须按能力注入，不建立一个 Futu 共享单体

研究 Skill 只依赖协议，不依赖 `FutuClient` 具体实现。建议按能力拆分：

```text
QuoteProvider       -> snapshot、历史 OHLCV、交易日/市场状态（按覆盖范围）
FinancialProvider   -> 三表、估值、公司概况
DividendProvider    -> 股息历史、股息日历、公司行动
ConsensusProvider   -> 当前评级/目标价/预测快照
InsiderProvider     -> 内部人交易或持股变动（区分语义）
FxProvider          -> 即期/历史汇率和时间序列
EvidenceProvider    -> SEC、IR、行业、产业链和新闻证据
```

`FutuMarketProvider`、`FutuEventsProvider` 等是这些协议的实现，不应被所有 Skill 共同导入为一个包含全部能力的 facade。每个 provider 方法必须返回统一的 `ProviderResult[T]`，其中包含 `data`、`status`、`coverage`、`provenance` 和 `error`；`permission_denied`、`quota_exhausted`、`not_supported`、`no_data` 和 `request_failed` 必须可区分。

### 18.3 单一 `provider` 字符串改为 `DataSourcePlan`

`WorkflowRequest` 必须使用 `DataSourcePlan`，而不是单一 provider 字符串；跨上市价差需要 Futu + FX，memory analyzer 需要 Futu + SEC/IR：

```text
DataSourcePlan:
  quote:
    provider_id: futu
    adapter_version: futu-quote@1
  fx:
    provider_id: fx-provider
    adapter_version: fx@1
  evidence:
    provider_id: sec-ir-evidence
    adapter_version: sec-ir@1
```

每个字段或证据项都要记录 `provider_id`、`adapter_version`、`retrieved_at_utc`、timezone-aware `as_of_utc`、`published_at`、`available_at_utc` 和 fallback/缺口原因。只有字段语义完全相容时才允许 fallback；不能用“另一个市场的近似字段”默默填充。

### 18.4 artifact 依赖必须形成可校验的 DAG

仅有 `parent_artifacts` 不够。manifest 需要声明：

```text
requires_artifacts:
  - kind: consensus.snapshot
    producer: hk-us-consensus-radar
    version: ">=1,<2"
    optional: false
produces_artifacts:
  - kind: consensus.revision-report
    schema: market-analysis.consensus-revision@1
```

registry 必须能回答“删除某 Skill 会影响哪些下游 artifact”，并在运行前拒绝缺失、循环或版本不满足的依赖。`consensus-revision-radar` 对历史 consensus snapshot 的依赖、`stock-memory-analyzer-usa` 对 evidence provider 的依赖都必须显式注册。

## 19. 目录、依赖方向与隔离规则（目标态）

### 19.1 目标目录

```text
skills/
  ingest/
    contracts.py                 # InstrumentId、ProviderResult、Provenance
    protocols.py                 # 能力协议，不含具体 Futu SDK
    futu.py                      # Futu/OpenD 传输、分页、错误与只读保护
    providers/                   # futu_quote、futu_financial、futu_events...
    fake.py                      # 离线 fixture provider
  store/
    data_manager.py              # 既有 OHLCV 存储
    research_store.py            # 非 OHLCV artifact、manifest、质量状态
    cache.py                     # request hash、TTL、原始响应缓存
  research/
    market_analysis/
      contracts.py
      protocols.py
      registry.py
      planner.py
      plugins/<module_name>/     # Python-safe module；manifest 映射稳定 skill_id
  report/
    contracts.py                 # pure report/provenance contract
    research_report.py           # runtime rendering and bundle publishing

strategies/
  cross_sectional/
    us_hk/                       # 仅保留真正生成 Factor/target_weights 的策略

scripts/
  run_market_analysis.py         # 只做参数、registry、provider plan、报告输出编排

tests/
  contracts/                     # registry、版本、artifact DAG、PIT/OOS、安全策略
  policy/                        # import graph、research-scope 交易 API denylist、可选依赖隔离
  skills/research/market_analysis/<module_name>/
                                  # 每个 Skill 的纯函数和 fixture 测试
  strategies/cross_sectional/us_hk/
  integration/                   # FakeProvider 全链路；真实 OpenD 测试默认跳过
```

9 个能力必须位于 `skills/research/market_analysis/plugins/<module_name>/`；它们多数是报告型研究能力，不是策略。`strategies/cross_sectional/us_hk/` 只接收已验证的规范化特征并生成权重；研究报告不得反向依赖策略目录。

### 19.2 强制依赖方向

```text
provider implementation -> ingest protocols/contracts
market-analysis plugin  -> ingest protocols + store contracts + report contracts
workflow runner         -> SkillRegistry + DataSourcePlan
strategy                -> provider-neutral feature/selection contracts
scripts                 -> runner only
```

必须禁止：

- `skills/research/market_analysis/plugins/*` 直接导入 `futu` SDK 或 `.agents/skills/futuapi` CLI。
- 一个 Skill 直接导入另一个 Skill 的实现模块；跨 Skill 只能消费版本化 artifact。
- 任意 `skills/` 模块导入 `strategies/`。
- workflow 通过 `subprocess` 调用 Futu CLI。
- import 时读取环境变量、创建 OpenD 连接、执行网络请求或初始化交易上下文；P0 必须先把现有报告类型抽为纯 contract，并将 workspace 解析和渲染延迟到运行期。

外部上游代码如暂时不能重写，应作为隔离 sidecar 或离线移植输入，不能把其供应商依赖和全局 import 污染带入核心包。默认优先用本项目自己的 provider-neutral 实现重建研究逻辑，不直接 vendor 上游仓库。

## 20. Futu 兼容化的硬性修订

本节是进入 P0/P1 前的阻断项。当前 `skills/ingest/futu.py` 可作为“历史 K 线 OHLCV、只读抓取 adapter”，不能在未扩展前称为完整 Futu provider。

| 问题 | 必须的修订 | 失败时的处理 |
|---|---|---|
| 复权/会话数据覆盖 | 使用完整结构化 dataset key：provider、frequency、`autype`、session、extended-time、calendar、schema/content 版本；禁止不同合法组合写同一文件，也不得创建 Futu 不支持的组合。 | 写入前冲突或非法组合即拒绝。 |
| provenance 丢失 | 持久化 provider、API 方法、原始/规范 symbol、参数、源时区、抓取 UTC 时间、SDK/OpenD 版本、分页数、行数、完整性、错误码和 quota 状态。 | 缺 provenance 的 artifact 不可发布。 |
| 时区静默丢弃 | `eob` 固定为交易所本地墙上时间且为 tz-naive；`source_timezone`、UTC-aware `bar_start/end_utc` 与 `bar_available_at_utc` 必须保存并相互校验；跨市场比较只使用 UTC。 | 缺源时区或 UTC 边界时阻断跨市场分析。 |
| session 误用 | `RTH/ETH/ALL` 与 `extended_time` 只在 Futu 支持的美股分时（≤60m）组合中开放；非美股、日线、非法周期和 `OVERNIGHT` 组合直接拒绝。 | 返回参数错误，不降级为空数据。 |
| 分页截断 | opaque `page_req_key` 只能由 provider 传递；达到 `max_pages` 仍有下一页时必须 `complete=false`，不能作为完整历史序列发布。 | 回测/因子输入拒绝 partial 数据。 |
| 分页去重过宽 | 仅在同一 dataset key 内按 `(native_code, bar_end_utc, session_scope, extended_time)` 识别分页重叠；无法证明是重叠时记录异常并拒绝静默覆盖。 | 质量状态为 `invalid` 或 `needs_review`。 |
| symbol 信息损失 | 同时保存 `native_symbol`（如 `HK.00700`、`US.AAPL`）和 canonical `InstrumentId`；Futu US alias 只能经有效期 instrument master 解析 venue，不能无损宣称为 NASDAQ。 | alias 无法消歧或 round-trip 不一致即拒绝。 |
| 期货边界模糊 | 本项目港美股 Skill 的第一版只支持股票/ETF/指数等明确列入 allowlist 的 quote 标的；期货若要支持，另建 futures adapter 和契约。 | 未实现的 futures namespace 明确 `not_supported`。 |
| 严格 PIT 复权 | 当前抓取的 QFQ/HFQ K 线或 `get_rehab` 因子可能包含未来公司行动；严格 PIT 只能用 raw bars + 当时可见的事件，或版本化 adjustment snapshot。 | 无可见复权快照时拒绝进入严格回测。 |
| QuoteContext 写操作 | `OpenQuoteContext` 也存在自选股/提醒等非研究写方法；provider 只能调用 SDK 方法 allowlist。 | 非 allowlist 调用被 policy/SDK spy 拒绝。 |
| 权限/额度混同 | quota 检查只能是 advisory；权限不足、额度不足、历史范围不足、请求失败和真正无数据必须按 endpoint × market × entitlement 分型。 | 不能把空 DataFrame 解释为“没有数据”。 |

官方接口边界应以以下文档为准，并在 provider contract 测试中固化关键语义：

- [历史 K 线](https://openapi.futunn.com/futu-api-doc/en/quote/request-history-kline.html)：分页、周期、复权、历史范围和 session 参数。
- [历史 K 线额度](https://openapi.futunn.com/futu-api-doc/en/quote/get-history-kl-quota.html)：额度是账号/权限相关状态，不是请求成功保证。
- [行情快照](https://openapi.futunn.com/futu-api-doc/en/quote/get-market-snapshot.html)：实时快照与历史 K 线是不同能力和限频边界。
- [财务报表](https://openapi.futunn.com/futu-api-doc/en/quote/get-financials-statements.html) 与 [估值详情](https://openapi.futunn.com/futu-api-doc/en/quote/get-valuation-detail.html)：报告期、发布日期和 PIT 语义不能混同。
- [研究员共识](https://openapi.futunn.com/futu-api-doc/en/quote/get-research-analyst-consensus.html)：当前聚合快照不等于历史修订序列。
- [股息](https://openapi.futunn.com/futu-api-doc/en/quote/get-corporate-actions-dividends.html) 与 [股息日历](https://openapi.futunn.com/futu-api-doc/en/quote/get-dividend-calendar.html)：事件日期和币种需要规范化。
- [内部人交易](https://openapi.futunn.com/futu-api-doc/en/quote/get-insider-trade-list.html)：覆盖市场和语义有限，不能把股东持股变动直接当作 insider transaction。
- [Futu Quote API 总览](https://openapi.futunn.com/futu-api-doc/en/quote/overview.html)：不同接口的权限、订阅和市场覆盖必须逐项声明。

## 21. 9 个 Skill 的修订后交付分层

每个 Skill 都独立发现、启用/禁用、测试和发布；本仓库不为这 9 个目录引入单独 Python 包安装机制。“分层”只表示数据能力和研究结论的覆盖范围，不改变模块边界。

| Skill | 首版状态 | 独立输入/输出 | 关键限制 |
|---|---|---|---|
| `skill-hk-us-quote-scan` | **P2 可交付** | quote snapshot + history OHLCV → quote-scan artifact/report | 最适合作为第一个 vertical slice；复权、流动性、估值字段要分来源。 |
| `skill-hk-us-dividend-events` | **P3 部分可交付** | dividend/corporate-action → event calendar/report | 需要统一 announce/ex/pay 日期、币种和时区；缺失事件不得伪造。 |
| `skill-cross-listing-parity` | **P3 受限可交付** | Futu quote + FX provider + share ratio → parity observation | 只输出观察价差；不输出可执行套利，不建模借券、税费、结算和资本管制。 |
| `skill-us-sector-rotation` | **P3 受限可交付** | 明确 US universe + sector mapping + returns → rotation report/optional feature | 若没有 as-of sector membership，只能声明固定 universe，不得宣称历史无幸存者偏差。 |
| `skill-hk-us-insider-radar` | **P3 US 优先** | US insider transaction 或 HK holding-change → separate event artifacts | US insider 与 HK 持股变动分开命名、分开 schema；不能合并成一个指标。 |
| `skill-hk-stock-dossier` | **P4 当前快照** | quote + financial + dividend + ownership/consensus → dossier report | 完整 PIT 基本面和全部 HK 事件不承诺；每个缺口显示 `unsupported`。 |
| `skill-hk-us-consensus-radar` | **P4 当前快照** | current rating/target/estimate + quote → consensus radar | 可做当前聚合快照；没有历史抓取档案就不能做修订趋势。 |
| `skill-hk-us-consensus-revision-radar` | **P5 受限/阻断** | versioned consensus snapshots → revision trajectory | Futu-only 不能即时补出历史；先积累带 `published_at/as_of_utc/available_at_utc` 的 snapshot archive。 |
| `skill-stock-memory-analyzer-usa` | **P5 sidecar** | market/fundamental + SEC/IR/industry evidence → evidence-linked report | 不应伪装为 Futu-only；固定股票集合和外部证据 provider 必须显式配置。 |

这里的“独立”意味着 Skill 可以独立运行和移除，不意味着每个 Skill 都只用一个 provider。多源依赖应通过 `DataSourcePlan` 和 artifact DAG 隔离。

## 22. 增删 Skill、替换 provider 的操作协议

### 22.1 新增一个 Skill

只允许新增以下内容：

1. `plugins/<module_name>/manifest.py`、workflow、schemas、纯分析函数和本 Skill 的可选依赖；manifest 显式声明稳定的 `skill_id` 与 Python-safe `module_name`。
2. `tests/skills/research/market_analysis/<module_name>/`、registry contract fixture 和至少一个 FakeProvider 集成 fixture。
3. Skill 文档、能力矩阵和 artifact schema。

新增不应修改：

- 其他 Skill 的源码和测试；
- 中央 dispatcher 的分支；
- Futu provider 的业务逻辑；
- 全局 `current` 指针；
- 其他 Skill 的 artifact 和报告目录。

### 22.2 删除或禁用一个 Skill

删除 manifest、plugin 代码、专属可选依赖、公开导出和文档注册；registry 重新扫描后该 Skill 不可运行。历史 raw/artifact/report 默认保留，标注 `producer_status=removed`，不做破坏性删除。若仍有下游强依赖，删除操作必须先报告影响 DAG 并阻止发布，而不是让下游悄悄读旧缓存。

验收方式是对每个 9 个 Skill 做一次 N-1 测试：逐个移除后，无依赖的其余插件仍能导入、通过离线 fixture、生成独立 artifact；直接或间接依赖者必须以 DAG 原因返回 `blocked`，而非假装成功或读取旧缓存。没有残留 import、CLI、registry 或路径引用。

### 22.3 替换 Futu provider

用 FakeProvider、LocalProvider 或另一个合规 provider 替换 `DataSourcePlan` 中的 provider binding。若 canonical input contract 和 provenance 语义不变，Skill 代码不应变更；provider-native raw 只留在 `data/raw/providers/<provider>/`。任何字段语义变化必须升级 contract，而不是在 adapter 中偷偷转换。

### 22.4 能力降级

降级状态使用固定枚举：

```text
available | partial | unsupported | blocked | stale | failed
```

`partial` 必须带 `missing_fields` 和 `reason`；`unsupported` 不得转为空字符串、零值或空 DataFrame；`stale` 不得用于需要实时或 PIT 的任务；`blocked` 不得继续进入回测和生产报告。

## 23. 版本、命名空间与发布一致性

每个可复用 contract 和 artifact manifest 至少包含：

```text
contract_id
contract_version
producer_version
min_reader_version
max_reader_version
schema_hash
provider_id
adapter_version
dataset_id
query_hash
content_hash
provenance
```

兼容规则：

- major 版本不兼容时 fail-closed；
- minor/patch 只有在字段兼容测试通过时才可读取；
- N-1 reader 必须能读取当前受支持的旧 artifact；N+1 artifact 未经 migration 不得被旧 reader 读取；
- 任何 schema migration 都要生成新 artifact，不覆盖旧 artifact；
- cache 命中前先检查 contract、provider adapter、参数、时区、复权、session 和数据集版本；
- `current` 不是全局指针，至少按 `(skill_id, artifact_type, query_hash)` 隔离。

建议存储边界如下：

```text
data/raw/providers/<provider>/<capability>/<request_hash>.json
data/market/<provider>/<frequency>/<adjustment>/<session>/<extended-time>/<dataset_id>/<symbol>.parquet
data/artifacts/<skill_id>/<artifact_type>/<artifact_id>/data.*
data/artifacts/<skill_id>/<artifact_type>/<artifact_id>/manifest.json
reports/<skill_id>/<skill_version>/<run_id>/index.html
```

正式报告为 HTML-only；manifest、参数和指标等机器数据属于 artifact 或兼容性
sidecar，不是另一种正式报告格式。

现有 `data/market/{frequency}/{symbol}.parquet` 只能保留为 legacy 读取兼容面；新写入必须使用完整结构化 key，不能再以 `frequency` 字符串承载 raw/qfq/hfq、session、extended-time 和 dataset version。`output_namespace` 必须限制为安全字符集、禁止路径穿越、禁止保留字和跨 Skill 冲突。

## 24. 修订后的构建阶段和硬门禁

### P0：合同和插件内核（无网络）

交付 `SkillManifest`、registry、capability status、DataSourcePlan、artifact dependency DAG、版本规则、命名空间验证和 import policy；先抽取无副作用的 report/provenance contract 与版本化 report manifest，并同步更新相关 `SKILL.md`、README 和公开 API/测试文档。此阶段不实现 9 个研究逻辑。

**门禁**：重复 `skill_id`、缺入口、`skill_id`/`module_name` 映射冲突、循环依赖、未知 schema、非法 namespace，以及 research package 内直接 Futu import、交易 API import、动态绕过均能被测试拒绝。

### P1：Futu 数据平面正确性

修正历史 K 线的复权键、时区/provenance、session 校验、分页完整性、去重、quota/权限错误和股票/ETF/指数 allowlist；将 quote、financial、dividend、consensus、insider 等 provider 按协议拆分。用 Fake SDK 覆盖异常路径。

**门禁**：不连接 OpenD 也能完成 provider contract 测试；所有 partial、permission、quota、no-data、历史范围不足和 not-supported 状态可区分；完整 dataset key 的任意合法组合互不覆盖；严格 PIT 下当前 QFQ/HFQ 被拒绝，除非存在当时可见的复权快照。

### P2：Quote Scan 最小垂直闭环

固定 `US.AAPL` 与 `HKEX.00700` fixture，完成：

```text
Fake/Futu provider
  -> InstrumentId + MarketSnapshot + OHLCV
  -> hk-us-quote-scan
  -> provider-neutral artifact + manifest
  -> HTML-only report
```

**门禁**：一次离线命令可复现；报告中的每个数字都能反查到 artifact、query hash 和 provenance；不需要修改中央 dispatcher。

### P3：独立交付 dividend/parity/sector/US insider

每个 Skill 单独 PR、单独测试和单独 artifact namespace。parity 增加 FX provider；sector 明确固定 universe/as-of 限制；insider 将 US insider 与 HK holding change 分开。

**门禁**：任意移除一个 Skill 后无依赖插件的 N-1 测试通过、依赖插件按 DAG 返回 `blocked`；FakeProvider 替换 Futu 后流程不变；research scope 内无交易 API、无 quote-side 写操作、无空成功、无隐式 provider fallback。

### P4：dossier 和当前 consensus

在字段级 provenance、timezone-aware `as_of_utc`、`published_at`、`available_at_utc`、report period 和缺口状态齐全后，再实现 dossier 和当前 consensus radar。财务报告期不得当作发布日期，当前共识不得当作历史共识。

**门禁**：PIT 检查、报告快照 manifest、字段缺失展示和跨市场币种/时区测试通过。

### P5：revision radar 与 memory analyzer sidecar

先运行 snapshot archive，积累版本化共识快照；另行接入 SEC/IR/行业 evidence provider。若没有历史 snapshot 或证据 provenance，两个 Skill 保持 `blocked/partial`，不交付虚假的完整实现。

**门禁**：历史回放只能使用当时已发布数据；证据项有来源和发布日期；删除 evidence provider 后 memory analyzer 正确阻断，不影响其他 8 个 Skill。

### P6：发布与运维硬化

补齐原子发布、current 指针、崩溃恢复、TTL、重试/退避、OpenD 版本矩阵、许可证/SBOM、secret scan、运行指标和回滚。

**总 Go/No-Go**：contract、policy、unit、integration、regression 全部通过；任何把权限/额度当无数据、把 partial 当完整、混用完整 dataset key 的任一维度、丢失 provenance、覆盖 current、在 research scope 导入/调用交易 API 或 quote-side 写操作、绕过 strict PIT 复权门禁，或 schema hash 不一致的情况均为 No-Go。

## 25. 最小测试清单（必须新增到实施任务）

### Plugin 与依赖边界

- registry 自动发现、重复 `skill_id`、缺失入口、非法 manifest 和循环 artifact 依赖。
- 新增 Skill 不修改中央 dispatcher 的 contract test。
- 删除任意一个 Skill 后无依赖插件仍可导入、fixture 运行和报告发布；依赖插件必须带 DAG 原因 `blocked`。
- `skills/` 不反向导入 `strategies/`；research plugin 不导入具体 Futu 实现、Futu CLI、交易上下文或 `subprocess`。
- import 时不读取环境、不建连接、不联网；报告 contract 也必须无副作用；可选依赖未安装时其他 Skill 仍能导入。

### Futu 数据平面

- >1000 根数据的多页分页、opaque `page_req_key`、中途错误和 max-pages partial。
- `none/forward/backward`、session、extended-time 与 dataset version 的合法数据集互不覆盖；provenance 真实落盘并可从 DataManager 读取。
- HK/US 源时区、美国 DST、`bar_available_at_utc`、仅美股 ≤60m 的 session 合法性与 `OVERNIGHT` 拒绝。
- `US.AAPL` 的 native/canonical identity round-trip（不由 alias 推断 venue）；股票 allowlist 与 futures 明确拒绝/独立 adapter。
- quota、权限、历史范围不足、请求失败、无数据的结构化区分。
- OpenD 未启动、版本不兼容、断线、重连、非重试错误、限流/退避行为。

### Artifact、PIT 与发布

- producer/consumer contract 的 N-1/N/N+1 兼容矩阵；未知字段和未知 major 版本 fail-closed。
- artifact content hash、schema hash、query hash 不一致时拒绝发布。
- 同 hash 并发写入收敛；不同 hash 不覆盖；staging 失败不破坏当前版本；崩溃恢复后 catalog 一致。
- cache 不泄漏 OOS、未来发布日期、未来复权因子或历史时点不可见数据；报告同时携带 `as_of_utc`、`published_at`、`available_at_utc` 和完整 provenance。
- 真实 OpenD 集成测试默认 opt-in，并在 research package 范围内静态拒绝任何交易、账户、持仓、订单、解锁、quote-side 写操作或动态绕过。

## 26. 最终构建结论

### 可行性

本项目完全可以以 Futu 为港美股主行情/证券数据源，接入并兼容 9 个上游 Skill 的研究意图；最稳妥的落地方式是“本地重建研究逻辑 + provider-neutral contract + Futu 只读 adapter + 显式多源 sidecar”。

### 合理性

把 9 个能力放在独立 plugin 目录、由 registry 自动发现，以 artifact DAG 和版本化 contract 连接，是合理且可长期扩展的架构。它允许拆除或增加单个 Skill，而不改变其他 Skill、Futu provider 和整体 runner；但这个结论只对完成 P0/P1 及其测试门禁后的目标态成立。

### 当前不能承诺的内容

- Futu-only 完整复现历史 consensus revision radar。
- Futu-only 完整复现港股 insider transaction、SEC/IR/产业链证据和历史 FX。
- 用当前共识、未来修订或当前 sector membership 回填历史回测。
- 9 个 Skill 现在已经可以无影响地随意删除或增加。

### 推荐的实施顺序

```text
1. SkillManifest/Registry/Artifact DAG/Import policy
2. Futu 数据正确性：复权、时区、分页、provenance、权限
3. quote-scan vertical slice
4. FX fixture/provider + dividend + parity + sector + US insider
5. dossier + current consensus
6. consensus snapshot archive
7. revision radar + evidence sidecar memory analyzer
8. 发布、回滚、SBOM、许可证和运维门禁
```

在此修订方案下，最终交付物不是“复制 9 个上游仓库”，而是 9 个拥有独立 manifest、独立测试、独立 artifact namespace 和明确能力状态的研究插件。其中，Futu 是默认证券数据 provider，但不是所有研究证据的唯一来源；不能由 Futu 提供的内容必须显式降级或通过独立 provider 补齐。
