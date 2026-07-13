# 全球资金风格流向早报

这是一个基于 `Python + GitHub Actions + DeepSeek + 飞书` 的日频自动化项目，用免费市场数据生成“全球资金流向早报”。

## 功能

- 每日抓取全球主要市场、主题与宏观代理指标
- 用规则引擎判断资金偏好流向
- 用 DeepSeek 把规则结果整理成可读的中文晨报
- 推送精简版到飞书群机器人
- 追加完整版到飞书云文档
- 同时落盘 `Markdown + JSON` 产物，便于复盘与审计

## 当前判断逻辑

本项目输出的是“资金偏好/风格流向判断”，不是机构数据库意义上的精确美元净流入净流出。

判断依据主要来自：

- 区域指数相对强弱
- 主题板块相对强弱
- 近 5 日延续性
- 成交量相对活跃度
- 美元、长债、VIX、黄金、原油等宏观代理因子

## 本地运行

1. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

2. 配置环境变量

复制 `.env.example` 为 `.env`，填写以下字段：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`，建议 `deepseek-v4-flash`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_DOC_ID`

3. 运行

```bash
set PYTHONPATH=src
python -m all_markets.main
```

执行完成后会在 `outputs/YYYY-MM-DD/` 下生成：

- `report.md`
- `report.json`

## GitHub Actions Secrets

在仓库 `Settings -> Secrets and variables -> Actions` 中新增：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `FEISHU_WEBHOOK_URL`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_DOC_ID`
- `REPORT_BRAND`

## 飞书接入说明

### 1. 飞书群机器人

- 在目标群中添加自定义机器人
- 获取 `Webhook URL`
- 填入 `FEISHU_WEBHOOK_URL`

### 2. 飞书云文档

- 在飞书开放平台创建自建应用
- 为应用申请文档读写权限
- 获取 `App ID` 和 `App Secret`
- 新建一个长期归档文档，把文档 ID 填入 `FEISHU_DOC_ID`

当前实现采用“向已有文档末尾追加内容”的方式，维护成本最低。

## 调度时间

当前 GitHub Actions 默认在 `23:30 UTC` 运行，约等于北京时间早上 `07:30`。

你可以自行修改 `.github/workflows/daily_report.yml` 中的 cron。

## 后续可扩展

- 新增 A 股、港股、加密市场
- 引入 ETF 资金流、新闻摘要、宏观日历
- 增加周报/月报聚合
- 增加异常告警和失败重试策略
