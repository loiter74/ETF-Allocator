"""
ETF-Allocator MCP Server — 用自然语言调 ETF 系统的接口。

架构：HTTP 代理型。本 server 通过 stdio 与 ZCode 通信，内部用 httpx 调本地
FastAPI 后端（默认 http://localhost:8000）。不 import 业务模块，纯解耦代理。

依赖：Dashboard 后端服务必须先启动（ETF-Allocator/start.bat 或 uvicorn）。
未启动时所有 tool 会返回友好提示。

注册：见仓库根 .zcode/config.json 的 mcp.servers.etf-allocator。
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Optional

import httpx
from mcp.server.mcpserver import MCPServer

API_BASE = os.environ.get("ETF_API_BASE", "http://localhost:8000").rstrip("/")
# 受管资产白名单（6 个），供 tool 描述引用，避免模型编造资产名
ASSET_NAMES = "白酒ETF / 银行ETF / 红利ETF / 沪深300ETF / 科创50ETF / 国债ETF"
# 资产名 → 标的代码（PortfolioSnapshot 需要 code 字段，这里补全）
ASSET_CODES = {
    "白酒ETF": "161725",
    "银行ETF": "512800",
    "红利ETF": "515080",
    "沪深300ETF": "510300",
    "科创50ETF": "588000",
    "国债ETF": "511010",
}

mcp = MCPServer("etf-allocator")


def _api_call(method: str, path: str, *, json_body: Optional[dict] = None,
              params: Optional[dict] = None) -> Any:
    """统一调本地 FastAPI，处理连接错误和 HTTP 错误，返回 JSON 或友好提示。"""
    try:
        # trust_env=False：不走系统代理（HTTP_PROXY 等），直连本地 FastAPI
        # 否则环境里的代理（如 127.0.0.1:7890）会拦截 localhost 请求返回 502
        with httpx.Client(timeout=60.0, trust_env=False) as client:
            resp = client.request(method, f"{API_BASE}{path}", json=json_body, params=params)
    except httpx.ConnectError:
        return {
            "error": "后端服务未启动",
            "hint": f"请先启动 Dashboard 后端（ETF-Allocator/start.bat），确认 {API_BASE} 可访问后重试。",
        }
    except httpx.TimeoutException:
        return {"error": "后端响应超时（>60s）", "hint": "可能是因子计算耗时，稍后重试或缩小查询范围。"}

    if resp.status_code >= 400:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text[:500]
        return {"error": f"后端返回 HTTP {resp.status_code}", "detail": detail}

    return resp.json()


# ============================================================
# Tool 1: 生成交易计划（核心，只读）
# ============================================================
@mcp.tool(
    name="generate_trade_plan",
    description=(
        "生成本月交易计划（只读预览，不写库）。输入完整持仓快照 + 新增资金，"
        "系统按 V2 规则输出：正式卖单、科创50影子止盈单、纪律补仓买单（含阶段明细）、现金轧差。\n\n"
        "受管资产白名单（asset 字段必须用这些中文名）：" + ASSET_NAMES + "。\n"
        "非白名单持仓也可传入，系统只计入账户风险、不自动交易。\n\n"
        "两阶段语义：若返回 phase='sell_preview'，说明本月有正式卖单（战略硬上限触发），"
        "buys 会为空 —— 需先回填真实成交价调 confirm_trade_plan，才会算出买单。"
        "phase='complete' 时 buys 已直接算好。\n\n"
        "现金约束：bond_pool_cash + equity_pending_cash 不得超过 account_cash。"
    ),
)
def generate_trade_plan(
    new_money: float,
    positions: list[dict],
    account_cash: float = 0.0,
    snapshot_date: Optional[str] = None,
    price_date: Optional[str] = None,
    bond_pool_cash: float = 0.0,
    equity_pending_cash: float = 0.0,
) -> Any:
    """生成交易计划。

    Args:
        new_money: 本月新增资金（元），如 10000
        positions: 持仓列表，每项 {asset: "白酒ETF", shares: 6200, price: 0.583, average_cost: 0.532}。
                   asset 必须是白名单中文名；code 会自动补全。
        account_cash: 账户总现金（元）。注意 bond_pool_cash + equity_pending_cash 不得超过此值。
        snapshot_date: 快照日（YYYY-MM-DD），默认今天。
        price_date: 行情日（YYYY-MM-DD），默认等于 snapshot_date。
        bond_pool_cash: 国债累积池现金标记（元，须 ≤ account_cash）。
        equity_pending_cash: 权益待投现金（元，须 ≤ account_cash）。

    Returns:
        交易计划 JSON：trade_plan.buys / formal_sells / shadow_sells / cash_ledger 等。
    """
    today = snapshot_date or date.today().isoformat()
    pdate = price_date or today

    # 补全 positions：自动填 code（白名单资产）
    full_positions = []
    for pos in positions:
        asset = pos.get("asset", "")
        full = {
            "asset": asset,
            "code": pos.get("code") or ASSET_CODES.get(asset, ""),
            "shares": pos["shares"],
            "price": pos["price"],
            "is_equity": pos.get("is_equity", asset != "国债ETF"),
        }
        if "average_cost" in pos:
            full["average_cost"] = pos["average_cost"]
        full_positions.append(full)

    body = {
        "snapshot": {
            "snapshot_date": today,
            "price_date": pdate,
            "new_money": new_money,
            "account_cash": account_cash,
            "bond_pool_cash": bond_pool_cash,
            "equity_pending_cash": equity_pending_cash,
            "positions": full_positions,
        }
    }
    return _api_call("POST", "/api/trade-plan/preview", json_body=body)


# ============================================================
# Tool 2: 确认交易计划（有副作用：写库）
# ============================================================
@mcp.tool(
    name="confirm_trade_plan",
    description=(
        "⚠️ 确认交易计划并写入数据库（有副作用）。用于 preview 后的正式落账："
        "推进科创50利润保护状态、记录成交审计。\n\n"
        "幂等：同一 idempotency_key 重复调用只落账一次，安全。\n\n"
        "若 preview 返回 phase='sell_preview'（有正式卖单），必须在此传入真实成交 fills "
        "（asset/shares/price），系统才会据此重算买单（next_plan.buys）。"
        "phase='complete' 时直接确认即可，不需 fills。"
    ),
)
def confirm_trade_plan(
    plan_id: str,
    idempotency_key: str,
    snapshot: dict,
    fills: Optional[list[dict]] = None,
) -> Any:
    """确认交易计划。

    Args:
        plan_id: preview 返回的 trade_plan.plan_id（必须原样回传，否则报"计划已变化"）。
        idempotency_key: 客户端生成的幂等键（8~200 字符，如 "2026-08-confirm-001"）。
        snapshot: 与 preview 相同的完整快照对象（{snapshot_date, price_date, new_money, account_cash, positions, ...}）。
        fills: 真实卖出成交回填列表，仅当 preview 有 formal_sells 时必填。
               每项 {asset: "白酒ETF", shares: 1500, price: 1.23, commission?: 5}。

    Returns:
        {confirmation, confirmed_plan, next_plan(重算后的买单), strategy_state(推进后的科创状态)}。
    """
    body = {
        "snapshot": snapshot,
        "plan_id": plan_id,
        "idempotency_key": idempotency_key,
    }
    if fills:
        body["fills"] = fills
    return _api_call("POST", "/api/trade-plan/confirm", json_body=body)


# ============================================================
# Tool 3: 查本月报告（只读）
# ============================================================
@mcp.tool(
    name="get_monthly_report",
    description=(
        "查询本月配置报告（只读）。返回市场温度计（沪深300 PE分位/全A PB分位/权益比例）、"
        "各资产机会分与分配建议、组合风险（因子组权重）、国债累积池状态。\n\n"
        "这是 v1.3 兼容入口：基于最新 PIT 数据算因子，total_assets=0 时为'初始建仓模式'。"
        "要看真实持仓的三阶段交易计划，请用 generate_trade_plan。"
    ),
)
def get_monthly_report(
    report_date: Optional[str] = None,
    total_assets: float = 0.0,
) -> Any:
    """查本月报告。

    Args:
        report_date: 报告日（YYYY-MM-DD），默认最新数据日。
        total_assets: 当前组合总资产（元）。0=初始建仓模式（目标权重归零）。

    Returns:
        报告 JSON：market_temp / allocations / portfolio_risk / bond_status 等。
    """
    params: dict[str, Any] = {}
    if report_date:
        params["date"] = report_date
    if total_assets > 0:
        params["total"] = total_assets
    return _api_call("GET", "/api/report", params=params)


# ============================================================
# Tool 4: 查估值历史（只读）
# ============================================================
@mcp.tool(
    name="get_valuation_history",
    description=(
        "查询指数估值（PE/PB）历史序列和当前分位（只读）。用于判断'现在算贵还是便宜'。\n\n"
        "常用指数：000300=沪深300、000985=全A(上证50替代)、399997=中证白酒、"
        "399986=中证银行、000922=中证红利、000688=科创50。\n"
        "field 只接受 'pe' 或 'pb'。分位用 expanding window 计算，防未来函数。"
    ),
)
def get_valuation_history(
    index: str = "000300",
    field: str = "pe",
    years: int = 5,
) -> Any:
    """查估值历史。

    Args:
        index: 指数代码，如 "000300"（沪深300）。
        field: "pe" 或 "pb"。
        years: 回看年数（默认 5）。

    Returns:
        {index, field, available, data: [{date, value, percentile}, ...]}。
    """
    return _api_call("GET", "/api/history", params={"index": index, "field": field, "years": years})


# ============================================================
# Tool 5: 解析券商截图文字（只读草稿）
# ============================================================
@mcp.tool(
    name="parse_broker_text",
    description=(
        "把券商 App 截图的 OCR 文字解析成结构化持仓草稿（只读，不写库）。\n"
        "适合'我截了张图，OCR 出这些字，帮我认出持仓和现金'的场景。\n\n"
        "输出是待核对草稿：每个字段带置信度和证据，需人工核对后才能用于 generate_trade_plan。"
        "原图不会上传后端，只传 OCR 文字。"
    ),
)
def parse_broker_text(
    ocr_text: str,
    snapshot_date: Optional[str] = None,
) -> Any:
    """解析券商文字。

    Args:
        ocr_text: 从券商截图 OCR 出的文字内容（一段或多段拼起来）。
        snapshot_date: 已知快照日（可选，辅助解析）。

    Returns:
        草稿 JSON：draft.positions[].{asset, shares, price, average_cost}（每个字段含 value/confidence/source）。
    """
    body: dict[str, Any] = {"ocr_texts": [{"text": ocr_text, "name": "broker-screenshot"}]}
    if snapshot_date:
        body["snapshot_date"] = snapshot_date
    return _api_call("POST", "/api/portfolio-snapshot/parse-text", json_body=body)


if __name__ == "__main__":
    mcp.run(transport="stdio")
