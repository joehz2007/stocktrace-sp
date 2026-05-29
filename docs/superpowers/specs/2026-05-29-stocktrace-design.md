# StockTrace 设计文档

> 日期: 2026-05-29
> 状态: 已批准,待实现
> 需求来源: `docs/requirements.md`

## 1. 目标与范围

StockTrace 是面向中国 A 股的本地轻量跟踪系统:维护股票池、定时采集行情与低频指标、基于快照差分生成事件型信号、邮件提醒,并通过 Flask Web 与 CLI 查看结果。单机研究工具,**不含**交易、账户、权限、云端协作、历史回测、完整财务因子体系。

功能范围以 `docs/requirements.md` 为准,本文档是其工程化设计与实现约束。

## 2. 架构总览(分层 + 适配器)

```
入口层   app/cli.py   app/web.py   app/scheduler.py
            │            │              │
            └────────────┴──────────────┘
                         ▼
业务层   app/services/*   (编排 + 纯逻辑,不直接碰 HTTP)
            │                        │
            ▼                        ▼
仓储层  app/db/repository.py    适配器层 app/sources/*  (唯一碰 HTTP)
            │                        │
        SQLite (data/)         腾讯/东财/新浪/百度
```

**核心原则**:三个入口只调 service 层;service 通过构造注入获得仓储与适配器;脆弱的外部 HTTP 收敛进可替换、可录制夹具的适配器;易错且口径关键的纯逻辑(指标、信号差分、解析、去重)独立成无 IO 单元,便于严格 TDD。

### 2.1 包结构

```
stocktrace-sp/
  app/
    __init__.py
    config.py            # 邮件配置(env EMAIL_* > data/email_config.json)、HOST/PORT/data 路径
    cli.py               # python -m app.cli
    web.py               # python -m app.web  (Flask, 服务端拼 HTML)
    scheduler.py         # python -m app.scheduler (APScheduler)
    db/
      connection.py      # SQLite 连接、data/ 目录定位、初始化
      schema.sql         # 建表 DDL
      repository.py      # 纯数据访问(增查),无业务逻辑
    sources/
      base.py            # 适配器协议(Protocol) + HTTP 工具(requests 封装、超时、UA)
      tencent.py         # smartbox 搜索 / 实时行情 / 沪深指数
      eastmoney.py       # 分红 / 日K / 120日资金流 / 涨跌家数
      sina.py            # 财报三表
      baidu.py           # 分钟级资金流
    services/
      stock_pool.py      # 解析 + 分隔符 + 腾讯搜索 + 后缀回退 + 代码标准化
      snapshot.py        # 盘中快照编排
      metrics.py         # 纯函数:ROE/股息率TTM/动态PE/资产负债率/MA偏离/趋势文案
      signals.py         # 纯函数:事件差分
      macro.py           # 沪深宏观快照同步
      low_freq.py        # 低频刷新编排
      backfill.py        # regen-signals + backfill
      notify.py          # 未通知新信号→发送→写日志→成功去重
    email_sender.py      # SMTP 发送
  tests/                 # pytest,核心逻辑重点覆盖
    fixtures/            # 录制的真实响应(json/html),供适配器解析单测
  docs/                  # requirements.md / go.txt / superpowers/specs
  data/                  # 运行时 SQLite + email_config.json (gitignore)
  pyproject.toml         # uv 管理,Python 3.12
  Dockerfile
  start.sh               # 容器内同时启动 web(0.0.0.0:5000) 与 scheduler
  .gitignore
```

### 2.2 技术选型

- Python 3.12,**uv** 管理虚拟环境与依赖,`pyproject.toml` 声明。
- 依赖:`Flask`(Web)、`APScheduler`(调度)、`requests`(HTTP)。开发依赖:`pytest`。
- DB:标准库 `sqlite3` + `schema.sql`,不引 ORM。
- 适配器经构造函数注入 service;默认实现走真实 HTTP,测试传假实现。
- Flask 直接字符串拼 HTML,无前端框架(需求强制)。

## 3. 数据模型 (SQLite 表)

| 表 | 用途 | 关键字段 |
|---|---|---|
| `stock` | 股票池 | code(PK), name, added_at |
| `intraday_snapshot` | 盘中快照 | code, name, snapshot_time, price, change_pct, turnover_pct, amount_wan, volume_ratio, pe_static, pe_ttm, pe_dynamic, pe_dynamic_source, pb, market_cap_yi, float_market_cap_yi, dividend_yield_ttm, roe, ma20, ma60, dist_ma20_pct, dist_ma60_pct, trend_status, debt_to_asset_ratio, main_net_in, main_net_in_source |
| `macro_snapshot` | 沪深宏观快照 | market(sh/sz), snapshot_time, index_point, change_point, change_pct, high, low, amount, up_count, down_count, flat_count, total_count |
| `signal` | 事件信号 | code, name, signal_type, level, snapshot_time, detail, created_at |
| `notification_log` | 邮件通知日志 | signal_id, recipient, status(success/fail), error, sent_at |
| `dividend` | 分红历史 | code, report_date, announce_date, pretax_bonus_per10, plan_or_impl |
| `fund_flow` | 日级资金流(120日) | code, trade_date, main_net_in(原始单位:元) |
| `financial` | 财报三表关键项 | code, report_date, net_profit_attr, equity_attr, total_assets, total_liabilities |
| `daily_quote` | 日K | code, trade_date, open, high, low, close, volume, amount |
| `daily_indicator` | 日级指标 | code, trade_date, ma20, ma60, vol_ratio_20, trend_status |
| `valuation_forecast` | 动态PE预测 | code, forecast_eps, forecast_net_profit_yi, source, updated_at |

> 分钟级资金流(百度)为盘中实时取用,不落独立表,直接进 `intraday_snapshot.main_net_in`。

## 4. 数据源适配器

| 适配器 | 数据 | 来源 |
|---|---|---|
| `tencent` | 股票搜索 / 实时行情 / 沪深指数 | 腾讯 smartbox、腾讯财经 |
| `eastmoney` | 分红 / 日K / 120日资金流 / 涨跌家数 | 东方财富 datacenter / K线 / push2(his) / 指数统计 |
| `sina` | 财报三表 | 新浪财经 |
| `baidu` | 分钟级资金流 | 百度股市通 |

`base.py` 定义适配器 `Protocol`(如 `QuoteSource`、`SearchSource` 等),封装 `requests`(超时、UA、重试)。每个适配器方法返回解析后的 dataclass/dict,**不做业务计算**。

## 5. 关键业务逻辑与口径

### 5.1 股票池解析 (`stock_pool`)
- 分隔符:英文逗号、中文逗号、顿号、分号、换行、制表符。
- 解析:优先腾讯 smartbox;失败时若为数字按 6 位代码标准化;名称搜索失败再去掉后缀 `股份/股票/证券/集团/有限` 重试;仍失败返回友好错误。
- 仅支持添加,不支持删除/禁用/分组。批量添加忽略统一自定义名称。

### 5.2 盘中快照 (`snapshot.sync`)
顺序:同步沪深宏观 → 拉腾讯实时行情 → 读本地低频缓存 → `metrics` 计算派生指标 → 主力净流入(优先百度分钟级,失败回落本地日级 `fund_flow` 最近一条) → 落 `intraday_snapshot` → 触发 `signals` → 可选 `notify`。
- 单位:快照内主力净流入统一万元;`fund_flow` 落表保留原始单位元。

### 5.3 指标口径 (`metrics`,纯函数)
- **PE/PB/市值/换手/量比**:直接取腾讯行情字段。
- **动态PE**:`价格/预测EPS`,否则 `总市值(亿)/预测净利润(亿)`;仅本地有 `valuation_forecast` 时可得;写入快照(首页/详情暂不展示)。
- **股息率TTM**(东财近似):近一年报告期(含预案)现金分红总额 / 最近总市值 ×100%。按 `report_date` 窗口统计(非除权日滚动365天);同一报告期取公告日最新一条;`PRETAX_BONUS_RMB` 先由"每10股税前派息"换算为"每股税前派息"。
- **ROE**:最近一期累计归母净利润年化 / 最近一期股东权益 ×100%。年化因子:3月→4,6月→2,9月→4/3,12月→1。
- **资产负债率**:负债合计 / 资产总计 ×100%。
- **MA20/MA60 与趋势**:日级指标算 MA20、MA60、20日量比、趋势文案。趋势规则:多头(价>MA20 且 MA20>MA60)/ 空头(价<MA20 且 MA20<MA60)/ 中性偏强(价>MA60)/ 中性偏弱(价<MA60)。

### 5.4 信号生成 (`signals`,纯函数)
输入"上一条快照 + 当前快照",输出信号列表。
- 普通态:仅"当前有、上一条没有"时生成一次。
- 穿越态:必须比较前后两条。
- 每股第一条快照仅作基线,不生成信号。

| 信号 | 条件 | 级别 | 类型 |
|---|---|---|---|
| 放量上涨 | 10:00 后,量比≥2.0 且涨幅≥+2% | 中 | 普通 |
| 放量下跌 | 10:00 后,量比≥2.5 且跌幅≤-2% | 高 | 普通 |
| 主力净流入 | 10:00 后,主力净额/成交额≥+8% | 低 | 普通 |
| 主力净流出 | 10:00 后,主力净额/成交额≤-8% | 低 | 普通 |
| 高股息(健康) | 股息率≥5% 且未跌破 MA60 | 低 | 普通 |
| 高股息(破位) | 股息率≥5% 且跌破 MA60 | 中 | 普通 |
| 金叉 | 距MA60差(MA20-MA60)由≤0 变 >0 | 高 | 穿越 |
| 死叉 | (MA20-MA60)由≥0 变 <0 | 高 | 穿越 |
| 站上MA60 | 距MA60 由<+1% 升到≥+1% | 中 | 穿越 |
| 跌破MA60 | 距MA60 由>-1% 跌到≤-1% | 高 | 穿越 |
| 乖离过热 | 距MA20 由<+15% 升到≥+15% | 中 | 穿越 |
| 乖离超卖 | 距MA20 由>-15% 跌到≤-15% | 中 | 穿越 |

### 5.5 信号补算 (`backfill`)
- `regen-signals <date>`:基于当日盘中快照序列重算该日信号,可先删旧再重建。
- `backfill(start,end)`:用 `daily_quote+daily_indicator+fund_flow` 合成"日线版快照",按"当日 vs 上一交易日"补;补出信号时间统一记当日 `15:00:00`。都不传则默认补当天。

### 5.6 邮件通知 (`notify`)
- 只发 `notification_log` 中无成功记录的新信号;同信号对同收件人成功后不再发。
- 成功/失败都写 `notification_log`;失败向调用方抛异常/失败提示。
- 配置优先级:环境变量 `EMAIL_*` > `data/email_config.json`。

### 5.7 失败策略
- 低频刷新:单股单项失败不中断整任务。
- CLI/Scheduler:打印失败原因。
- Web:吞异常,只显示最终同步结果。

## 6. 宏观快照 (`macro`)
同步上证指数(sh)、深证成指(sz):点位、涨跌点、涨跌幅、最高/最低、成交额、上涨/下跌/平盘/总家数。首页展示最新沪深概览;`/macro` 展示最近 200 条。

## 7. 入口

### 7.1 CLI (`python -m app.cli`)
`init / add <输入> / list / sync [codes...] / sync --low-freq / sync --notify / snapshots <code> --limit N / signals [code] --limit N / regen-signals <date> / macro --limit N / notify / forecast <code> --eps E --source S / financial <code> <date> --total-assets A --total-liabilities L`。
- `forecast`:写动态PE所需预测 EPS/净利润。
- `financial`:手工录入财务数据,支持由总资产/总负债反算资产负债率。

### 7.2 Web (`python -m app.web`, Flask 拼 HTML)
- `/` 首页:添加股票、立即同步、同步+低频、最新沪深宏观、股票池最新快照(列:代码/名称/现价/涨跌幅/PE_TTM/ROE/PB/股息率TTM/距MA20/距MA60/资产负债率/主力净流入万元)、最新快照时间、主力净流入来源汇总、**服务端排序**。
- `/stock/<code>`:核心指标卡片、最近100条快照、最近30条信号、只同步该股、只同步该股+低频。
- `/signals`:最近200条信号、阈值说明、级别与类型中文文案。
- `/macro`:最近200条宏观快照。
- `/snapshots`:最近500条全部快照历史。
- `/add`:处理首页表单,支持批量,批量时忽略统一自定义名称。
- `/sync`:参数 `code`(只同步一只)、`low_freq=1`(先刷低频)、`notify=1`(同步后发邮件)。
- `/backfill`:参数 `start`/`end`,都不传补当天。
- `/notify`:发送未通知新信号。
- 默认 `host=127.0.0.1 port=5001`,可由 `HOST`/`PORT` 覆盖。

### 7.3 Scheduler (`python -m app.scheduler`, APScheduler)
- **盘中任务** `intraday_job`:固定每 30 分钟触发,仅在工作日 09:30–11:35、13:00–15:10 真正执行同步;启动后立即执行一次;`misfire_grace_time=30min`;单实例避免重叠。盘中同步后自动生成信号并尝试发邮件。
- **低频任务**:每天 20:00 执行(分红→日资金流→财报→日K/MA),`misfire_grace_time=1h`。

## 8. 运行

- 本地:`uv run python -m app.web`,默认 `127.0.0.1:5001`。
- Docker:容器内 Web 绑 `0.0.0.0:5000`;`start.sh` 同容器启动 scheduler 与 web;`data/` 卷持久化 SQLite 与邮件配置。

## 9. 测试策略(核心逻辑重点覆盖)

- **严格 TDD(先测后写)**:`metrics`、`signals`、`stock_pool` 解析、`notify` 去重、`backfill` 日线版快照合成。纯函数/可注入仓储,离线运行。
- **适配器**:用 `tests/fixtures/` 下录制的真实响应做解析单测,不打真实网络。
- **入口(cli/web/scheduler)**:轻量冒烟——路由可返回、命令可跑通,service 注入假仓储/假适配器。
- 依赖注入用简单构造传参,不引重型 DI 框架。

## 10. 非目标(明确不做)

自动交易/下单、多用户/登录/权限、云端账号体系、历史回测、完整财务因子体系。
