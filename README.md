# StockTrace

面向 A 股的本地轻量跟踪系统:维护股票池、定时采集行情与低频指标、基于快照差分生成事件型信号、邮件提醒,提供 Flask Web 与 CLI 两套入口。单机研究工具,不含交易/账户/权限/云端/回测。

需求与设计见 `docs/requirements.md`、`docs/superpowers/specs/`、`docs/superpowers/plans/`。

## 架构

分层 + 适配器:入口(cli/web/scheduler)只调 service;service 通过构造注入获得仓储与数据源适配器;只有 `app/sources/*` 碰 HTTP;指标计算、信号差分等纯逻辑独立成无 IO 单元。

```
app/
  config.py            # 邮件配置(env EMAIL_* > data/email_config.json)、HOST/PORT
  cli.py web.py scheduler.py   # 三个入口
  wiring.py            # 装配点:把真实数据源接到 service
  db/                  # sqlite schema / connection / repository
  sources/             # 腾讯 / 东财 / 新浪 / 百度 适配器(唯一碰 HTTP)
  services/            # metrics / signals / stock_pool / snapshot / low_freq / backfill / macro / notify
```

## 安装与运行

需要 Python 3.12 + [uv](https://docs.astral.sh/uv/)。

```bash
uv venv --python 3.12
uv pip install flask apscheduler requests
uv run python -m app.cli init           # 初始化 SQLite (data/stocktrace.db)
```

### CLI

```bash
uv run python -m app.cli add 600519
uv run python -m app.cli add 贵州茅台
uv run python -m app.cli add "600519, 三七互娱, 华钰股份"   # 批量,支持中英逗号/顿号/分号/换行/制表符
uv run python -m app.cli list
uv run python -m app.cli sync                  # 同步全部
uv run python -m app.cli sync 600519 000858    # 只同步指定
uv run python -m app.cli sync --low-freq       # 同步前先刷低频(分红/资金流/财报/日K)
uv run python -m app.cli sync --notify         # 同步后发邮件
uv run python -m app.cli snapshots 600519 --limit 10
uv run python -m app.cli signals               # 最近信号
uv run python -m app.cli signals 600519 --limit 20
uv run python -m app.cli regen-signals 2026-05-28   # 按日重算该日信号
uv run python -m app.cli macro --limit 10
uv run python -m app.cli notify                # 发送未通知过的新信号
uv run python -m app.cli forecast 600519 --eps 25.3 --source manual          # 动态PE预测
uv run python -m app.cli financial 600519 2025-12-31 --total-assets 1000 --total-liabilities 300
```

### Web

```bash
uv run python -m app.web        # 默认 http://127.0.0.1:5001
```

页面:`/` 首页(添加/同步/股票池快照/沪深宏观/服务端排序)、`/stock/<code>`、`/signals`、`/macro`、`/snapshots`、`/backfill?start=&end=`、`/notify`。

### 调度器

```bash
uv run python -m app.scheduler  # 盘中每30分钟(工作日09:30-11:35/13:00-15:10) + 每日20:00低频
```

## 邮件配置

优先级:环境变量 `EMAIL_*` > `data/email_config.json`。

```json
{
  "smtp_host": "smtp.example.com",
  "smtp_port": 465,
  "username": "you@example.com",
  "password": "******",
  "from_addr": "you@example.com",
  "recipients": ["a@example.com", "b@example.com"]
}
```

环境变量:`EMAIL_SMTP_HOST` `EMAIL_SMTP_PORT` `EMAIL_USERNAME` `EMAIL_PASSWORD` `EMAIL_FROM` `EMAIL_RECIPIENTS`(逗号分隔)。

## Docker

```bash
docker build -t stocktrace .
docker run -p 5000:5000 -v $(pwd)/data:/app/data stocktrace
```

容器内 Web 绑 `0.0.0.0:5000`,`start.sh` 同容器启动调度器与 Web,`data/` 卷持久化 SQLite 与邮件配置。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `HOST` | `127.0.0.1` | Web 监听地址 |
| `PORT` | `5001` | Web 端口 |
| `STOCKTRACE_DATA_DIR` | `data` | SQLite 与邮件配置目录 |
| `EMAIL_*` | — | 邮件配置(见上) |

## 测试

```bash
uv run pytest
```

核心逻辑(指标口径、信号差分、解析、邮件去重、补算)重点覆盖;适配器用录制夹具做解析单测,不打真实网络。

## 数据源核对结论

适配器解析→落库契约用录制夹具锁定并测通;字段映射已对真实接口逐个核对(脚本在 `scripts/verify_*.py`,可自行复跑)。

| 数据源 | 核对结论 |
|---|---|
| 腾讯(行情/搜索/指数) | ✅ 实测核准。字段位与单位经真实数据验证:`amount_wan` 万元、`market_cap_yi`[45]/`float_market_cap_yi`[44] 亿元(用总市值≥流通市值的国有大盘股区分确认)、`pe_static`[53](经茅台 EPS 反算确认) |
| 新浪(财报三表) | ✅ 实测核准。tab 分隔 CSV,标签 `资产总计/负债合计/归属于母公司股东权益合计/归属于母公司所有者的净利润` 命中。**已修复**:新浪日期为 `YYYYMMDD`,归一化为 `YYYY-MM-DD`,否则 `metrics._report_month` 取错月份致 ROE 失效 |
| 东财(分红/日K/资金流/涨跌家数) | ✅ 字段映射核对一致。涨跌家数用 `push2/ulist.np`(secids)+ Referer;资金流用**多 URL 回退**(push2/push2his × http/https);分红走 `datacenter`。HTTP 层对连接错误/超时/5xx 网关错退避重试 |
| 百度(分钟级资金流) | ✅ 零鉴权接口 `vapi/v1/fundflow` + `Origin/Referer: gushitong.baidu.com` 头,解析分钟级 `mainForce`(万)。**国内/住宅 IP 可直接取数**;机房/海外 IP 被百度边缘层 403,此时按设计回落本地日级 `fund_flow` |

> 验证命令(在本机正常网络下):
> ```bash
> PYTHONPATH=. uv run python scripts/verify_tencent.py 600519
> PYTHONPATH=. uv run python scripts/verify_sina.py 600519
> PYTHONPATH=. uv run python scripts/verify_eastmoney.py 600519
> PYTHONPATH=. uv run python scripts/verify_baidu.py 600519
> ```

### 网络韧性与代理排查

适配器层(`app/sources/`)按"数据源会抖"设计,并参考同仓 `stocktrace` 项目的实战经验:

- **多 URL 回退**:东财资金流/日K 依次尝试 `push2` / `push2his`、`http` / `https`,任一可达即用。
- **退避重试**:连接重置、超时、502/503/504 网关错自动重试(不重试 4xx 与其它 5xx)。
- **逐项失败隔离**:低频刷新单只/单项失败不中断;盘中资金流失败回落本地日级 `fund_flow`;涨跌家数缺失则该字段为空——app 始终可用。

常见现象:**本机 V2Ray/Clash 等代理(`http_proxy`/`https_proxy`/`all_proxy` 环境变量)对部分 `*.eastmoney.com` 主机间歇性 502/重置**,而腾讯/新浪/datacenter 正常。排查:

```bash
env | grep -i proxy                       # 确认是否有本机代理
# 若在国内,给数据域名设直连最稳:
export NO_PROXY="eastmoney.com,gtimg.cn,sina.com.cn,sina.cn,baidu.com,qq.com,$NO_PROXY"
```

或在代理客户端给 `*.eastmoney.com` 设 direct 规则 / 换节点。容器/服务器部署时,建议用国内出口(海外 IP 会触发百度 403、部分东财主机重置)。
