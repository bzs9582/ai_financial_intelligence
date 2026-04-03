from __future__ import annotations

from html import escape
from typing import Any
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

from .analysis import (
    AnalysisService,
    DISCLAIMER,
    SUPPORTED_ASSETS,
    SUPPORTED_TIMEFRAMES,
)
from .settings import AppSettings


def _get_service(app: FastAPI) -> AnalysisService:
    service = getattr(app.state, "analysis_service", None)
    if service is None:
        settings = getattr(app.state, "analysis_settings", None)
        service = AnalysisService(settings=settings)
        app.state.analysis_service = service
    return service


def create_app(settings: AppSettings | None = None) -> FastAPI:
    app = FastAPI(title="AI Financial Intelligence Platform")
    app.state.analysis_settings = settings

    @app.get("/", response_class=HTMLResponse)
    async def home(request: Request) -> HTMLResponse:
        service = _get_service(request.app)
        latest = service.latest_result()
        html = render_page(
            service=service,
            active_asset=service.settings.default_asset,
            active_timeframe=service.settings.default_timeframe,
            latest_result=latest,
        )
        return HTMLResponse(html)

    @app.post("/analyze", response_class=HTMLResponse)
    async def analyze(request: Request) -> HTMLResponse:
        service = _get_service(request.app)
        raw_form = (await request.body()).decode("utf-8")
        form = parse_qs(raw_form)
        asset = form.get("asset", [service.settings.default_asset])[0]
        timeframe = form.get("timeframe", [service.settings.default_timeframe])[0]
        try:
            result = await service.run_analysis(asset, timeframe)
        except ValueError as exc:
            html = render_page(
                service=service,
                active_asset=asset.upper(),
                active_timeframe=timeframe.lower(),
                latest_result=service.latest_result(),
                error_message=str(exc),
            )
            return HTMLResponse(html, status_code=400)

        html = render_page(
            service=service,
            active_asset=result["report"]["asset"],
            active_timeframe=result["report"]["timeframe"],
            current_result=result,
            latest_result=result,
            success_message="分析已完成，以下为最新结构化报告。",
        )
        return HTMLResponse(html)

    return app


def _render_options(options: tuple[str, ...], active_value: str) -> str:
    rendered: list[str] = []
    for option in options:
        selected = " selected" if option == active_value else ""
        rendered.append(
            f'<option value="{escape(option)}"{selected}>{escape(option)}</option>'
        )
    return "".join(rendered)


def _render_source_statuses(statuses: list[dict[str, Any]]) -> str:
    items = []
    for status in statuses:
        items.append(
            """
            <li class="status-item">
              <strong>{name}</strong>
              <span class="status-mode">{mode}</span>
              <p>{detail}</p>
            </li>
            """.format(
                name=escape(str(status["name"])),
                mode=escape(str(status["mode"])),
                detail=escape(str(status["detail"])),
            )
        )
    return "".join(items)


def _render_report(result: dict[str, Any]) -> str:
    report = result["report"]
    probabilities = "".join(
        """
        <li class="probability-row">
          <span>{scenario}</span>
          <span>{probability}%</span>
        </li>
        """.format(
            scenario=escape(item["scenario"]),
            probability=escape(str(item["probability"])),
        )
        for item in report["scenario_probabilities"]
    )
    bull_case = "".join(
        f"<li>{escape(item)}</li>" for item in report.get("bull_case", [])
    )
    bear_case = "".join(
        f"<li>{escape(item)}</li>" for item in report.get("bear_case", [])
    )
    invalidations = "".join(
        f"<li>{escape(item)}</li>" for item in report.get("invalidation_conditions", [])
    )
    risk_notes = "".join(
        f"<li>{escape(item)}</li>" for item in report.get("risk_notes", [])
    )
    key_signals = "".join(f"<li>{escape(item)}</li>" for item in report["key_signals"])

    return f"""
    <section class="report-shell">
      <div class="report-header card">
        <p class="eyebrow">Latest Report</p>
        <h2>{escape(report['asset'])} / {escape(report['timeframe'])}</h2>
        <p>{escape(report['snapshot_summary'])}</p>
        <p class="timestamp">Generated at {escape(report['generated_at'])}</p>
      </div>
      <div class="report-grid">
        <article class="card">
          <h3>Key Signals</h3>
          <ul>{key_signals}</ul>
        </article>
        <article class="card">
          <h3>Data Source Status</h3>
          <ul class="status-list">{_render_source_statuses(report['source_statuses'])}</ul>
        </article>
        <article class="card">
          <h3>Peter</h3>
          <p>{escape(report['peter']['summary'])}</p>
        </article>
        <article class="card">
          <h3>Venturus</h3>
          <p>{escape(report['venturus']['summary'])}</p>
        </article>
        <article class="card">
          <h3>Pivot</h3>
          <p>{escape(report['pivot']['summary'])}</p>
        </article>
        <article class="card">
          <h3>Reality Check</h3>
          <p>{escape(report['reality_check']['summary'])}</p>
        </article>
        <article class="card">
          <h3>多头逻辑</h3>
          <ul>{bull_case}</ul>
        </article>
        <article class="card">
          <h3>空头逻辑</h3>
          <ul>{bear_case}</ul>
        </article>
        <article class="card">
          <h3>情景概率分布</h3>
          <ul class="probability-list">{probabilities}</ul>
        </article>
        <article class="card">
          <h3>失效条件</h3>
          <ul>{invalidations}</ul>
        </article>
        <article class="card">
          <h3>风险提示</h3>
          <ul>{risk_notes}</ul>
        </article>
      </div>
    </section>
    """


def _render_latest_summary(latest_result: dict[str, Any] | None) -> str:
    if not latest_result:
        return """
        <article class="card">
          <p class="eyebrow">Recent Analysis</p>
          <h2>尚无分析记录</h2>
          <p>使用默认 BTCUSDT / 4h 即可生成第一份报告。</p>
        </article>
        """

    report = latest_result["report"]
    source_modes = ", ".join(status["mode"] for status in report["source_statuses"])
    return f"""
    <article class="card">
      <p class="eyebrow">Recent Analysis</p>
      <h2>{escape(report['asset'])} / {escape(report['timeframe'])}</h2>
      <p>{escape(report['snapshot_summary'])}</p>
      <p class="timestamp">Updated at {escape(report['generated_at'])}</p>
      <p class="meta">Source modes: {escape(source_modes)}</p>
    </article>
    """


def render_page(
    *,
    service: AnalysisService,
    active_asset: str,
    active_timeframe: str,
    current_result: dict[str, Any] | None = None,
    latest_result: dict[str, Any] | None = None,
    success_message: str | None = None,
    error_message: str | None = None,
) -> str:
    notice = ""
    if success_message:
        notice = f'<p class="notice success">{escape(success_message)}</p>'
    elif error_message:
        notice = f'<p class="notice error">{escape(error_message)}</p>'

    report_html = _render_report(current_result) if current_result else ""
    proxy_label = service.settings.proxy.label()

    return f"""
    <!doctype html>
    <html lang="zh-CN">
      <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>AI Financial Intelligence Platform</title>
        <style>
          :root {{
            --bg: #f5efe3;
            --panel: rgba(255, 251, 245, 0.82);
            --ink: #182322;
            --muted: #53615f;
            --accent: #0f766e;
            --accent-soft: #d4eee4;
            --danger: #8f2d23;
            --border: rgba(24, 35, 34, 0.12);
            --shadow: 0 20px 50px rgba(24, 35, 34, 0.12);
          }}
          * {{ box-sizing: border-box; }}
          body {{
            margin: 0;
            min-height: 100vh;
            font-family: "Segoe UI", "PingFang SC", sans-serif;
            color: var(--ink);
            background:
              radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 30%),
              linear-gradient(145deg, #f2ebdc, #f8f4ec 55%, #ece4d1);
          }}
          .page {{
            max-width: 1180px;
            margin: 0 auto;
            padding: 32px 20px 56px;
          }}
          .hero {{
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 20px;
            align-items: start;
          }}
          .card {{
            background: var(--panel);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border);
            border-radius: 22px;
            padding: 22px;
            box-shadow: var(--shadow);
          }}
          .hero h1, h2, h3 {{
            font-family: "Georgia", "Songti SC", serif;
            margin: 0 0 12px;
          }}
          .hero p, li {{
            line-height: 1.55;
          }}
          .eyebrow {{
            margin: 0 0 12px;
            color: var(--muted);
            letter-spacing: 0.08em;
            text-transform: uppercase;
            font-size: 0.78rem;
          }}
          .controls {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 14px;
            margin: 18px 0;
          }}
          label {{
            display: block;
            font-size: 0.92rem;
            color: var(--muted);
            margin-bottom: 8px;
          }}
          select, button {{
            width: 100%;
            border-radius: 14px;
            border: 1px solid var(--border);
            padding: 12px 14px;
            font: inherit;
          }}
          button {{
            border: none;
            background: linear-gradient(135deg, #0f766e, #1f5d57);
            color: white;
            font-weight: 700;
            cursor: pointer;
          }}
          .meta {{
            color: var(--muted);
          }}
          .notice {{
            margin: 16px 0 0;
            padding: 12px 14px;
            border-radius: 14px;
          }}
          .success {{
            background: var(--accent-soft);
          }}
          .error {{
            background: rgba(143, 45, 35, 0.12);
            color: var(--danger);
          }}
          .report-shell {{
            margin-top: 24px;
          }}
          .report-header {{
            margin-bottom: 20px;
          }}
          .timestamp {{
            color: var(--muted);
            font-size: 0.92rem;
          }}
          .report-grid {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 18px;
          }}
          ul {{
            padding-left: 18px;
            margin: 0;
          }}
          .status-list, .probability-list {{
            list-style: none;
            padding-left: 0;
          }}
          .status-item {{
            padding: 10px 0;
            border-top: 1px solid var(--border);
          }}
          .status-item:first-child {{
            border-top: none;
            padding-top: 0;
          }}
          .status-item p {{
            margin: 8px 0 0;
            color: var(--muted);
          }}
          .status-mode {{
            display: inline-block;
            margin-left: 8px;
            padding: 2px 8px;
            border-radius: 999px;
            background: rgba(15, 118, 110, 0.1);
            color: var(--accent);
            font-size: 0.82rem;
          }}
          .probability-row {{
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-top: 1px solid var(--border);
          }}
          .probability-row:first-child {{
            border-top: none;
            padding-top: 0;
          }}
          @media (max-width: 900px) {{
            .hero, .report-grid {{
              grid-template-columns: 1fr;
            }}
            .controls {{
              grid-template-columns: 1fr;
            }}
          }}
        </style>
      </head>
      <body>
        <main class="page">
          <section class="hero">
            <article class="card">
              <p class="eyebrow">Bootstrap MVP</p>
              <h1>AI Financial Intelligence Platform</h1>
              <p>在单页中选择资产与时间窗口，生成一份包含多空逻辑、概率分布与失效条件的结构化投研报告。</p>
              <p class="meta">Proxy: {escape(proxy_label)} | Mock mode: {escape(str(service.settings.mock_mode))}</p>
              <form method="post" action="/analyze">
                <div class="controls">
                  <div>
                    <label for="asset">资产</label>
                    <select id="asset" name="asset">{_render_options(SUPPORTED_ASSETS, active_asset)}</select>
                  </div>
                  <div>
                    <label for="timeframe">周期</label>
                    <select id="timeframe" name="timeframe">{_render_options(SUPPORTED_TIMEFRAMES, active_timeframe)}</select>
                  </div>
                </div>
                <button type="submit">开始分析</button>
              </form>
              {notice}
              <p class="meta">{escape(DISCLAIMER)}</p>
            </article>
            {_render_latest_summary(latest_result)}
          </section>
          {report_html}
        </main>
      </body>
    </html>
    """


app = create_app()
