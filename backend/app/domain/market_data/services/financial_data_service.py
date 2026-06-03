"""
Financial Raw Data Service — 数据中心: 原始财务数据查询服务

三层定位:
  此服务 + FinancialQueryService(量化指标层) + FinancialIndicator(算子层)
  = 完整财务数据服务体系

职责:
  1. 提供原始财报字段的完整元数据 (数据字典 / 分类 / 单位 / 说明)
  2. 灵活的数据查询 (单股/多股/指定字段/日期范围/多期对比)
  3. LLM prompt 注入支持 (format_catalog_for_prompt)
  4. 周期对比 (同比 / 环比 / TTM 汇总)

不涉及:
  - 衍生计算 (Layer 2 衍生指标由 FinancialQueryService 处理)
  - 指标持久化 (财务量化指标由 indicator_store 管理)
"""
from typing import List, Dict, Optional, Any
from datetime import date
from app.framework.logger import logger


# ═══ 原始财报字段元数据 (21 项) ═══════════════════════
# 唯一真相源: FinancialStatement ORM 模型 (models.py)

RAW_FIELD_METADATA: Dict[str, Dict[str, Any]] = {
    # ── 利润表 (Income Statement) ──
    "revenue": {
        "label": "营业收入",
        "unit": "元",
        "category": "利润表",
        "statement": "income",
        "description": "企业主营业务收入, 不含营业外收入。"
                       "增长驱动=量×价, 判断景气度核心指标。",
        "remarks": "a股季报为单季度数据, 计算TTM需累加近4季",
    },
    "parent_profit": {
        "label": "归母净利润",
        "unit": "元",
        "category": "利润表",
        "statement": "income",
        "description": "归属于母公司股东的净利润, 扣除非经常性损益前。"
                       "净利润=收入-成本-费用+其他收益-所得税。",
        "remarks": "与扣非净利润的差距反映非经常性损益比重",
    },
    "operate_cost": {
        "label": "营业成本",
        "unit": "元",
        "category": "利润表",
        "statement": "income",
        "description": "主营业务对应的直接成本 (材料+人工+制造费用)。"
                       "毛利率=(收入-成本)/收入, 是最核心的盈利质量指标。",
        "remarks": "不含销售/管理/研发/财务费用",
    },
    "sale_expense": {
        "label": "销售费用",
        "unit": "元",
        "category": "利润表",
        "statement": "income",
        "description": "销售环节产生的费用 (广告/渠道/销售人员薪酬)。"
                       "销售费用率上升可能意味着竞争加剧/获客成本上升。",
        "remarks": "",
    },
    "manage_expense": {
        "label": "管理费用",
        "unit": "元",
        "category": "利润表",
        "statement": "income",
        "description": "行政管理费用 (管理人员薪酬/办公/折旧)。"
                       "管理费用率下降说明规模效应显现。",
        "remarks": "新准则下不含研发费用 (已单独列示)",
    },
    "rd_expense": {
        "label": "研发费用",
        "unit": "元",
        "category": "利润表",
        "statement": "income",
        "description": "研发投入 (资本化+费用化合计中的费用化部分)。"
                       "研发费用率=RD/收入, >10%为高研发投入型公司。",
        "remarks": "资本化的研发支出在资产负债表中, 不在本字段",
    },
    # ── 现金流量表 (Cash Flow) ──
    "op_cashflow": {
        "label": "经营性现金流净额",
        "unit": "元",
        "category": "现金流量表",
        "statement": "cashflow",
        "description": "经营活动产生的现金流量净额。"
                       "持续>净利润为佳, 持续<净利润需警惕。",
        "remarks": "是利润质量的'照妖镜', 比净利润更难造假",
    },
    # ── 资产负债表 — 资产 (Balance Sheet - Assets) ──
    "inventory": {
        "label": "存货",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "原材料+在产品+产成品。存货增速 > 收入增速 → 滞销预警。",
        "remarks": "存货跌价准备会直接减少利润",
    },
    "contract_liability": {
        "label": "合同负债(预收账款)",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "已收款但尚未履约的合同负债 (原'预收账款')。"
                       "持续增长说明产品供不应求, 是未来收入的先行指标。",
        "remarks": "新收入准则下预收账款改为合同负债",
    },
    "accounts_receivable": {
        "label": "应收账款",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "已发货但未收回的货款。应收/收入比上升说明回款能力下降。"
                       "周转天数(DSO)=AR/收入×365。",
        "remarks": "应收账款坏账准备会直接减少利润",
    },
    "total_assets": {
        "label": "总资产",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "资产总计 = 流动资产 + 非流动资产。"
                       "总资产扩张反映企业规模增长。",
        "remarks": "与总负债对比得到资产负债率",
    },
    "current_assets": {
        "label": "流动资产合计",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "一年内可变现的资产 (货币资金+应收+存货+其他)。"
                       "流动比率=流动资产/流动负债, >1为安全。",
        "remarks": "",
    },
    "fixed_assets": {
        "label": "固定资产",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "厂房/设备/土地等长期资产 (扣除累计折旧)。"
                       "固定资产周转率=收入/平均固定资产, 衡量产能利用效率。",
        "remarks": "重资产公司的折旧对利润影响大",
    },
    "cash": {
        "label": "货币资金",
        "unit": "元",
        "category": "资产负债表(资产)",
        "statement": "balance",
        "description": "现金及现金等价物。是企业偿债能力的最后保障。"
                       "货币资金/总负债 > 30% 为安全。",
        "remarks": "需注意'存贷双高'异常信号",
    },
    # ── 资产负债表 — 负债 (Balance Sheet - Liabilities) ──
    "total_liabilities": {
        "label": "总负债",
        "unit": "元",
        "category": "资产负债表(负债)",
        "statement": "balance",
        "description": "负债合计 = 流动负债 + 非流动负债。"
                       "资产负债率=负债/总资产, 制造业通常40-60%。",
        "remarks": "结合有息负债率看真实偿债压力",
    },
    "current_liabilities": {
        "label": "流动负债合计",
        "unit": "元",
        "category": "资产负债表(负债)",
        "statement": "balance",
        "description": "一年内需偿还的负债 (短期借款+应付+其他)。"
                       "与流动资产对比得到流动比率。",
        "remarks": "",
    },
    "short_loan": {
        "label": "短期借款",
        "unit": "元",
        "category": "资产负债表(负债)",
        "statement": "balance",
        "description": "一年内到期的银行借款。短期借款/货币资金 > 1 有短期偿债压力。",
        "remarks": "是流动负债中有息的部分",
    },
    "long_loan": {
        "label": "长期借款",
        "unit": "元",
        "category": "资产负债表(负债)",
        "statement": "balance",
        "description": "一年以上到期的银行借款。反映企业的长期融资能力。",
        "remarks": "结合在建工程判断借款用途",
    },
    "accounts_payable": {
        "label": "应付账款",
        "unit": "元",
        "category": "资产负债表(负债)",
        "statement": "balance",
        "description": "已收货但尚未支付给供应商的款项。"
                       "应付账款/收入反映对上游供应商的占款能力。",
        "remarks": "应付款增加说明产业链地位强 (占用上游资金)",
    },
    "noncurrent_liab_1year": {
        "label": "一年内到期非流动负债",
        "unit": "元",
        "category": "资产负债表(负债)",
        "statement": "balance",
        "description": "原属长期负债但将在一年内到期的部分。"
                       "是隐性短期偿债压力, 常被忽略。",
        "remarks": "短期借款+本项=真实的短期有息负债",
    },
    # ── 资产负债表 — 权益 (Balance Sheet - Equity) ──
    "total_equity": {
        "label": "总权益(净资产)",
        "unit": "元",
        "category": "资产负债表(权益)",
        "statement": "balance",
        "description": "股东权益合计 = 总资产 - 总负债。"
                       "ROE=净利润/平均权益, 是衡量股东回报的核心指标。",
        "remarks": "包含股本/资本公积/未分配利润等",
    },
}

# 按财务报表分类组织的分组名
CATEGORY_GROUPS: Dict[str, str] = {
    "利润表": "income",
    "现金流量表": "cashflow",
    "资产负债表(资产)": "balance_assets",
    "资产负债表(负债)": "balance_liabilities",
    "资产负债表(权益)": "balance_equity",
}

# 元数据字段 (非业务数据)
META_FIELDS = ["stock_code", "report_date", "report_type", "announce_date"]


class FinancialRawDataService:
    """原始财务数据查询服务 — 数据中心模块

    提供数据字典、灵活查询、周期对比、LLM prompt 注入四大能力。
    不涉及指标计算，不依赖 FINANCIAL_REGISTRY。
    """

    # ═══ 数据字典 ═══════════════════════════════════

    @staticmethod
    def get_catalog() -> Dict[str, Any]:
        """返回完整数据字典 (名称/单位/分类/说明)

        Returns:
            {
                "fields": {field_name: {label, unit, category, description, ...}, ...},
                "by_category": {"利润表": [field_names], ...},
                "meta_fields": [...],
                "summary": {"total_fields": 21, "categories": [...]}
            }
        """
        fields = {}
        for name, meta in RAW_FIELD_METADATA.items():
            fields[name] = {
                "label": meta["label"],
                "unit": meta["unit"],
                "category": meta["category"],
                "statement": meta.get("statement", ""),
                "description": meta.get("description", ""),
                "remarks": meta.get("remarks", ""),
            }

        # 按分类分组
        by_category: Dict[str, List[str]] = {}
        for name, meta in RAW_FIELD_METADATA.items():
            cat = meta["category"]
            by_category.setdefault(cat, []).append(name)

        return {
            "fields": fields,
            "by_category": by_category,
            "meta_fields": META_FIELDS.copy(),
            "summary": {
                "total_fields": len(RAW_FIELD_METADATA),
                "categories": list(by_category.keys()),
            },
        }

    @staticmethod
    def format_catalog_for_prompt() -> str:
        """格式化数据字典为纯文本, 供注入 LLM prompt 使用"""
        catalog = FinancialRawDataService.get_catalog()
        lines = ["## 原始财报数据字典 (FinancialStatement)", ""]
        lines.append("可通过 raw_fields 参数请求以下字段。单位为**元**（注意非亿元）。")
        lines.append("数据最新在前 (newest-first), 季报频率。")
        lines.append("")

        for cat, field_names in catalog["by_category"].items():
            lines.append(f"### {cat}")
            lines.append("")
            for name in sorted(field_names):
                meta = catalog["fields"][name]
                lines.append(
                    f"  - `{name}`: {meta['label']} (单位={meta['unit']})"
                )
                lines.append(f"    {meta['description']}")
                if meta.get("remarks"):
                    lines.append(f"    📌 {meta['remarks']}")
                lines.append("")

        lines.append("### 元数据字段 (自动附带)")
        lines.append(f"  - `stock_code`: 股票代码")
        lines.append(f"  - `report_date`: 报告期 (如 2026-03-31)")
        lines.append(f"  - `report_type`: 报告类型 (Q=季报, M=中报, A=年报)")
        lines.append(f"  - `announce_date`: 公告日期")
        lines.append("")

        lines.append("### 注意事项")
        lines.append("- 所有金额单位为**元**，LLM 需自行转换亿元显示")
        lines.append("- 数据方向: newest-first, quarters[0]=最新")
        lines.append("- 季报数据为单季度, TTM=近4季求和")
        lines.append("- 同比增长率需同期对比 ( quarters[i] vs quarters[i+4] )")
        lines.append("")

        return "\n".join(lines)

    # ═══ 查询 ═══════════════════════════════════════

    @staticmethod
    async def query(
        code: str,
        fields: Optional[List[str]] = None,
        periods: int = 4,
        latest_only: bool = True,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        """查询单只股票的原始财务数据

        Args:
            code: 6位股票代码
            fields: 需要返回的字段列表, None=全部字段
            periods: 返回的季度数 (默认4, 最大20)
            latest_only: True=只返回最新一期; False=返回多期
            start_date: 起始日期 (如 "2025-01-01"), 覆盖 periods
            end_date: 结束日期 (如 "2026-03-31"), 默认最新

        Returns:
            latest_only=True: {stock_code, report_date, <field>: value, ...}
            latest_only=False: {stock_code, periods: [{report_date, <field>: value, ...}]}
        """
        from app.models.models import FinancialStatement
        from sqlalchemy import select, desc
        from app.framework.database.session import async_session

        # 构建查询
        stmt = (
            select(FinancialStatement)
            .where(FinancialStatement.stock_code == code)
            .order_by(desc(FinancialStatement.report_date))
        )

        if start_date:
            stmt = stmt.where(FinancialStatement.report_date >= start_date)
        if end_date:
            stmt = stmt.where(FinancialStatement.report_date <= end_date)
        if not (start_date or end_date):
            stmt = stmt.limit(periods)

        async with async_session() as db:
            res = await db.execute(stmt)
            rows = res.scalars().all()

        if not rows:
            return {"stock_code": code, "error": "no_data"}

        # 确定返回字段 (默认全部)
        all_raw_fields = set(RAW_FIELD_METADATA.keys())
        selected_fields = set(fields) if fields else all_raw_fields
        # 确保元数据字段总包含
        meta_fields_set = {"report_date"}

        def _row_to_dict(r) -> Dict[str, Any]:
            d = {"report_date": str(r.report_date)}
            for f in selected_fields:
                val = getattr(r, f, None)
                if val is not None:
                    d[f] = float(val)
                else:
                    d[f] = None
            return d

        if latest_only:
            result = {"stock_code": code}
            result.update(_row_to_dict(rows[0]))
            return result
        else:
            return {
                "stock_code": code,
                "periods": [_row_to_dict(r) for r in rows],
            }

    @staticmethod
    async def query_bulk(
        codes: List[str],
        fields: Optional[List[str]] = None,
        periods: int = 4,
        latest_only: bool = True,
    ) -> Dict[str, Any]:
        """批量查询多只股票的最新或历史数据

        Returns:
            latest_only=True:
                {"results": [{stock_code, report_date, <field>: value}, ...]}
            latest_only=False:
                {"results": [{stock_code, periods: [...]}, ...]}
        """
        import asyncio

        tasks = [
            FinancialRawDataService.query(
                code, fields=fields, periods=periods, latest_only=latest_only
            )
            for code in codes
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid = []
        errors = []
        for code, r in zip(codes, results):
            if isinstance(r, Exception):
                errors.append({"stock_code": code, "error": str(r)})
            elif r.get("error"):
                errors.append({"stock_code": code, "error": r["error"]})
            else:
                valid.append(r)

        return {
            "results": valid,
            "errors": errors,
            "summary": {"total": len(codes), "success": len(valid), "failed": len(errors)},
        }

    @staticmethod
    async def compare(
        code: str,
        fields: Optional[List[str]] = None,
        periods: int = 8,
    ) -> Dict[str, Any]:
        """周期对比: 同比 + 环比 + TTM 汇总

        Args:
            code: 6位股票代码
            fields: 需要对比的字段 (属于 RAW_FIELD_METADATA)
            periods: 用于对比的季度数, 至少5期才可算同比

        Returns:
            {stock_code, comparisons: [
                {report_date, <field>: value,
                 <field>_qoq: 环比变化率(%),
                 <field>_yoy: 同比变化率(%)}, ...
            ], ttm: {revenue_ttm, profit_ttm, ...}}
        """
        data = await FinancialRawDataService.query(
            code, fields=fields, periods=periods, latest_only=False
        )
        if data.get("error"):
            return {"stock_code": code, "error": data["error"]}

        all_periods = data.get("periods", [])

        # 确定对比字段
        if fields:
            compare_fields = [f for f in fields if f in RAW_FIELD_METADATA]
        else:
            compare_fields = list(RAW_FIELD_METADATA.keys())[:10]  # 默认前10个

        comparisons = []
        for i, p in enumerate(all_periods):
            entry = {"report_date": p["report_date"]}
            for f in compare_fields:
                cur = p.get(f)
                entry[f] = cur

                # 环比: vs 上一季 (i+1)
                if i + 1 < len(all_periods):
                    prev_q = all_periods[i + 1].get(f)
                    if cur is not None and prev_q is not None and prev_q != 0:
                        entry[f"{f}_qoq"] = round(
                            (cur - prev_q) / abs(prev_q) * 100, 2
                        )
                    else:
                        entry[f"{f}_qoq"] = None

                # 同比: vs 上年同季 (i+4)
                if i + 4 < len(all_periods):
                    prev_y = all_periods[i + 4].get(f)
                    if cur is not None and prev_y is not None and prev_y != 0:
                        entry[f"{f}_yoy"] = round(
                            (cur - prev_y) / abs(prev_y) * 100, 2
                        )
                    else:
                        entry[f"{f}_yoy"] = None

            comparisons.append(entry)

        # TTM 汇总 (近4季)
        ttm = {}
        if len(all_periods) >= 4:
            ttm_window = all_periods[:4]
            for f in ["revenue", "parent_profit", "operate_cost", "op_cashflow",
                       "sale_expense", "manage_expense", "rd_expense"]:
                vals = [p.get(f) or 0 for p in ttm_window]
                ttm[f"{f}_ttm"] = round(sum(vals), 2)

        # YoY 对比 (最近完整四季 vs 前一年同四季)
        if len(all_periods) >= 8:
            cur_4q = [p for p in all_periods[:4] if p.get("revenue") is not None]
            prev_4q = [p for p in all_periods[4:8] if p.get("revenue") is not None]
            if cur_4q and prev_4q:
                for f in ["revenue", "parent_profit"]:
                    cur_sum = sum(p.get(f, 0) or 0 for p in cur_4q)
                    prev_sum = sum(p.get(f, 0) or 0 for p in prev_4q)
                    if prev_sum != 0:
                        ttm[f"{f}_ttm_yoy"] = round(
                            (cur_sum - prev_sum) / abs(prev_sum) * 100, 2
                        )

        return {
            "stock_code": code,
            "comparisons": comparisons,
            "ttm": ttm,
        }
