"""
FinancialAuditor V4.0 — 财务排雷与体检专家
专注 8Q 财务剪刀差 + 营收/利润四连击 + 存货/合同负债异动审查
"""
from typing import Dict, Any, List, Optional
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class FinancialAuditor(ResearchAgent):
    """财务审计师 — V4.0 专家节点, 负责定量排雷"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "FinancialAuditor"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        """对单个标的执行财务体检"""
        code = ctx.get("stock_code", "")
        name = ctx.get("stock_name", "")
        if not code:
            return {"agent": self.name, "error": "No stock_code", "verdict": "SKIP"}

        logger.info(f"[{self.name}] Auditing {code} {name}")

        # 1. 加载 8Q 财务数据
        fin = await self.data_loader.load_financial_statements(code, periods=8)
        quarters = fin.get("quarters", [])
        if len(quarters) < 4:
            return {
                "agent": self.name, "code": code, "name": name,
                "verdict": "INSUFFICIENT_DATA",
                "reason": f"Only {len(quarters)} quarters available (need >=4)",
                "quarters_available": len(quarters),
            }

        # 2. 计算核心指标
        metrics = self._compute_metrics(quarters)

        # 3. 审计判定
        audit = self._audit(metrics, quarters)

        audit["agent"] = self.name
        audit["code"] = code
        audit["name"] = name
        audit["quarters_count"] = len(quarters)
        return audit

    # ═══ 指标计算 ═════════════════════════════════

    def _compute_metrics(self, quarters: List[Dict]) -> List[Dict]:
        """为每个季度计算 YoY / QoQ / 剪刀差"""
        results = []
        for i, q in enumerate(quarters):
            rev = q.get("revenue", 0) or 0
            profit = q.get("profit", 0) or 0
            inv = q.get("inventory", 0) or 0
            cl = q.get("contract_liability", 0) or 0
            ocf = q.get("op_cashflow", 0) or 0

            m = {
                "report_date": q.get("report_date", ""),
                "revenue": rev,
                "profit": profit,
                "op_cashflow": ocf,
                "inventory": inv,
                "contract_liability": cl,
            }

            # QoQ (环比: vs 上一季度)
            if i >= 1:
                prev_rev = results[i - 1]["revenue"]
                prev_profit = results[i - 1]["profit"]
                m["rev_qoq"] = self._pct(rev, prev_rev)
                m["profit_qoq"] = self._pct(profit, prev_profit)
            else:
                m["rev_qoq"] = None
                m["profit_qoq"] = None

            # YoY (同比: vs 去年同季度, 即 i-4)
            if i >= 4:
                yoy_rev = results[i - 4]["revenue"]
                yoy_profit = results[i - 4]["profit"]
                m["rev_yoy"] = self._pct(rev, yoy_rev)
                m["profit_yoy"] = self._pct(profit, yoy_profit)
            else:
                m["rev_yoy"] = None
                m["profit_yoy"] = None

            # 剪刀差 = 利润增速 - 营收增速 (正 → 利润率扩张)
            if m.get("rev_yoy") is not None and m.get("profit_yoy") is not None:
                m["scissor_gap"] = round(m["profit_yoy"] - m["rev_yoy"], 2)
            else:
                m["scissor_gap"] = None

            # 毛利率估算
            m["gross_margin_est"] = round((rev - (rev - profit)) / rev * 100, 1) if rev > 0 else 0

            # 经营现金流/利润 健康度
            m["ocf_profit_ratio"] = round(ocf / profit, 2) if profit and profit > 0 else None

            # 存货/营收 占比 (过高可能积压)
            m["inventory_revenue_ratio"] = round(inv / rev, 2) if rev > 0 else None

            results.append(m)

        return results

    # ═══ 审计判定 ═════════════════════════════════

    def _audit(self, metrics: List[Dict], quarters: List[Dict]) -> Dict:
        """综合判定: 剪刀差 / 四连击 / 存货 / 合同负债"""
        # 取有 YoY 数据的季度 (i>=4)
        yoy_quarters = [m for m in metrics if m.get("rev_yoy") is not None]
        if not yoy_quarters:
            return {"verdict": "INSUFFICIENT_DATA", "metrics": metrics}

        latest = metrics[-1]

        # ── 1. 剪刀差检测 ──
        scissor_quarters = [m for m in yoy_quarters if (m.get("scissor_gap") or 0) > 0]
        latest_gap = latest.get("scissor_gap")
        scissor_pass = latest_gap is not None and latest_gap > 0

        # ── 2. 四连击检测 (连续4个有YoY数据的季度, 营收和利润同比都正增长) ──
        consecutive_hits = 0
        max_consecutive = 0
        for m in yoy_quarters:
            if (m.get("rev_yoy") or 0) > 0 and (m.get("profit_yoy") or 0) > 0:
                consecutive_hits += 1
                max_consecutive = max(max_consecutive, consecutive_hits)
            else:
                consecutive_hits = 0
        four_quarters_hit = max_consecutive >= 4

        # ── 3. QoQ 双增检测 ──
        qoq_quarters = [m for m in metrics if m.get("rev_qoq") is not None]
        recent_qoq_hits = sum(
            1 for m in qoq_quarters[-4:]
            if (m.get("rev_qoq") or 0) > 0 and (m.get("profit_qoq") or 0) > 0
        )

        # ── 4. 存货异动 ──
        inv_ratios = [m.get("inventory_revenue_ratio") for m in metrics if m.get("inventory_revenue_ratio")]
        inv_trend = "stable"
        if len(inv_ratios) >= 4:
            recent_avg = sum(r for r in inv_ratios[-2:] if r) / max(1, sum(1 for r in inv_ratios[-2:] if r))
            earlier_avg = sum(r for r in inv_ratios[-6:-2] if r) / max(1, sum(1 for r in inv_ratios[-6:-2] if r))
            if earlier_avg > 0 and recent_avg / earlier_avg > 1.3:
                inv_trend = "rising_alert"  # 存货占比上升 >30%, 可能滞销
            elif earlier_avg > 0 and recent_avg / earlier_avg < 0.7:
                inv_trend = "declining"  # 存货减少, 可能供不应求

        # ── 5. 合同负债异动 ──
        cl_values = [m.get("contract_liability", 0) or 0 for m in metrics]
        cl_trend = "stable"
        if len(cl_values) >= 4 and cl_values[-1] > 0:
            recent_avg = sum(cl_values[-2:]) / 2
            earlier_avg = sum(cl_values[-6:-2]) / max(1, len(cl_values[-6:-2]))
            if earlier_avg > 0 and recent_avg / earlier_avg > 1.5:
                cl_trend = "surging"  # 合同负债暴增 → 订单充沛
            elif earlier_avg > 0 and recent_avg / earlier_avg > 1.2:
                cl_trend = "rising"
            elif earlier_avg > 0 and recent_avg / earlier_avg < 0.7:
                cl_trend = "declining_alert"  # 合同负债骤降 → 订单萎缩

        # ── 6. OCF 健康度 ──
        ocf_ratios = [m.get("ocf_profit_ratio") for m in metrics if m.get("ocf_profit_ratio") is not None]
        ocf_health = "healthy"  # >0.8 健康, 0.5-0.8 一般, <0.5 差
        if ocf_ratios:
            recent_ocf = sum(r for r in ocf_ratios[-4:] if r) / max(1, sum(1 for r in ocf_ratios[-4:] if r))
            if recent_ocf < 0.5:
                ocf_health = "poor"
            elif recent_ocf < 0.8:
                ocf_health = "moderate"

        # ── 综合判决 ──
        score = 0
        flags = []
        if scissor_pass:
            score += 30
            flags.append("✅ 剪刀差为正: 利润率扩张中")
        else:
            flags.append(f"⚠️ 剪刀差为负({latest_gap}%), 利润增速跑输营收")

        if four_quarters_hit:
            score += 35
            flags.append(f"✅ 四连击: 连续{max_consecutive}季度营收+利润同比双增")
        else:
            flags.append(f"⚠️ 未达四连击(当前连续{max_consecutive}季度)")

        if recent_qoq_hits >= 3:
            score += 15
            flags.append(f"✅ 近4季度中{recent_qoq_hits}季度环比双增")

        if inv_trend == "declining":
            score += 10
            flags.append("✅ 存货占比下降: 供不应求信号")
        elif inv_trend == "rising_alert":
            score -= 15
            flags.append("🚨 存货占比急升: 可能滞销或囤货")

        if cl_trend in ("surging", "rising"):
            score += 10
            flags.append(f"✅ 合同负债{cl_trend}: 在手订单充沛")
        elif cl_trend == "declining_alert":
            score -= 15
            flags.append("🚨 合同负债骤降: 新订单萎缩")

        if ocf_health == "poor":
            score -= 20
            flags.append("🚨 经营现金流/利润 < 0.5: 利润含金量低")
        elif ocf_health == "moderate":
            score -= 5
            flags.append("⚠️ 经营现金流/利润偏低")

        # 判决
        if score >= 60:
            verdict = "PASS"
        elif score >= 35:
            verdict = "CAUTION"
        else:
            verdict = "FAIL"

        return {
            "verdict": verdict,
            "score": score,
            "flags": flags,
            "scissor": {
                "latest_gap_pct": latest_gap,
                "scissor_quarters_count": len(scissor_quarters),
                "is_expanding": scissor_pass,
            },
            "momentum": {
                "consecutive_yoy_hits": max_consecutive,
                "four_quarters_hit": four_quarters_hit,
                "recent_qoq_hits": recent_qoq_hits,
            },
            "inventory_trend": inv_trend,
            "contract_liability_trend": cl_trend,
            "ocf_health": ocf_health,
            "metrics": metrics,
        }

    # ═══ 工具 ═════════════════════════════════════

    @staticmethod
    def _pct(current: float, base: float) -> Optional[float]:
        """计算百分比变化"""
        if base and base != 0:
            return round((current - base) / abs(base) * 100, 2)
        return None

    # ═══ 基类要求 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        return await super().load_context(ctx)

    def build_prompt(self, ctx): return ""

    async def stream(self, ctx): yield "streaming not implemented"
