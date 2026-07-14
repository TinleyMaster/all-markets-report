# 全球资金流向早报

这是一个基于 `Python + GitHub Actions + DeepSeek + 飞书应用机器人` 的日频自动化项目，用免费市场数据生成“全球资金流向早报”。

## 功能

- 每日抓取全球主要市场、主题与宏观代理指标
- 额外抓取免费 RSS 新闻，生成“主线新闻追踪”
- 读取零成本维护型事件清单，生成“本周重磅日历”
- 用规则引擎判断资金偏好流向
- 输出“两层结构”：
  - 第1层：日频免费主报告（地域轮动、行业轮动、跨资产、四分法结论）
  - 第2层：周频增强信号（CFTC COT、A股北向资金、BTC ETF、信用债风险偏好）
- 用 DeepSeek 把规则结果整理成可读的中文晨报
- 使用飞书应用机器人发送群消息
- 每天在飞书云空间新建一份归档文档
- 按 `年份/月` 自动创建目录归档
- 同时落盘 `Markdown + JSON` 产物，便于复盘与审计

## 当前判断逻辑

本项目输出的是“资金偏好/风格流向判断”，不是机构数据库意义上的精确美元净流入净流出。

判断依据主要来自：

- 区域指数相对强弱
- 主题板块相对强弱
- 近 5 日延续性
- 成交量相对活跃度
- 美元、长债、VIX、黄金、原油等宏观代理因子
- 周频公开数据补充验证：CFTC COT、北向资金、BTC ETF 净流入、信用债 ETF 相对强弱
- 免费新闻层：Google News RSS 聚合出的地缘政治、美股科技、亚太、外汇债市、加密主线
- 零成本日历层：`config/event_calendar.yaml` 维护的重点跟踪事件

## 零新增成本晨报层

为了把输出从“行情解释器”升级为更像真正的晨报，项目新增了两层完全免费的补充能力：

- `config/news_sources.yaml`
  - 配置免费 RSS 新闻源
  - 当前默认追踪：地缘政治与能源、美股科技、亚太、外汇债市、加密
- `config/event_calendar.yaml`
  - 配置本周关注事件
  - 当前是维护型清单，适合把本周最关键的宏观/财报/产业事件直接写进日报

说明：

- 这两层不增加任何付费 API 成本
- 代价是需要你偶尔维护 `event_calendar.yaml`
- 后续如果升级到付费新闻源，只需替换数据层，不需要重写整套报告模板

## 飞书归档方式

日报不再追加到固定文档，而是每天新建一份飞书云文档：

- 文档名：`YYYY-MM-DD 全球资金流向早报.md`
- 归档路径：`你指定的父目录 / 年份 / 月份 / 当日日报文档`
- 若年份目录或月份目录不存在，脚本会自动创建

说明：

- 飞书“云文档”本质是在线文档，不是真正本地 `.md` 文件
- 当前实现会创建一个标题带 `.md` 后缀的飞书云文档，并将 Markdown 内容写入其中

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
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_CHAT_ID`
- `FEISHU_REPORT_FOLDER`
- `REPORT_BRAND`

其中：

- `FEISHU_CHAT_ID` 是飞书群的 `chat_id`
- `FEISHU_REPORT_FOLDER` 可以直接填写飞书文件夹链接，也可以填写 `fld...` 文件夹 token

3. 运行

```bash
set PYTHONPATH=src
python -m all_markets.main
```

执行完成后会在 `outputs/YYYY-MM-DD/` 下生成：

- `report.md`
- `report.json`

如果飞书配置完整，还会：

- 在目标群发送日报摘要
- 在飞书云空间的年/月目录下创建当日日报文档

## GitHub Actions Secrets

在仓库 `Settings -> Secrets and variables -> Actions` 中新增：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_MODEL`
- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_CHAT_ID`
- `FEISHU_REPORT_FOLDER`
- `REPORT_BRAND`

## 飞书应用要求

你的飞书应用需要同时具备两类能力：

- 群机器人发消息
- 云空间文件夹和云文档创建/写入

建议你把这个应用加到：

- 目标群聊中
- 目标归档文件夹的协作者中，并授予可编辑或管理权限

否则即使 API 可调用，也可能没有目标群或目标目录的写权限。

## 调度时间

当前 GitHub Actions 默认在 `23:30 UTC` 运行，约等于北京时间早上 `07:30`。

你可以自行修改 `.github/workflows/daily_report.yml` 中的 cron。

## 后续可扩展

- 新增 A 股、港股、加密市场
- 引入 ETF 资金流、新闻摘要、宏观日历
- 增加周报/月报聚合
- 增加异常告警和失败重试策略
