"""
StockAuditor V1.0 — 股票审计工具
不是 Pipeline Step，是独立工具，可被 Step 6 enrichment 阶段按需调用。

三个审计维度，每个由 LLM 自主规划分析路径、选择关注维度:
  - audit_financial:      财务状况审计 (LLM 从 8Q 财报 + 27 指标中自主发现风险)
  - audit_human_capital:  人力资本审计 (Web 搜索 + LLM 分析核心团队/人才能力)
  - audit_valuation:      估值定价 (LLM 选择估值方法 + 框架函数执行计算)
"""
import json as _json
from typing import Dict, Any, List, Optional
from decimal import Decimal
from app.framework.logger import logger
from app.domain.research.services.data_loader import data_loader


class _SafeEncoder(_json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _j(obj, **kw):
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return _json.dumps(obj, **kw)


class StockAuditor:
    """股票审计工具 — 单只股票多维度健康检查

    用法:
        auditor = StockAuditor()
        result = await auditor.audit_financial("688012")

    或在 Step 6 enrichment 中按需调用:
        summary = await auditor.audit_summary("688012")
    """

    def __init__(self, provider=None):
        self._provider = provider
        self.data_loader = data_loader

    # ── provider lazy init ────────────────────────────

    @property
    def provider(self):
        if self._provider is None:
            from app.framework.ai.providers.deepseek import DeepSeekProvider
            self._provider = DeepSeekProvider()
        return self._provider

    # ═══════════════════════════════════════════════════
    #   audit_financial — 财务健康审计
    # ═══════════════════════════════════════════════════

    async def audit_financial(self, code: str) -> Dict[str, Any]:
        """财务健康审计 — LLM 自主规划分析维度

        输入: 8Q 财报原始数据 + 27 个财务指标
        输出: LLM 自主决定的分析结论, 无预设维度
        """
        logger.info(f"[StockAuditor] Financial audit: {code}")

        # 1. 加载原始财报
        fin = await self.data_loader.load_financial_statements(code, periods=8)
        quarters = fin.get("quarters", [])
        if len(quarters) < 2:
            return {"code": code, "verdict": "INSUFFICIENT_DATA",
                    "reason": f"Only {len(quarters)} quarters available"}

        # 2. 加载 27 个财务指标
        from app.domain.quant.engine.financial_query_service import FinancialQueryService
        qs = FinancialQueryService()
        fin_indicators = await qs.query(code, indicators=None, raw_fields=None, latest_only=True)
        fin_indicators = fin_indicators or {}

        # 3. 加载基本面 (PE/PB/市值等)
        fundamentals = await self.data_loader.load_fundamentals([code])
        fund = fundamentals.get(code, {})

        # 4. 构建数据简报
        data_package = {
            "stock_code": code,
            "stock_name": fund.get("name", code),
            "industry": fund.get("industry", ""),
            "market_data": {
                "pe_ttm": fund.get("pe_ttm"),
                "pb": fund.get("pb"),
                "mcap_yi": fund.get("mcap_yi"),
                "roe": fund.get("roe"),
                "dividend_yield": fund.get("dividend_yield"),
            },
            "financial_indicators": fin_indicators,
            "quarters_count": len(quarters),
            "latest_quarter": quarters[0].get("report_date", "") if quarters else "",
            "quarters_summary": [{
                "report_date": q.get("report_date"),
                "revenue_yi": round(float(q.get("revenue", 0) or 0) / 1e8, 2),
                "profit_yi": round(float(q.get("profit", 0) or 0) / 1e8, 2),
                "op_cashflow_yi": round(float(q.get("op_cashflow", 0) or 0) / 1e8, 2),
                "gross_margin_pct": round(
                    (float(q.get("revenue", 0) or 0) - float(q.get("operate_cost", 0) or 0))
                    / float(q.get("revenue", 0) or 1) * 100, 1) if float(q.get("revenue", 0) or 0) > 0 else None,
                "rd_expense_yi": round(float(q.get("rd_expense", 0) or 0) / 1e8, 2),
                "inventory_yi": round(float(q.get("inventory", 0) or 0) / 1e8, 2),
                "contract_liability_yi": round(float(q.get("contract_liability", 0) or 0) / 1e8, 2),
            } for q in quarters[:8]],
        }

        prompt = f"""你是A股财务审计专家。请对以下公司进行财务健康审计。

根据提供的财务数据，自主决定分析维度 —— 你可以关注:
- 盈利质量 (毛利率趋势/ROIC/非经常性损益)
- 成长真实性 (营收 vs 利润 vs 经营现金流是否匹配)
- 财务健康 (库存/合同负债/应收账款/有息负债)
- 现金流质量 (OCF/利润比, 自由现金流)
- 资产质量 (固定资产/研发资本化)
- 排雷信号 (Beneish M-Score/剪刀差/存货激增)
- 任何你认为重要的其他维度

数据如下:
{_j(data_package, indent=2)}

## 输出要求
输出结构化JSON审计报告, 至少包含:
{{
  "verdict": "HEALTHY / CAUTION / RISK / INSUFFICIENT_DATA",
  "score": 0-100,
  "highlights": ["亮点1", "亮点2", ...],
  "risks": ["风险1", "风险2", ...],
  "dimensions_analyzed": [
    {{"name": "分析维度名", "finding": "发现", "verdict": "GOOD/NEUTRAL/BAD"}}
  ],
  "key_metrics": {{"你关注的指标名": 值, ...}},
  "summary": "一段总结 (50字以内)"
}}

只输出JSON, 不要其他文字。"""

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=180)
            result = self._parse_json(text)
            if isinstance(result, dict):
                result["code"] = code
                result["stock_name"] = fund.get("name", code)
                result["audit_type"] = "financial"
                logger.info(f"[StockAuditor] Financial {code}: verdict={result.get('verdict')}, score={result.get('score')}")
                return result
        except Exception as e:
            logger.warning(f"[StockAuditor] Financial audit LLM failed: {e}")

        return {"code": code, "audit_type": "financial", "verdict": "ERROR", "error": "LLM analysis failed"}

    # ═══════════════════════════════════════════════════
    #   audit_human_capital — 人力资本审计
    # ═══════════════════════════════════════════════════

    async def audit_human_capital(self, code: str, name: str = "") -> Dict[str, Any]:
        """人力资本审计 — LLM 从核心团队、人才能力等角度分析公司

        较贵 (Web Search × 3 + LLM Pro), 仅按需调用。
        """
        logger.info(f"[StockAuditor] Human capital audit: {code} {name}")

        if not name:
            fundamentals = await self.data_loader.load_fundamentals([code])
            name = fundamentals.get(code, {}).get("name", code)

        # 1. 三维并行 Web 搜索
        queries = {
            "core_team": f"{name} {code} 创始人 董事长 总经理 CTO 核心高管 履历 背景",
            "talent_capability": f"{name} {code} 研发团队 技术人员占比 人才 校园招聘",
            "culture_equity": f"{name} {code} 股权激励 员工持股 企业文化 管理风格",
        }
        search_results = {}
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=4):
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:300],
                })
            search_results[key] = items

        # 2. LLM 分析
        prompt = f"""你是一位顶级人才评估专家(猎头+组织心理学家+薪酬顾问)。请从人力资本角度分析 {name} ({code})。

## 搜索结果
### 核心团队信息
{_j(search_results.get("core_team", []), ensure_ascii=False)}

### 人才能力信息
{_j(search_results.get("talent_capability", []), ensure_ascii=False)}

### 文化与股权激励
{_j(search_results.get("culture_equity", []), ensure_ascii=False)}

## 分析要求
从人力资本角度评估这家公司, 自主决定分析维度:
- 核心团队质量 (创始人视野/高管履历/技术背景/行业经验)
- 人才密度与研发能力 (技术团队规模/人才吸引力/培养体系)
- 组织健康度 (股权激励/核心团队稳定性/管理层价值观)
- 人才风险 (关键人员依赖/继任计划/人才流失风险)
- 任何你认为重要的其他维度

## 输出 JSON
{{
  "verdict": "STRONG / ADEQUATE / WEAK / INSUFFICIENT_DATA",
  "score": 0-100,
  "highlights": ["亮点1", "亮点2"],
  "risks": ["风险1", "风险2"],
  "dimensions_analyzed": [
    {{"name": "分析维度", "finding": "发现", "verdict": "GOOD/NEUTRAL/BAD"}}
  ],
  "core_team_assessment": {{
    "founder_ceo": "创始人/CEO评价",
    "cto_tech_lead": "CTO/技术负责人评价",
    "team_experience": "团队整体行业经验评价"
  }},
  "talent_density": "人才密度评价",
  "key_personnel_risk": "关键人员风险 (如有)",
  "summary": "一段总结 (50字以内)"
}}

只输出JSON, 不要其他文字。搜索结果有限的字段填null, 不要编造。"""

        try:
            text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=240)
            result = self._parse_json(text)
            if isinstance(result, dict):
                result["code"] = code
                result["stock_name"] = name
                result["audit_type"] = "human_capital"
                logger.info(f"[StockAuditor] HumanCapital {code}: verdict={result.get('verdict')}, score={result.get('score')}")
                return result
        except Exception as e:
            logger.warning(f"[StockAuditor] Human capital LLM failed: {e}")

        return {"code": code, "name": name, "audit_type": "human_capital",
                "verdict": "ERROR", "error": "LLM analysis failed"}

    # ═══════════════════════════════════════════════════
    #   audit_valuation — 估值定价
    # ═══════════════════════════════════════════════════

    async def _load_valuation_data(self, code: str) -> Dict[str, Any]:
        """加载估值所需数据 (fundamentals + 8Q + TTM)"""
        fundamentals = await self.data_loader.load_fundamentals([code])
        fund = fundamentals.get(code, {})
        fin = await self.data_loader.load_financial_statements(code, periods=8)
        quarters = fin.get("quarters", [])
        ttm = self._compute_ttm(quarters)
        return {
            "fundamentals": fund,
            "quarters": quarters,
            "ttm": ttm,
        }

    async def audit_valuation(self, code: str, name: str = "") -> Dict[str, Any]:
        """估值定价 — LLM 选择估值方法 + 框架函数执行计算

        两步: LLM 规划 → 代码执行 → 返回结果
        """
        logger.info(f"[StockAuditor] Valuation audit: {code} {name}")

        # 1. 加载数据
        val_data = await self._load_valuation_data(code)
        fund = val_data["fundamentals"]
        ttm = val_data["ttm"]

        if not name:
            name = fund.get("name", code)

        # 2. 可用估值方法清单 (给 LLM 参考)
        from app.framework.finance import (
            pe_valuation, pb_valuation, ps_valuation,
            ev_ebitda_valuation, peg_valuation, fcf_yield_valuation,
            scenario_weighted,
            match_asset_type,
        )

        available_methods = [
            {"name": "pe_valuation", "desc": "市盈率估值: 目标价 = EPS × PE倍数",
             "params": {"eps": "每股收益", "pe_multiple": "目标PE倍数"},
             "适用": "盈利稳定可预测的企业"},
            {"name": "pb_valuation", "desc": "市净率估值: 目标价 = 每股净资产 × PB倍数",
             "params": {"book_per_share": "每股净资产", "pb_multiple": "目标PB倍数"},
             "适用": "金融/强周期底部企业"},
            {"name": "ps_valuation", "desc": "市销率估值: 目标价 = 每股营收 × PS倍数",
             "params": {"revenue_per_share": "每股营收", "ps_multiple": "目标PS倍数"},
             "适用": "高成长无利润/SaaS/创新药"},
            {"name": "ev_ebitda_valuation", "desc": "EV/EBITDA: 目标价 = (EBITDA×倍数-净债务)/总股本",
             "params": {"ebitda": "EBITDA(亿元)", "net_debt": "净债务(亿元)", "shares": "总股本(亿股)", "multiple": "目标倍数"},
             "适用": "重资产制造/折旧高的企业"},
            {"name": "peg_valuation", "desc": "PEG估值: 目标价 = EPS × 增速% × PEG",
             "params": {"eps": "每股收益", "growth_rate_pct": "盈利增速%", "peg_target": "目标PEG(默认1.0)"},
             "适用": "成长型企业"},
            {"name": "fcf_yield_valuation", "desc": "FCF收益率: 目标价 = FCF每股 / 目标收益率%",
             "params": {"fcf_per_share": "每股自由现金流", "target_yield_pct": "目标收益率%(默认5%)"},
             "适用": "现金牛(水电/高速/港口)"},
        ]

        # 4. LLM 规划: 选择方法 + 定参数
        plan_prompt = f"""你是估值专家。请为 {name} ({code}) 选择合适的估值方法并确定参数。

## 公司数据
{{
  "industry": "{fund.get('industry', '未知')}",
  "price": {fund.get('pe_ttm', 'N/A')},
  "pe_ttm": {fund.get('pe_ttm', 'N/A')},
  "pb": {fund.get('pb', 'N/A')},
  "mcap_yi": {fund.get('mcap_yi', 'N/A')},
  "roe": {fund.get('roe', 'N/A')},
  "dividend_yield": {fund.get('dividend_yield', 'N/A')},
  "eps_growth_3y": {fund.get('eps_growth_3y', 'N/A')},
  "ttm_revenue_yi": {ttm.get('revenue_yi')},
  "ttm_profit_yi": {ttm.get('profit_yi')},
  "ttm_op_cashflow_yi": {ttm.get('ocf_yi')},
  "total_shares_yi": {ttm.get('shares_yi')},
  "net_debt_yi": {ttm.get('net_debt_yi')}
}}

## 可用估值方法
{_j(available_methods, ensure_ascii=False, indent=2)}

## 要求
根据该公司行业特性和财务特征, 选择 1-2 种最合适的估值方法, 并提供参数。
选择逻辑: 优先匹配该公司所属行业常用的方法, 同时考虑其财务结构(是否盈利/是否高折旧/是否高成长)。

## 输出 JSON
{{
  "chosen_methods": [
    {{
      "method": "pe_valuation",
      "rationale": "为什么选这个方法",
      "params": {{"eps": 2.5, "pe_multiple": 20}},
      "weight": 0.6
    }}
  ],
  "scenario_analysis": {{
    "bull": {{"price": 100, "probability": 0.2, "assumption": "乐观情景假设"}},
    "base": {{"price": 80, "probability": 0.6, "assumption": "基准情景假设"}},
    "bear": {{"price": 50, "probability": 0.2, "assumption": "悲观情景假设"}}
  }},
  "price_current": null,
  "asset_type_suggestion": "根据行业和财务特征判断的资产类型"
}}

参数值使用合理估计。如果数据不足填 null。
只输出JSON。"""

        try:
            plan_text = await self.provider.chat_pro(plan_prompt, max_tokens=3072, timeout=180)
            plan = self._parse_json(plan_text)
            if not isinstance(plan, dict):
                raise ValueError("Invalid plan JSON")
        except Exception as e:
            logger.warning(f"[StockAuditor] Valuation planning LLM failed: {e}")
            return {"code": code, "name": name, "audit_type": "valuation",
                    "verdict": "ERROR", "error": f"Planning failed: {e}"}

        # 5. 执行计算
        computed = self._execute_valuation(plan, ttm)

        # 6. 组装结果
        return {
            "code": code,
            "stock_name": name,
            "audit_type": "valuation",
            "asset_type": plan.get("asset_type_suggestion", "unknown"),
            "valuation_plan": plan.get("chosen_methods", []),
            "computed": computed,
            "scenario_analysis": plan.get("scenario_analysis", {}),
            "summary": self._build_valuation_summary(computed),
        }

    # ═══════════════════════════════════════════════════
    #   组合审计
    # ═══════════════════════════════════════════════════

    async def audit_full(self, code: str, name: str = "") -> Dict[str, Any]:
        """全量审计 — financial + human_capital + valuation"""
        logger.info(f"[StockAuditor] Full audit: {code} {name}")

        financial = await self.audit_financial(code)

        # 并行执行 human_capital 和 valuation
        import asyncio
        hc_task = asyncio.create_task(self.audit_human_capital(code, name))
        val_task = asyncio.create_task(self.audit_valuation(code, name))
        human_capital = await hc_task
        valuation = await val_task

        return {
            "code": code,
            "stock_name": name or financial.get("stock_name", code),
            "audit_type": "full",
            "financial": financial,
            "human_capital": human_capital,
            "valuation": valuation,
            "overall_verdict": self._overall_verdict(financial, human_capital, valuation),
        }

    async def audit_summary(self, code: str) -> Dict[str, Any]:
        """轻量审计摘要 — 仅 financial + quick valuation, 不跑 expensive human capital

        供 Step 6 enrichment 阶段对候选池每只标的调用
        """
        financial = await self.audit_financial(code)
        valuation = await self.audit_valuation(code)
        return {
            "code": code,
            "audit_type": "summary",
            "financial_verdict": financial.get("verdict"),
            "financial_score": financial.get("score"),
            "valuation": valuation.get("computed"),
            "risks": financial.get("risks", []),
            "highlights": financial.get("highlights", []),
        }

    # ═══════════════════════════════════════════════════
    #   工具方法
    # ═══════════════════════════════════════════════════

    def _compute_ttm(self, quarters: List[Dict]) -> Dict[str, Any]:
        """计算 TTM 聚合数据"""
        if len(quarters) < 4:
            return {}

        recent = quarters[:4]
        revenue = sum(float(q.get("revenue", 0) or 0) for q in recent)
        profit = sum(float(q.get("profit", 0) or 0) for q in recent)
        ocf = sum(float(q.get("op_cashflow", 0) or 0) for q in recent)
        rd = sum(float(q.get("rd_expense", 0) or 0) for q in recent)
        cash = float(quarters[0].get("cash", 0) or 0)
        total_liab = float(quarters[0].get("total_liabilities", 0) or 0)
        total_equity = float(quarters[0].get("total_equity", 0) or 0)
        current_assets = float(quarters[0].get("current_assets", 0) or 0)
        current_liab = float(quarters[0].get("current_liabilities", 0) or 0)
        short_loan = float(quarters[0].get("short_loan", 0) or 0)
        long_loan = float(quarters[0].get("long_loan", 0) or 0)
        inventory = float(quarters[0].get("inventory", 0) or 0)
        accounts_recv = float(quarters[0].get("accounts_receivable", 0) or 0)
        accounts_pay = float(quarters[0].get("accounts_payable", 0) or 0)

        net_debt = (short_loan + long_loan) - cash

        return {
            "revenue_yi": round(revenue / 1e8, 2),
            "profit_yi": round(profit / 1e8, 2),
            "ocf_yi": round(ocf / 1e8, 2),
            "rd_yi": round(rd / 1e8, 2),
            "net_debt_yi": round(net_debt / 1e8, 2),
            "cash_yi": round(cash / 1e8, 2),
            "total_liab_yi": round(total_liab / 1e8, 2),
            "total_equity_yi": round(total_equity / 1e8, 2),
            "current_ratio": round(current_assets / current_liab, 2) if current_liab > 0 else None,
            "inventory_yi": round(inventory / 1e8, 2),
            "accounts_recv_yi": round(accounts_recv / 1e8, 2),
            "accounts_pay_yi": round(accounts_pay / 1e8, 2),
        }

    def _execute_valuation(self, plan: Dict, ttm: Dict) -> Dict[str, Any]:
        """执行 LLM 规划的估值计算"""
        from app.framework.finance.valuation import (
            pe_valuation, pb_valuation, ps_valuation,
            ev_ebitda_valuation, peg_valuation, fcf_yield_valuation,
            scenario_weighted,
        )

        results = []
        weighted_prices = []

        for method_def in plan.get("chosen_methods", []):
            method = method_def.get("method", "")
            params = method_def.get("params", {})
            weight = method_def.get("weight", 1.0)

            try:
                if method == "pe_valuation":
                    price = pe_valuation(
                        eps=float(params.get("eps", 0)),
                        pe_multiple=float(params.get("pe_multiple", 15)),
                    )
                elif method == "pb_valuation":
                    price = pb_valuation(
                        book_per_share=float(params.get("book_per_share", 0)),
                        pb_multiple=float(params.get("pb_multiple", 1.5)),
                    )
                elif method == "ps_valuation":
                    price = ps_valuation(
                        revenue_per_share=float(params.get("revenue_per_share", 0)),
                        ps_multiple=float(params.get("ps_multiple", 3)),
                    )
                elif method == "ev_ebitda_valuation":
                    price = ev_ebitda_valuation(
                        ebitda=float(params.get("ebitda", 0)),
                        net_debt=float(params.get("net_debt", 0)),
                        shares=float(params.get("shares", 1)),
                        multiple=float(params.get("multiple", 10)),
                    )
                elif method == "peg_valuation":
                    price = peg_valuation(
                        eps=float(params.get("eps", 0)),
                        growth_rate_pct=float(params.get("growth_rate_pct", 15)),
                        peg_target=float(params.get("peg_target", 1.0)),
                    )
                elif method == "fcf_yield_valuation":
                    price = fcf_yield_valuation(
                        fcf_per_share=float(params.get("fcf_per_share", 0)),
                        target_yield_pct=float(params.get("target_yield_pct", 5.0)),
                    )
                else:
                    continue

                results.append({
                    "method": method,
                    "params": params,
                    "target_price": price,
                    "weight": weight,
                })
                weighted_prices.append(price * weight)
            except Exception as e:
                logger.warning(f"[StockAuditor] Valuation method {method} failed: {e}")
                results.append({"method": method, "error": str(e)})

        # 情景分析
        scenarios = plan.get("scenario_analysis", {})
        scenario_result = {}
        if scenarios.get("bull") and scenarios.get("base") and scenarios.get("bear"):
            try:
                scenario_result = scenario_weighted(
                    bull=float(scenarios["bull"]["price"]),
                    base=float(scenarios["base"]["price"]),
                    bear=float(scenarios["bear"]["price"]),
                )
            except Exception as e:
                logger.warning(f"[StockAuditor] Scenario analysis failed: {e}")

        # 加权平均目标价
        total_weight = sum(m.get("weight", 1.0) for m in results if "error" not in m)
        avg_target = round(sum(weighted_prices) / total_weight, 2) if total_weight > 0 else None

        return {
            "methods_used": results,
            "weighted_avg_target": avg_target,
            "scenario_weighted": scenario_result if scenario_result else None,
        }

    def _build_valuation_summary(self, computed: Dict) -> str:
        """生成估值摘要"""
        parts = []
        if computed.get("weighted_avg_target"):
            parts.append(f"加权平均目标价: {computed['weighted_avg_target']}")
        if computed.get("scenario_weighted"):
            sw = computed["scenario_weighted"]
            parts.append(f"情景加权: {sw.get('weighted_price')} "
                         f"(区间 {sw.get('range', ['?','?'])[0]}-{sw.get('range', ['?','?'])[1]})")
            if sw.get("asymmetry"):
                parts.append(f"不对称性: {sw['asymmetry']}")
        return " | ".join(parts) if parts else "估值数据不足"

    def _overall_verdict(self, financial: Dict, hc: Dict, valuation: Dict) -> str:
        """综合 verdict"""
        scores = []
        for d in [financial, hc, valuation]:
            v = d.get("verdict", "")
            if v in ("HEALTHY", "STRONG"):
                scores.append(1)
            elif v in ("CAUTION", "ADEQUATE"):
                scores.append(0)
            elif v in ("RISK", "WEAK"):
                scores.append(-1)
        if not scores:
            return "INSUFFICIENT_DATA"
        avg = sum(scores) / len(scores)
        if avg >= 0.5:
            return "GOOD"
        elif avg >= -0.3:
            return "NEUTRAL"
        else:
            return "RISK"

    @staticmethod
    def _parse_json(text: str) -> Optional[Dict]:
        """解析 LLM 输出的 JSON (兼容 markdown 包裹)"""
        import re
        if isinstance(text, dict):
            return text
        if isinstance(text, str):
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if m:
                try:
                    return _json.loads(m.group(0))
                except _json.JSONDecodeError:
                    pass
        return None
