# AI Financial Intelligence Platform

一个面向加密与宏观研究场景的首个 MVP 切片。当前版本提供一个可本地运行的 FastAPI 页面，允许用户手动发起分析，基于 Binance/FRED/事件源的 fixture-first 数据管线生成结构化投研报告，并将最近一次报告保存到 SQLite。

## 当前 MVP 切片

- Web 页面可手动触发一次分析
- 默认使用本地 fixtures，保证无外部 API 也能跑通
- 支持通过统一代理配置切换到真实 Binance/FRED/事件源请求
- 输出统一情报 JSON 与四角色结构化报告
- 将最近一次报告持久化到 `data/analysis.db`
- 在页面展示每个数据源的 live / fixture / fallback 状态
- 明确标注“仅供研究参考，不构成投资建议”

## 技术选择

- 后端：FastAPI
- SSR：直接返回 HTMLResponse，避免首轮引入额外前端框架和模板依赖
- 数据抓取：`httpx`
- 存储：标准库 `sqlite3`
- 测试：标准库 `unittest` + `httpx.ASGITransport`

## 本地启动

1. 安装依赖：

```bash
python -m pip install -e .
```

2. 可选环境变量：

```powershell
$env:AI_FI_MOCK_MODE="1"
$env:AI_FI_HTTP_PROXY="http://127.0.0.1:4780"
$env:FRED_API_KEY="your-key"
$env:AI_FI_EVENT_FEED_URL="https://api.rss2json.com/v1/api.json?rss_url=https://www.coindesk.com/arc/outboundfeeds/rss/"
```

说明：

- `AI_FI_MOCK_MODE=1` 为默认值，会强制使用本地 fixtures
- `AI_FI_MOCK_MODE=0` 时，应用会优先走真实外部请求；请求失败后会记录 warning 并回退到 fixtures
- `AI_FI_EVENT_FEED_URL` 未设置时，默认会使用 CoinDesk RSS 的 JSON 代理端点
- 代理默认值是 `http://127.0.0.1:4780`

3. 启动服务：

```bash
uvicorn ai_financial_intelligence.main:app --reload
```

4. 打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 运行验证

```bash
python -m unittest discover -s tests -p "test_*.py"
```

## 远程事件源 JSON 契约

除了默认的 CoinDesk RSS-to-JSON 端点外，也支持将 `AI_FI_EVENT_FEED_URL` 指向自定义 JSON 事件源。推荐使用如下稳定契约：

```json
{
  "schema_version": "ai-fi-event-feed/v1",
  "generated_at": "2026-04-03T10:00:00Z",
  "source": {
    "name": "custom-feed",
    "url": "https://example.com/events.json"
  },
  "events": [
    {
      "headline": "ETF inflows remain strong",
      "impact": "positive",
      "confidence": "high",
      "published_at": "2026-04-03T09:45:00Z",
      "url": "https://example.com/etf",
      "symbols": ["BTCUSDT"]
    }
  ]
}
```

字段约束：

- `schema_version` 固定为 `ai-fi-event-feed/v1`
- `events` 必须为数组，`headline` 为必填
- `impact` 支持 `positive` / `negative` / `neutral`
- `confidence` 支持 `low` / `medium` / `high`
- 其余字段如 `published_at`、`url`、`symbols`、`source` 为可选

## 目录说明

- `ai_financial_intelligence/`: 产品代码
- `ai_financial_intelligence/fixtures/`: 本地 mock 数据
- `docs/`: 产品范围、验收、任务与指标
- `factory/`: 自动化工厂 CLI
- `tests/`: 自动化测试

## 已知边界

- 真实 FRED 指标与默认 CoinDesk 事件源已接入，失败时仍会回退到 fixtures
- 报告生成仍是轻量规则编排，尚未接入真实大模型或 LangGraph/CrewAI
- 不包含登录、下单、社区、广场或多租户能力
