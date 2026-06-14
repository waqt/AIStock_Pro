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
        """人力资本审计 — 聚焦核心人物背景/学术地位 + 公司人才待遇

        较贵 (Web Search × 3 + LLM Pro), 仅按需调用。
        """
        logger.info(f"[StockAuditor] Human capital audit: {code} {name}")

        if not name:
            fundamentals = await self.data_loader.load_fundamentals([code])
            name = fundamentals.get(code, {}).get("name", code)

        # 加载研发费用数据 (用于佐证人才投入)
        rd_info = {}
        try:
            fin = await self.data_loader.load_financial_statements(code, periods=4)
            quarters = fin.get("quarters", [])
            if quarters:
                avg_rd = sum(float(q.get("rd_expense", 0) or 0) for q in quarters[:4]) / max(len(quarters[:4]), 1)
                avg_revenue = sum(float(q.get("revenue", 0) or 0) for q in quarters[:4]) / max(len(quarters[:4]), 1)
                rd_info = {
                    "rd_expense_avg_yi": round(avg_rd / 1e8, 2),
                    "rd_intensity_pct": round(avg_rd / avg_revenue * 100, 1) if avg_revenue > 0 else None,
                }
        except Exception:
            pass

        # 1. 三维并行 Web 搜索
        queries = {
            "core_people": f"{name} {code} 创始人 董事长 总经理 CTO 核心团队 履历 教育背景",
            "academic_status": f"{name} {code} 院士 学术带头人 教授 研发负责人 学术背景",
            "talent_treatment": f"{name} {code} 薪酬水平 员工待遇 人均薪酬 福利 研发人员待遇",
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
        rd_block = ""
        if rd_info:
            rd_block = f"\n### 研发投入佐证\n最近4季平均研发费用: {rd_info.get('rd_expense_avg_yi', '?')}亿/季\n研发费用率: {rd_info.get('rd_intensity_pct', '?')}%\n"

        prompt = f"""你是顶级人才评估专家。请从以下两个维度分析 {name} ({code}) 的人力资本质量。

## 搜索结果

### 核心人物背景
{_j(search_results.get("core_people", []), ensure_ascii=False)}

### 学术地位与行业声望
{_j(search_results.get("academic_status", []), ensure_ascii=False)}

### 人才待遇
{_j(search_results.get("talent_treatment", []), ensure_ascii=False)}
{rd_block}
## 分析要求

聚焦两个核心维度：

### 维度一: 核心人物背景与学术地位
评估创始人/董事长/总经理/CTO/研发负责人的:
- 学历背景 (是否名校/博士/海归)
- 学术地位 (院士/教授/行业标准制定者/学术论文)
- 行业声望 (是否行业协会负责人/国家项目带头人)
- 国际视野 (是否有海外留学/工作经历)

### 维度二: 公司人才待遇
- 薪酬水平: 人均薪酬 vs 行业均值
- 研发人员待遇: 研发人员薪酬/占比
- 人才吸引力: 能否吸引顶尖高校毕业生
- 研发投入佐证: 研发费用率 (如数据可用)
- 判断: 待遇是否有竞争力, 能否留住核心人才

## 输出 JSON
{{
  "verdict": "STRONG / ADEQUATE / WEAK / INSUFFICIENT_DATA",
  "score": 0-100,
  "highlights": ["亮点1", "亮点2"],
  "risks": ["风险1", "风险2"],
  "key_people": [
    {{"name": "姓名", "role": "职位", "background": "学历/履历摘要", "academic_status": "学术地位(如有)"}}
  ],
  "talent_assessment": {{
    "academic_depth": "学术深度评价(强/中/弱)",
    "compensation_level": "薪酬待遇评价(有竞争力/一般/偏低)",
    "rd_intensity_pct": {rd_info.get('rd_intensity_pct', 'null')},
    "talent_attraction": "人才吸引力评价",
    "key_personnel_risk": "关键人员依赖风险"
  }},
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

    # ═══ 新: b层补充 — FinancialStatement 原始元值 ══════

    async def _load_raw_financial(self, code: str) -> Dict[str, Any]:
        """b层补充: FinancialStatement 原始元值 (非亿元换算)"""
        fin = await self.data_loader.load_financial_statements(code, periods=1)
        quarters = fin.get("quarters", [])
        if not quarters:
            return {}
        q = quarters[0]
        return {
            "total_assets": float(q.get("total_assets", 0) or 0),
            "total_liabilities": float(q.get("total_liabilities", 0) or 0),
            "total_equity": float(q.get("total_equity", 0) or 0),
            "cash": float(q.get("cash", 0) or 0),
            "fixed_assets": float(q.get("fixed_assets", 0) or 0),
            "short_loan": float(q.get("short_loan", 0) or 0),
            "long_loan": float(q.get("long_loan", 0) or 0),
            "current_assets": float(q.get("current_assets", 0) or 0),
            "current_liabilities": float(q.get("current_liabilities", 0) or 0),
            "inventory": float(q.get("inventory", 0) or 0),
            "accounts_receivable": float(q.get("accounts_receivable", 0) or 0),
            "accounts_payable": float(q.get("accounts_payable", 0) or 0),
            "contract_liability": float(q.get("contract_liability", 0) or 0),
        }

    # ═══ 新: c层 — 财务指标加载 ═════════════════════════

    async def _load_financial_indicators(self, code: str) -> Dict[str, Any]:
        """c层: 从 financial_indicators SQLite 加载财务指标"""
        try:
            from app.domain.quant.engine import indicator_store
            row = indicator_store.get_financial_latest(code)
            if not row:
                return {}
            KEYS = [
                "roic_pct", "gross_margin_pct", "net_margin_pct", "operating_margin_pct",
                "avg_rev_yoy_4q", "rev_yoy_ttm", "revenue_4q_yi",
                "revenue_acceleration", "scissor_gap", "scissor_is_expanding",
                "gross_margin_trend", "gross_margin_chg_pp", "operating_leverage",
                "inflection_quality_label", "ocf_to_profit_label",
            ]
            return {k: row.get(k) for k in KEYS if row.get(k) is not None}
        except Exception as e:
            logger.warning(f"[StockAuditor] {code}: failed to load fin_indicators: {e}")
            return {}

    # ═══ 新: 股票信息 / 价格 / 历史数据加载 ════════════

    async def _load_stock_info(self, code: str) -> Dict[str, Any]:
        """加载总股本/流通股本"""
        from app.framework.database.session import async_session
        from app.models.models import StockMaster
        async with async_session() as db:
            row = await db.get(StockMaster, code)
            if not row:
                return {}
            return {
                "total_shares": float(row.total_shares or 0),
                "float_shares": float(row.float_shares or 0),
            }

    async def _load_latest_price(self, code: str) -> Optional[float]:
        """从 MarketData 读最新收盘价"""
        from app.framework.database.session import async_session
        from app.models.models import MarketData
        from sqlalchemy import select
        async with async_session() as db:
            row = await db.execute(
                select(MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(1)
            )
            price = row.scalar()
            return float(price) if price else None

    async def _load_pe_history(self, code: str, lookback_days: int = 1095) -> list:
        """加载近 3 年 PE 历史序列 (需 StockValuation 有 pe_ttm)"""
        from app.framework.database.session import async_session
        from app.models.models import StockValuation, MarketData
        from sqlalchemy import select
        async with async_session() as db:
            val = await db.get(StockValuation, code)
            if not val or not val.pe_ttm:
                return []
            rows = await db.execute(
                select(MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(lookback_days)
            )
            prices = [r[0] for r in rows.all() if r[0] and r[0] > 0]
            if not prices:
                return []
            eps_est = prices[0] / val.pe_ttm
            return [round(p / eps_est, 2) for p in reversed(prices)]

    async def _load_pb_history(self, code: str, lookback_days: int = 1095) -> list:
        """加载近 3 年 PB 历史序列"""
        from app.framework.database.session import async_session
        from app.models.models import StockValuation, MarketData, StockMaster
        from sqlalchemy import select
        async with async_session() as db:
            val = await db.get(StockValuation, code)
            if not val or not val.pb or not val.mcap_yi:
                return []
            info = await db.get(StockMaster, code)
            shares = float(info.total_shares or 0) if info else 0
            if shares <= 0:
                return []
            bvps = (val.mcap_yi * 1e8) / shares / val.pb
            if bvps <= 0:
                return []
            rows = await db.execute(
                select(MarketData.close)
                .where(MarketData.stock_code == code)
                .order_by(MarketData.trade_date.desc())
                .limit(lookback_days)
            )
            prices = [r[0] for r in rows.all() if r[0] and r[0] > 0]
            return [round(p / bvps, 2) for p in reversed(prices)]

    async def _load_industry_pe_median(self, industry: str) -> Optional[float]:
        """查询同行业 PE TTM 中位数"""
        if not industry:
            return None
        try:
            import numpy as np
            from app.framework.database.session import async_session
            from app.models.models import StockValuation, StockMaster
            from sqlalchemy import select, collate
            async with async_session() as db:
                rows = await db.execute(
                    select(StockValuation.pe_ttm)
                    .join(StockMaster, collate(StockMaster.stock_code, 'utf8mb4_unicode_ci') == StockValuation.stock_code)
                    .where(StockMaster.industry == industry)
                    .where(StockValuation.pe_ttm.isnot(None))
                    .where(StockValuation.pe_ttm > 0)
                )
                pe_values = [r[0] for r in rows.all()]
            return float(np.median(pe_values)) if pe_values else None
        except Exception as e:
            logger.warning(f"[StockAuditor] industry_pe_median failed: {e}")
            return None

    # ═══ 恢复: a+b 层数据加载 (原 _load_valuation_data) ══

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

    # ═══════════════════════════════════════════════════
    #   audit_valuation — 估值定价 (VALUATION_REGISTRY)
    # ═══════════════════════════════════════════════════

    def _build_valuation_catalog(self, method: type) -> Dict[str, Any]:
        """构建单个估值方法的目录描述"""
        meta = {
            "name": method.name,
            "label": getattr(method, 'label', method.name),
            "category": getattr(method, 'category', ''),
            "description": getattr(method, 'description', ''),
            "output": getattr(method, 'output', []),
            "needs_fin_indicators": getattr(method, 'requires_financial_indicators', False),
            "needs_market_data": getattr(method, 'requires_market_data', False),
        }
        manual = self._MANUAL_PARAMS.get(method.name)
        if manual:
            meta["manual_params"] = manual
        return meta

    # 需要 LLM 提供前向假设参数的方法清单
    _MANUAL_PARAMS = {
        "three_stage_growth": {
            "high_growth_rate": {"label": "高增期营收增速(%)", "default": 25.0, "desc": "Stage1(3年)年化营收增速"},
            "terminal_growth_rate": {"label": "永续增速(%)", "default": 4.0, "desc": "永续增长率"},
            "wacc": {"label": "折现率(%)", "default": 10.0, "desc": "加权平均资本成本"},
        },
        "scissor_inflection": {
            "phase_assumption": {"label": "剪刀差阶段假设", "default": "improving", "desc": "improving/stable/declining"},
        },
        "dol_adjusted": {
            "forward_growth": {"label": "前向营收增速(%)", "default": None, "desc": "预期未来营收增速(使用DB数据时自动填充)"},
        },
        "rev_growth_framework": {
            "phase1_growth": {"label": "高增期增速(%)", "default": 20.0, "desc": "Stage1年化营收增速"},
            "terminal_growth": {"label": "终端增速(%)", "default": 4.0, "desc": "永续增长率"},
        },
        "growth_peg": {
            "expected_growth": {"label": "预期EPS增速(%)", "default": None, "desc": "默认使用eps_growth_3y"},
        },
        "rnpv": {
            "rnd_type": {"label": "研发类型", "default": "moderate", "desc": "innovative(创新药)/moderate(创新仿制)/hybrid(仿制药)"},
        },
        "ps_valuation": {
            "ps_multiple": {"label": "目标PS倍数", "default": 3.0, "desc": "市销率目标倍数"},
        },
    }

    async def audit_valuation(self, code: str, name: str = "") -> Dict[str, Any]:
        """估值定价 — LLM 选择估值方法 + VALUATION_REGISTRY 执行计算

        数据流: a) 基本面 + b) 8Q TTM + c) 财务指标 → LLM 选方法 → 系统执行
        """
        logger.info(f"[StockAuditor] Valuation audit: {code} {name}")

        # 1. 加载 a+b 数据
        val_data = await self._load_valuation_data(code)
        fund = val_data["fundamentals"]
        ttm = val_data["ttm"]
        if not name:
            name = fund.get("name", code)

        # 2. 加载 b层补充 + c层财务指标 + 股票信息 + 最新价
        raw_fin = await self._load_raw_financial(code)
        fin_ind = await self._load_financial_indicators(code)
        stock_info = await self._load_stock_info(code)
        current_price = await self._load_latest_price(code)

        # 3. 构建 VALUATION_REGISTRY 目录 (排除 valuation_health)
        from app.domain.quant.valuation import VALUATION_REGISTRY

        catalog = {}
        for m_name, cls in VALUATION_REGISTRY.items():
            if m_name == "valuation_health":
                continue
            catalog[m_name] = self._build_valuation_catalog(cls)

        # 4. LLM 规划
        price_str = f"{current_price:.2f}" if current_price else "未知"
        plan_prompt = self._build_valuation_plan_prompt(
            name, code, fund, ttm, fin_ind, stock_info, price_str, catalog
        )

        try:
            plan_text = await self.provider.chat_pro(plan_prompt, max_tokens=4096, timeout=180)
            plan = self._parse_json(plan_text)
            if not isinstance(plan, dict):
                raise ValueError("Invalid plan JSON")
        except Exception as e:
            logger.warning(f"[StockAuditor] Valuation planning LLM failed: {e}")
            return {"code": code, "name": name, "audit_type": "valuation",
                    "verdict": "ERROR", "error": f"Planning failed: {e}"}

        # 5. 执行所选方法
        computed = await self._execute_valuation(
            plan, code, val_data, raw_fin, fin_ind, stock_info, current_price, catalog
        )

        selected = [m.get("method", "") for m in plan.get("chosen_methods", [])]
        return {
            "code": code,
            "stock_name": name,
            "audit_type": "valuation",
            "current_price": current_price,
            "valuation_plan": selected,
            "computed": computed,
            "summary": self._build_valuation_summary(computed),
        }

    def _build_valuation_plan_prompt(
        self, name: str, code: str, fund: dict, ttm: dict,
        fin_ind: dict, stock_info: dict, price_str: str, catalog: dict
    ) -> str:
        """构建估值规划提示词 (LLM 选择方法 + 参数)"""
        # 按是否需要手动参数分组
        auto_methods = []
        manual_methods = []
        for m_name, meta in catalog.items():
            entry = f"  - {meta['label']}({m_name}): {meta['description']}"
            if meta.get("manual_params"):
                entry += "\n    参数:"
                for p_name, p_info in meta["manual_params"].items():
                    entry += f" {p_info['label']}(默认{p_info['default']})"
                manual_methods.append(entry)
            else:
                auto_methods.append(entry)

        methods_block = "### 无需输入 (自动计算)\n" + "\n".join(auto_methods)
        if manual_methods:
            methods_block += "\n\n### 需 LLM 提供假设参数\n" + "\n".join(manual_methods)

        fin_ind_block = _j({k: v for k, v in fin_ind.items() if v is not None}, indent=2) if fin_ind else "暂无"

        return f"""你是估值专家。请为 {name}({code}) 选择合适的估值方法。

## 公司数据

当前股价: {price_str}
行业: {fund.get("industry", "未知")}
PE_TTM: {fund.get("pe_ttm", "N/A")} | PB: {fund.get("pb", "N/A")}
市值: {fund.get("mcap_yi", "N/A")}亿
ROE: {fund.get("roe", "N/A")}% | 股息率: {fund.get("dividend_yield", "N/A")}%
EPS 增速(3Y): {fund.get("eps_growth_3y", "N/A")}%
TTM 营收: {ttm.get("revenue_yi", "N/A")}亿 | 利润: {ttm.get("profit_yi", "N/A")}亿
经营现金流: {ttm.get("ocf_yi", "N/A")}亿 | 研发: {ttm.get("rd_yi", "N/A")}亿
净债务: {ttm.get("net_debt_yi", "N/A")}亿 | 净资产: {ttm.get("total_equity_yi", "N/A")}亿
总股本: {stock_info.get("total_shares", "N/A")}股

## 财务指标参考
{fin_ind_block}

## 可用估值方法 (VALUATION_REGISTRY)

{methods_block}

## 要求

根据该公司行业特性和财务特征, 选择 1-2 种最合适的估值方法。
- 优先选择"无需输入"的方法 (自动从真实财务数据计算)
- 如需手动参数方法, 根据公司数据合理估计参数值
- EV/EBITDA 适用于重资产高折旧行业
- DDM 适用于稳定派息公司
- rNPV 适用于生物医药/创新药

## 输出 JSON
{{
  "chosen_methods": [
    {{
      "method": "pe_percentile",
      "rationale": "为什么选这个方法",
      "params": {{}}
    }}
  ],
  "preliminary_judgment": "一句话初步判断估值水平"
}}

参数方法可提供的参数见方法说明。自动方法 params 留空对象。
只输出JSON。"""

    async def _execute_valuation(
        self, plan: dict, code: str,
        val_data: dict, raw_fin: dict, fin_ind: dict,
        stock_info: dict, current_price: Optional[float],
        catalog: dict,
    ) -> Dict[str, Any]:
        """执行估值计算 — 使用 VALUATION_REGISTRY

        对 plan 中的每个 chosen_method, 加载数据后调 method.compute()
        """
        from app.domain.quant.valuation import VALUATION_REGISTRY

        fund = val_data["fundamentals"]
        ttm = val_data["ttm"]

        results = []
        weighted_prices = []

        # 懒加载缓存
        pe_history = None
        pb_history = None
        industry_pe_median = None

        for method_def in plan.get("chosen_methods", []):
            m_name = method_def.get("method", "")
            user_params = method_def.get("params", {})

            cls = VALUATION_REGISTRY.get(m_name)
            if not cls:
                logger.warning(f"[StockAuditor] Unknown method: {m_name}")
                results.append({"method": m_name, "error": f"Unknown method"})
                continue

            try:
                # 构建基础数据
                kwargs = {
                    **fund,                # pe_ttm, pb, mcap_yi, roe, ...
                    **ttm,                 # revenue_yi, profit_yi, ... (亿元)
                    **raw_fin,             # total_assets, cash, ... (元)
                    **stock_info,          # total_shares
                    **fin_ind,             # roic_pct, scissor_gap, ...
                }
                if current_price is not None:
                    kwargs["price"] = current_price

                # 注入方法默认参数 (仅 manual_params 中的)
                manual = self._MANUAL_PARAMS.get(m_name, {})
                for p_name, p_info in manual.items():
                    default = p_info.get("default")
                    if default is not None:
                        kwargs.setdefault(p_name, default)

                # 用户参数覆盖
                for k, v in user_params.items():
                    if v is not None:
                        kwargs[k] = v

                # 按需加载历史数据
                if getattr(cls, 'requires_market_data', False):
                    if pe_history is None:
                        pe_history = await self._load_pe_history(code)
                    if pb_history is None:
                        pb_history = await self._load_pb_history(code)
                    kwargs.setdefault("pe_history", pe_history or [])
                    kwargs.setdefault("pb_history", pb_history or [])

                # 按需加载行业 PE 中位数
                if "industry_pe_median" in getattr(cls, 'requires', []):
                    if industry_pe_median is None:
                        industry = fund.get("industry", "")
                        industry_pe_median = await self._load_industry_pe_median(industry)
                    kwargs["industry_pe_median"] = industry_pe_median

                # 执行计算
                output = cls.compute(**kwargs)
                if not output:
                    raise ValueError("Empty compute result")

                # 提取目标价和上行空间 (不同方法输出字段不同)
                target_price = self._extract_target_price(m_name, output)
                upside = None
                if target_price is not None and current_price and current_price > 0:
                    upside = round((target_price - current_price) / current_price * 100, 1)

                results.append({
                    "method": m_name,
                    "label": getattr(cls, 'label', m_name),
                    "output": output,
                    "target_price": target_price,
                    "upside_pct": upside,
                })
                if target_price is not None:
                    weighted_prices.append(target_price)

            except Exception as e:
                logger.warning(f"[StockAuditor] {m_name} failed: {e}")
                results.append({"method": m_name, "error": str(e)})

        # 简单平均目标价
        avg_target = round(sum(weighted_prices) / len(weighted_prices), 2) if weighted_prices else None

        return {
            "methods_used": results,
            "avg_target_price": avg_target,
        }

    @staticmethod
    def _extract_target_price(method: str, output: dict) -> Optional[float]:
        """从方法输出中提取目标价 (不同方法字段名不同)"""
        TARGET_FIELDS = {
            "gordon_growth": "ddm_value",
            "graham_number": "graham_number",
            "net_asset_value": "nav_per_share",
            "residual_income": "rim_value",
            "three_stage_growth": "three_stage_value",
            "scissor_inflection": "scissor_target_price",
            "dol_adjusted": "dol_target_price",
            "rev_growth_framework": "rgv_target_price",
            "growth_peg": "growth_peg_target_price",
            "rnpv": "rnpv_value",
            "fcf_yield": "implied_value",
            "pe_percentile": None,  # 无目标价
            "pb_percentile": None,
            "peg_analysis": None,
            "ev_ic": None,
            "industry_premium": None,
            "roic_spread": None,
            "quality_adjusted": None,
            "scenario_estimate": "weighted_target",
            "gm_multiple_adjust": "gm_target_price",
            "ps_valuation": None,  # 需结合营收
        }
        field = TARGET_FIELDS.get(method)
        if field:
            return output.get(field)
        # 兜底: 取第一个数值
        for v in output.values():
            if isinstance(v, (int, float)) and v and v > 0:
                return v
        return None

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

    ## 旧 _execute_valuation 已移除 — 替换为 async 版 (见上方 _execute_valuation 新定义)

    def _build_valuation_summary(self, computed: Dict) -> str:
        """生成估值摘要"""
        parts = []
        if computed.get("avg_target_price"):
            parts.append(f"平均目标价: {computed['avg_target_price']}")
        methods = computed.get("methods_used", [])
        valid = [m for m in methods if "error" not in m]
        if valid:
            prices = [m.get("target_price") for m in valid if m.get("target_price")]
            if prices:
                parts.append(f"方法数: {len(valid)}, 目标价区间: {min(prices)}-{max(prices)}")
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
