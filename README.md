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

## 数据源口径备注

`app/sources/sina.py`、`baidu.py`、`tencent.py` 中带 `NOTE for maintainer` 的部分:解析→落库契约已用夹具锁定并测通,但真实线上端点的字段名/字段位需用一次真实请求确认后再微调映射,不影响上层逻辑。
