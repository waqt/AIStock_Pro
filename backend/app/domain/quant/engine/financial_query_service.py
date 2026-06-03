"""
Financial Query Service — Agent 可调用的财务数据查询与组装服务

设计目的:
  build_financial_data_view() 返回固定的结构化视图, Agent 只能被动消费。
  本服务提供更灵活的模式:
    1. 暴露数据字典给 Agent (指标注册表 + 原始字段清单)
    2. Agent 自主决定需要哪些指标/字段
    3. 根据 Agent 请求按需组装数据

用法 (Agent 内部):
    svc = FinancialQueryService()
    catalog = svc.get_catalog()           # 查看全部可用数据 (已缓存)
    data = await svc.query(               # 按需组装
        code="688012",
        indicators=["roic_pct", "revenue_yoy"],
        raw_fields=["revenue", "rd_expense"]
    )
    # → {"roic_pct": 18.5, "revenue_yoy": 12.3, "revenue": 1250000000, "rd_expense": 150000000}

API 端点:
    GET  /api/quant/financial-indicators/catalog   — 数据字典 (已缓存)
    POST /api/quant/financial-indicators/query     — 按需组装
"""
from typing import List, Dict, Optional, Any
from app.framework.logger import logger


# ═══ 输出字段单位标注 — 从 FINANCIAL_REGISTRY 自动推导 ═══
# 不再使用手写 FIELD_ANNOTATIONS, 改为从 cls.meta()['output_fields'] 读取
# 每注册一个新指标, 字段元数据自动出现在 catalog 中

# 原始字段单位 (FinancialStatement 表)
RAW_FIELD_UNITS: Dict[str, str] = {k: "元" for k in [
    "revenue", "parent_profit", "operate_cost", "sale_expense",
    "manage_expense", "rd_expense", "op_cashflow",
    "total_assets", "current_assets", "fixed_assets",
    "inventory", "contract_liability", "accounts_receivable", "cash",
    "total_liabilities", "current_liabilities", "short_loan",
    "long_loan", "accounts_payable", "noncurrent_liab_1year",
    "total_equity",
]}


# ═══ 衍生指标注册表 (Layer 2: 查询时实时计算, 不持久化) ═══
# 简单比率/周转类指标, 从已有财务字段直接计算, 无需预存

DERIVED_INDICATORS: Dict[str, Dict] = {
    "ar_turnover_days": {
        "label": "应收账款周转天数(DSO)",
        "description": "应收账款周转天数 = 平均应收账款 / 营业收入(TTM) × 365。"
                       "衡量回款速度, 缩短说明客户不敢拖欠（卡位权增强）, 拉长说明地位下降。",
        "judgment": "<30天=强; 30~60=正常; 60~90=偏长; >90=弱",
        "unit": "天",
        "category": "health",
        "indicator_type": "moat",
        "requires": ["accounts_receivable", "revenue"],
    },
    "fixed_asset_turnover": {
        "label": "固定资产周转率",
        "description": "营业收入(TTM) / 平均固定资产。"
                       "衡量产能利用效率, 扩张后维持或提升说明产能有效利用, 下降说明产能闲置。",
        "judgment": ">5=高(轻资产高周转); 2~5=正常; <2=低(重资产或产能闲置)",
        "unit": "倍",
        "category": "profitability",
        "indicator_type": "prosperity",
        "requires": ["revenue", "fixed_assets"],
    },
    "sga_ratio": {
        "label": "销售管理费用率",
        "description": "(销售费用+管理费用) / 营业收入(TTM)。"
                       "竞争加剧→销售费用率上升吞噬利润; 高认证壁垒→SG&A占比低且稳定。",
        "judgment": "<10%=低(壁垒高); 10~20%=正常; >20%=偏高(竞争激烈)",
        "unit": "%",
        "category": "health",
        "indicator_type": "moat",
        "requires": ["sale_expense", "manage_expense", "revenue"],
    },
    "ocf_to_revenue_ratio": {
        "label": "经营现金流/营收比",
        "description": "经营性现金流净额(TTM) / 营业收入(TTM)。"
                       "衡量每元收入的现金创造能力, 高说明收款好、利润质量高。",
        "judgment": ">20%=强; 10~20%=正常; <10%=偏弱; <0=亏损",
        "unit": "%",
        "category": "health",
        "indicator_type": "both",
        "requires": ["op_cashflow", "revenue"],
    },
}

# ═══ 原始财务数据字段字典 ═══════════════════════════

FINANCIAL_RAW_FIELDS: Dict[str, str] = {
    "revenue": "营业收入",
    "parent_profit": "归母净利润",
    "operate_cost": "营业成本",
    "sale_expense": "销售费用",
    "manage_expense": "管理费用",
    "rd_expense": "研发费用",
    "op_cashflow": "经营性现金流",
    "total_assets": "总资产",
    "current_assets": "流动资产",
    "fixed_assets": "固定资产",
    "inventory": "存货",
    "contract_liability": "合同负债（预收账款）",
    "accounts_receivable": "应收账款",
    "cash": "货币资金",
    "total_liabilities": "总负债",
    "current_liabilities": "流动负债合计",
    "short_loan": "短期借款",
    "long_loan": "长期借款",
    "accounts_payable": "应付账款",
    "noncurrent_liab_1year": "一年内到期非流动负债",
    "total_equity": "总权益（净资产）",
}


# ═══ 缓存 ═══════════════════════════════════════════

_catalog_cache: Optional[Dict[str, Any]] = None


class FinancialQueryService:
    """财务数据查询与组装服务 (catalog 已缓存, 多次调用不重复构建)"""

    @staticmethod
    def get_catalog() -> Dict[str, Any]:
        """返回完整数据字典: 注册指标 + 原始字段 (首次调用后缓存)"""
        global _catalog_cache
        if _catalog_cache is not None:
            return _catalog_cache

        from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY

        indicators = {}
        for name, cls in FINANCIAL_REGISTRY.items():
            meta = cls.meta()
            per_field = meta.get("output_fields", {})
            fields_with_meta = []
            for f in cls.output:
                finfo = per_field.get(f, {})
                fields_with_meta.append({
                    "field": f,
                    "unit": finfo.get("unit", "?"),
                    "meaning": finfo.get("meaning", ""),
                    "is_text": finfo.get("is_text", False),
                })

            indicators[name] = {
                "label": meta["label"],
                "description": meta["description"],
                "judgment": meta["judgment"],
                "category": meta["category"],
                "indicator_type": meta["indicator_type"],
                "output_fields": fields_with_meta,
                "output_field_names": meta["output"],
                "text_output": meta.get("text_output", []),
                "requires_raw_fields": meta["requires"],
            }

        # 衍生指标 (Layer 2)
        derived = {}
        for name, dmeta in DERIVED_INDICATORS.items():
            derived[name] = {
                "label": dmeta["label"],
                "description": dmeta["description"],
                "judgment": dmeta["judgment"],
                "unit": dmeta.get("unit", "?"),
                "category": dmeta.get("category", "other"),
                "indicator_type": dmeta.get("indicator_type", "both"),
                "requires_raw_fields": dmeta.get("requires", []),
            }

        # 原始字段附加单位信息
        raw_fields_with_meta = {}
        for f, label in FINANCIAL_RAW_FIELDS.items():
            raw_fields_with_meta[f] = {
                "label": label,
                "unit": RAW_FIELD_UNITS.get(f, "?"),
            }

        _catalog_cache = {
            "indicators": indicators,
            "derived_indicators": derived,
            "raw_fields": raw_fields_with_meta,
            "summary": {
                "total_indicators": len(indicators),
                "total_derived": len(derived),
                "total_raw_fields": len(FINANCIAL_RAW_FIELDS),
                "categories": _group_by_category(indicators),
            },
        }
        return _catalog_cache

    @staticmethod
    def format_catalog_for_prompt() -> str:
        """格式化数据字典为文本, 供注入 Agent prompt"""
        catalog = FinancialQueryService.get_catalog()
        lines = ["## 可用财务数据字典", ""]

        lines.append("你可通过 query_financial_data(code, indicators=[...], raw_fields=[...]) 获取数据。")
        lines.append("以下是可用指标和字段: ")
        lines.append("")

        lines.append("### Layer 1 — 已注册财务指标（通过 indicators 参数请求，预计算持久化）")
        lines.append("")
        for name, meta in sorted(catalog["indicators"].items()):
            lines.append(f"**{name}** ({meta['label']}) — {meta['description']}")
            lines.append(f"  - 分类: {meta['category']} | 判断: {meta['judgment']}")
            lines.append(f"  - 产出字段:")
            for fmeta in meta["output_fields"]:
                unit_str = f"单位={fmeta['unit']}" if fmeta['unit'] != '?' else ""
                tag = f" ({unit_str})" if unit_str else ""
                lines.append(f"    * `{fmeta['field']}` — {fmeta['meaning']}{tag}")
            lines.append("")

        lines.append("### Layer 2 — 衍生指标（通过 indicators 参数请求，实时计算）")
        lines.append("")
        lines.append("以下指标由原始财务字段实时计算，无需预计算。")
        lines.append("")
        for name, dmeta in sorted(catalog.get("derived_indicators", {}).items()):
            lines.append(f"**{name}** ({dmeta['label']}) — {dmeta['description']}")
            lines.append(f"  - 分类: {dmeta['category']} | 判断: {dmeta['judgment']} | 单位: {dmeta['unit']}")
            lines.append(f"  - 依赖字段: {', '.join(f'`{f}`' for f in dmeta['requires_raw_fields'])}")
            lines.append("")

        lines.append("### 原始财务数据字段（通过 raw_fields 参数请求）")
        lines.append("")
        for f, finfo in sorted(catalog["raw_fields"].items()):
            lines.append(f"  - `{f}`: {finfo['label']} (单位={finfo['unit']})")
        lines.append("")

        lines.append("### 使用示例")
        lines.append("```python")
        lines.append('# 获取ROIC和营收增长')
        lines.append('data = query_financial_data("688012", indicators=["roic_pct", "revenue_yoy"])')
        lines.append('# → {"stock_code": "688012", "report_date": "2026-03-31", "roic_pct": 18.5, "revenue_yoy": 12.3}')
        lines.append("")
        lines.append('# 获取原始财务字段')
        lines.append('data = query_financial_data("688012", raw_fields=["revenue", "rd_expense"])')
        lines.append('# → {"stock_code": "688012", "report_date": "2026-03-31", "revenue": 1250000000, "rd_expense": 150000000}')
        lines.append("")
        lines.append('# 获取多个报告期的趋势数据')
        lines.append('data = query_financial_data("688012", indicators=["roic_pct"], latest_only=False)')
        lines.append('# → {"stock_code": "688012", "periods": [{"report_date": "...", "roic_pct": 18.5}, ...]}')
        lines.append("```")
        lines.append("")

        lines.append("### 注意")
        lines.append("- 原始财务字段单位为 **元**（非亿元），LLM 需自行转换")
        lines.append("- `roic_pct=18.5` 表示 18.5%，不是 0.185")
        lines.append("- `roic=0.185` 表示小数形式，不是百分比")
        lines.append("- `m_score=-2.5` 表示 -2.5 分，非百分比")

        return "\n".join(lines)

    @staticmethod
    async def query(
        code: str,
        indicators: Optional[List[str]] = None,
        raw_fields: Optional[List[str]] = None,
        periods: int = 4,
        latest_only: bool = True,
    ) -> Dict[str, Any]:
        """按需组装财务数据

        Args:
            code: 股票代码 (6位)
            indicators: 需要的注册指标名称列表, None=不请求指标
            raw_fields: 需要的原始字段列表, None=不请求原始字段
            periods: 读取的季度数 (用于指标计算)
            latest_only: True=只返回最新报告期; False=返回全部请求报告期

        Returns:
            latest_only=True:  {stock_code, report_date, <field>: value, ...}
            latest_only=False: {stock_code, periods: [{report_date, <field>: value, ...}]}
        """
        from app.domain.quant.engine import indicator_store

        # ── SQLite 缓存优先: 仅 latest_only 模式可用 ──
        if latest_only and (indicators or raw_fields):
            cached = indicator_store.get_financial_latest(code)
            if cached:
                # 检查请求的所有指标是否都在缓存中
                all_available = True
                if indicators:
                    # 获取指标的输出字段映射
                    from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY
                    requested_fields = set(indicators)
                    if raw_fields:
                        requested_fields.update(raw_fields)
                    # 按字段名检查
                    for f in requested_fields:
                        if f not in cached:
                            all_available = False
                            break

                if all_available:
                    result = {"stock_code": code, "report_date": cached.get("report_date", "")}
                    for key in (indicators or []) + (raw_fields or []):
                        if key in cached:
                            result[key] = cached[key]
                    return result

        # ── 缓存不足, 从原始数据重新计算 ──
        from app.domain.research.services.financial_data_loader import load_financials

        fin = await load_financials(code, periods=max(periods, 8), mode="local")
        quarters = fin.get("quarters", [])

        if not quarters:
            return {"stock_code": code, "error": "no_financial_data"}

        if latest_only:
            return FinancialQueryService._assemble_single(
                code, quarters, indicators, raw_fields)
        else:
            return FinancialQueryService._assemble_multi(
                code, quarters, indicators, raw_fields)

    # ── 衍生指标计算 ─────────────────────────────────────

    @staticmethod
    def _compute_derived(name: str, quarters: list) -> Optional[float]:
        """实时计算衍生指标 (Layer 2), 不涉及 SQLite 存储"""
        def _ttm(idx: str) -> float:
            return sum(float(q.get(idx, 0) or 0) for q in quarters[:4])

        def _avg_ttm(idx: str) -> float:
            """平均余额: (本期末 + 上期末) / 2"""
            if len(quarters) < 5:
                return _ttm(idx) / 4  # 不足5季, 用TTM均值近似
            cur = float(quarters[0].get(idx, 0) or 0)
            prev = float(quarters[4].get(idx, 0) or 0)
            return (cur + prev) / 2

        try:
            if name == "ar_turnover_days":
                rev_ttm = _ttm("revenue")
                ar_avg = _avg_ttm("accounts_receivable")
                if rev_ttm and ar_avg is not None:
                    return round(ar_avg / (rev_ttm / 365), 1)

            elif name == "fixed_asset_turnover":
                rev_ttm = _ttm("revenue")
                fa_avg = _avg_ttm("fixed_assets")
                if rev_ttm and fa_avg:
                    return round(rev_ttm / fa_avg, 2)

            elif name == "sga_ratio":
                rev_ttm = _ttm("revenue")
                sga = _ttm("sale_expense") + _ttm("manage_expense")
                if rev_ttm:
                    return round(sga / rev_ttm * 100, 1)

            elif name == "ocf_to_revenue_ratio":
                rev_ttm = _ttm("revenue")
                ocf_ttm = _ttm("op_cashflow")
                if rev_ttm:
                    return round(ocf_ttm / rev_ttm * 100, 1)

        except Exception:
            pass
        return None

    # ── 内部 ──────────────────────────────────────────────

    @staticmethod
    def _assemble_single(
        code: str, quarters: List[Dict],
        indicator_names: Optional[List[str]],
        raw_field_names: Optional[List[str]],
    ) -> Dict[str, Any]:
        """组装单期数据 (最新报告期), 支持持久化+衍生指标"""
        from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY

        result = {"stock_code": code, "report_date": quarters[0].get("report_date", "")[:10]}

        if indicator_names:
            # 分离持久化指标 vs 衍生指标
            persistent = [n for n in indicator_names if n in FINANCIAL_REGISTRY]
            derived = [n for n in indicator_names if n in DERIVED_INDICATORS]

            # 持久化指标 (Layer 1)
            for name in persistent:
                cls = FINANCIAL_REGISTRY.get(name)
                if cls:
                    try:
                        output = cls.compute(quarters)
                        if isinstance(output, dict):
                            result.update(output)
                    except Exception as e:
                        logger.warning(f"[FinQuery] {code}: {name} failed: {e}")

            # 衍生指标 (Layer 2, 实时计算)
            for name in derived:
                val = FinancialQueryService._compute_derived(name, quarters)
                result[name] = val

        if raw_field_names and quarters:
            for f in raw_field_names:
                if f in quarters[0]:
                    result[f] = quarters[0].get(f)

        return result

    @staticmethod
    def _assemble_multi(
        code: str, quarters: List[Dict],
        indicator_names: Optional[List[str]],
        raw_field_names: Optional[List[str]],
    ) -> Dict[str, Any]:
        """组装多期数据 (每个报告期一条), 支持持久化+衍生指标"""
        from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY

        persistent = [n for n in (indicator_names or []) if n in FINANCIAL_REGISTRY]
        derived = [n for n in (indicator_names or []) if n in DERIVED_INDICATORS]

        periods_data = []
        for i in range(len(quarters) - 3):
            window = quarters[i:]
            rpt_date = window[0].get("report_date", "")[:10]
            entry = {"report_date": rpt_date}

            # 持久化指标 (Layer 1)
            if persistent:
                for name in persistent:
                    cls = FINANCIAL_REGISTRY.get(name)
                    if cls:
                        try:
                            output = cls.compute(window)
                            if isinstance(output, dict):
                                entry.update(output)
                        except Exception:
                            pass

            # 衍生指标 (Layer 2, 实时计算)
            if derived:
                for name in derived:
                    entry[name] = FinancialQueryService._compute_derived(name, window)

            if raw_field_names and window:
                for f in raw_field_names:
                    if f in window[0]:
                        entry[f] = window[0].get(f)

            periods_data.append(entry)

        return {"stock_code": code, "periods": periods_data}


def _group_by_category(indicators: Dict) -> Dict[str, List[str]]:
    """按 category 分组指标名称"""
    groups: Dict[str, List[str]] = {}
    for name, meta in indicators.items():
        cat = meta.get("category", "other")
        groups.setdefault(cat, []).append(name)
    return groups
