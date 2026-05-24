"""
GlobalCapexScanner V4.0 — 全球前瞻景气度扫描专家
单一职责: 扫描海外巨头(MAG7)财报电话会资本开支计划, 识别全球科技投资趋势
输出: capex_signals + hot_sectors + 全球景气方向
"""
import asyncio
import json as _json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(_json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def _j(obj, **kw):
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return _json.dumps(obj, **kw)


class GlobalCapexScanner(ResearchAgent):
    """全球 CapEx 扫描仪 V4.0 — 前瞻景气度, 自上而下"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "GlobalCapexScanner"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "")

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider"}

        logger.info(f"[{self.name}] Scanning global capex signals"
                    + (f" for: {industry}" if industry else " (broad)"))

        # 1. 多角度搜索 MAG7 CapEx
        search_data = await self._multi_angle_search(industry)

        # 2. LLM 分析 CapEx 流向
        result = await self._synthesize_capex_signals(industry, search_data)

        result["agent"] = self.name
        result["sources_count"] = search_data.get("total_results", 0)
        return result

    # ═══ 多角度搜索 ═════════════════════════════

    async def _multi_angle_search(self, industry: str) -> Dict:
        """4 个角度并行搜索全球 CapEx 信号"""
        if industry:
            queries = {
                "mag7": f"MAG7 Microsoft Meta Google Amazon capex 2026 AI infrastructure spending billions",
                "hyperscaler": f"hyperscaler datacenter capital expenditure 2026 {industry} cloud",
                "semicon": f"NVIDIA TSMC semiconductor equipment capex 2026 {industry} expansion",
                "supply": f"{industry} global supply chain investment capacity expansion 2026",
            }
        else:
            queries = {
                "mag7": "MAG7 Microsoft Meta Google Amazon Apple capex guidance 2026 AI spending",
                "hyperscaler": "hyperscaler datacenter infrastructure capital expenditure billions 2026",
                "semicon": "NVIDIA TSMC ASML semiconductor capex equipment orders 2026",
                "supply": "global tech supply chain reshoring capacity investment 2026",
            }

        results = {}
        total = 0
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=4):
                items.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:300],
                })
            results[key] = items
            total += len(items)

        results["total_results"] = total
        return results

    # ═══ LLM 综合分析 ═════════════════════════════

    async def _synthesize_capex_signals(self, industry: str, search: Dict) -> Dict:
        """LLM 将搜索数据综合为 CapEx 景气信号"""
        focus = f"聚焦 {industry} 相关领域" if industry else "全局扫描所有科技领域"

        prompt = f"""你是全球科技产业首席策略师。{focus}。基于以下 MAG7 资本开支数据和供应链情报, 输出全球科技投资景气度判断。

## MAG7 财报/CapEx 搜索结果
{_j(search.get("mag7", []))}

## 超大规模云商 CapEx
{_j(search.get("hyperscaler", []))}

## 半导体设备/产能
{_j(search.get("semicon", []))}

## 供应链投资
{_j(search.get("supply", []))}

## 输出要求: 纯 JSON
{{
  "global_summary": "全球科技 CapEx 核心结论 (2-3句子)",
  "capex_signals": [
    {{
      "sector": "领域名 (如: AI数据中心/先进封装/HBM/光通信)",
      "signal": "ACCELERATING/STABLE/DECELERATING",
      "magnitude": "CapEx 规模估算 (亿美元, 如搜索中有)",
      "growth_yoy": "YoY增速% (估)",
      "key_drivers": "核心驱动因素",
      "mega_cap_source": "MAG7/其他/混合 — 哪类巨头在投",
      "timeline": "预计持续到何时",
      "confidence": "HIGH/MEDIUM/LOW — 依据搜索结果质量"
    }}
  ],
  "hot_sectors": [
    {{
      "name": "最受益赛道名",
      "capex_intensity": 10,
      "reason": "为什么直接受益于上述 CapEx 流向",
      "a_stock_theme": "A股对应主题 (如: 光模块/先进封装设备/半导体材料)"
    }}
  ],
  "divergence_alerts": [
    "任何 CapEx 计划与实际出货数据的背离点 (如搜索结果中有)"
  ],
  "forward_looking": "6-12个月前瞻: 哪些环节可能超预期/低于预期"
}}

评分标准:
- capex_intensity: 1-10, CapEx 流入强度, 10=核心受益环节
- signal: ACCELERATING=加速, STABLE=稳定, DECELERATING=减速
- confidence: 搜索结果充分→HIGH, 有限→MEDIUM, 极少→LOW"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=4096), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                signals = result.get("capex_signals", [])
                sectors = result.get("hot_sectors", [])
                logger.info(
                    f"[{self.name}] Generated: {len(signals)} capex signals, "
                    f"{len(sectors)} hot sectors")
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Analysis timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Analysis failed: {e}")

        return {"error": "LLM analysis failed", "raw_search": search}

    # ═══ Macro Report Synthesis ═════════════════════

    async def synthesize_macro_report(self) -> Dict:
        """读取 DB 结构化宏观数据 + Web 搜索定性变量 → LLM 综合 → macro_report.json"""
        import os, time as _time
        from datetime import datetime as dt, timedelta

        # 1. 读取 DB 数据
        from app.framework.database.session import async_session
        from app.models.models import ExchangeRate, MacroHistory
        from sqlalchemy import select, func

        db_data = {}
        async with async_session() as db:
            er_rows = await db.execute(select(ExchangeRate))
            for r in er_rows.scalars().all():
                db_data[r.code] = {"rate": r.rate, "biz_date": str(r.biz_date) if r.biz_date else None}

            # 趋势数据: 最近3个值的趋势
            for code in ["US10YT", "CN10YT", "CN_PMI_MFG", "CN_PMI_NONMFG", "CN_LPR1Y"]:
                mh_rows = await db.execute(
                    select(MacroHistory.obs_date, MacroHistory.value)
                    .where(MacroHistory.code == code)
                    .order_by(MacroHistory.obs_date.desc()).limit(6))
                vals = [(str(r[0]), r[1]) for r in mh_rows.all()]
                if vals:
                    db_data[f"{code}_trend"] = vals

        # 2. Web 搜索定性变量
        search_results = {}
        queries = {
            "liquidity": "美联储缩表 QT 全球流动性 央行资产负债表 2026年5月",
            "geopolitics": "芯片出口管制 中美关税 地缘政治 供应链 2026",
            "china_policy": "中国 新质生产力 产业政策 专项债 制造业投资 2026",
        }
        for key, query in queries.items():
            items = []
            for r in await self.data_loader.search_web(query, num=3):
                items.append({"title": r.get("title",""), "snippet": r.get("snippet","")[:200]})
            search_results[key] = items

        # 3. LLM 合成
        db_summary = _j(db_data, ensure_ascii=False)
        search_summary = _j(search_results, ensure_ascii=False)

        prompt = f"""你是全球宏观策略师。基于以下结构化数据和实时搜索, 输出一份宏观投资环境综合判断。

## 结构化宏观数据 (DB)
{db_summary}

## 实时搜索 (Web)
{search_summary}

## 输出要求: 纯 JSON

{{
  "executive_summary": {{
    "one_liner": "一句话宏观定调",
    "conclusion": "宏观总体结论 (3-4句, 涵盖全球+中国)",
    "liquidity_direction": "全球流动性方向判断 (1-2句, 含美联储/QT/中国央行)",
    "risk_appetite": "风险偏好判断 (1-2句, 含结构性机会+压制因素)",
    "capex_direction": "全球 CAPEX 方向 (2-3句, 含规模/节奏/传导路径)",
    "top_3_themes": [
      {{ "rank": 1, "theme": "主题名", "conviction": "高/中高/中", "why": "30字内理由" }}
    ]
  }},

  "macro_conclusion": {{
    "cycle_stage": {{
      "global": "复苏后期/过热/滞胀/衰退",
      "china": "弱复苏/强复苏/衰退/过热",
      "evidence": "2-3句, 引用具体的 PMI/M2/CPI 数据支撑"
    }},
    "key_rates": {{
      "fed_rate": {{ "value": "当前利率", "trend": "暂停/加息/降息预期" }},
      "us10y": {{ "value": "从DB取", "trend": "回落/上升/震荡" }},
      "cn10y": {{ "value": "从DB取", "trend": "方向" }},
      "cn_lpr1y": {{ "value": "从DB取", "trend": "方向" }},
      "us_cn_spread": {{ "value": "利差bp", "trend": "方向" }}
    }},
    "liquidity": {{
      "direction": "一句话",
      "global_qt": "缩表进度",
      "china_credit": "信用扩张状态"
    }},
    "inflation_pmi": {{
      "us_cpi": {{ "value": "估", "trend": "方向" }},
      "cn_cpi": {{ "value": "估", "trend": "方向" }},
      "cn_pmi_mfg": {{ "value": "从DB取", "trend": "方向" }},
      "cn_pmi_nonmfg": {{ "value": "从DB取", "trend": "方向" }}
    }},
    "geopolitics": {{
      "key_events": ["事件1", "事件2"],
      "supply_chain_impact": "对供应链的影响"
    }},
    "china_policy": {{
      "monetary": "方向",
      "fiscal": "方向",
      "industrial": "重点产业",
      "property": "地产状况"
    }}
  }},

  "benefited_sectors": [
    {{
      "sector": "受益赛道",
      "driver": "驱动逻辑",
      "timeline": "时间窗",
      "confidence": "高/中高/中",
      "a_stock_mapping": ["代码+简称"]
    }}
  ],

  "key_risks": [
    {{ "risk": "风险描述", "probability": "高/中/低", "impact": "致命/重大/一般" }}
  ],

  "data_sources": {{
    "fed_rate": {{ "value": "从DB", "as_of": "日期", "source": "akshare" }},
    "us10y": {{ "value": "从DB", "as_of": "日期", "source": "akshare" }},
    "liquidity": {{ "source": "web_search+LLM", "as_of": "今天" }}
  }}
}}

规则:
- 所有数字必须来自结构化数据 (DB), 不得编造
- 如果 DB 中某字段缺失, 标注 "数据未覆盖" 并用搜索补充
- benefited_sectors 必须包含 A 股映射代码 (6位)
- 结论必须简洁, 每个字段 1-3 句"""
        try:
            t0 = _time.time()
            text = await asyncio.wait_for(
                self.provider.chat_pro(prompt, max_tokens=4096), timeout=90)
            if not text:
                logger.warning(f"[{self.name}] LLM returned empty text")
                return {"error": "LLM returned empty"}
            result = self.parse_json(text)
            if isinstance(result, dict):
                logger.info(f"[{self.name}] Macro report synthesized in {_time.time()-t0:.0f}s")
                return self._save_macro_report(result)
            else:
                logger.warning(f"[{self.name}] parse_json returned non-dict: {type(result).__name__} len={len(str(text))}")
                return {"error": f"parse_json returned {type(result).__name__}"}
        except Exception as e:
            logger.warning(f"[{self.name}] Macro synthesis failed: {type(e).__name__}: {e}")
        return {"error": "Macro synthesis failed"}

    @staticmethod
    def _save_macro_report(data: Dict) -> Dict:
        import os
        from datetime import datetime as dt, timedelta
        # backend/data/ (项目根)
        report_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data")
        report_dir = os.path.abspath(report_dir)
        os.makedirs(report_dir, exist_ok=True)
        filepath = os.path.join(report_dir, "macro_report.json")
        now = dt.now()
        report_id = f"macro_{now.strftime('%Y%m%d')}"
        record = {
            "report_id": report_id,
            "generated_at": now.isoformat(),
            "valid_until": (now + timedelta(days=30)).isoformat(),
            "generated_by": "GlobalCapexScanner V5.7",
            "data": data,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            _json.dump(record, f, ensure_ascii=False, indent=2, default=str)
        # 写入 registry
        try:
            from app.domain.research.services.report_store import _sync_upsert
            _sync_upsert(
                report_type="macro", report_id=report_id,
                title="宏观周期报告", agent="GlobalCapexScanner",
                filepath="data/macro_report.json",
                generated_at=record["generated_at"],
                valid_until=record["valid_until"],
                summary=data.get("executive_summary", {}).get("one_liner", "")[:200],
            )
        except Exception: pass
        logger.info(f"[GlobalCapexScanner] Macro report saved: {filepath}")
        return record

    @staticmethod
    def load_macro_cache() -> Dict:
        """优先查 registry, 兜底读文件"""
        from datetime import datetime as dt
        import os
        # backend/data/macro_report.json
        _report_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "data")
        _report_dir = os.path.abspath(_report_dir)
        _filepath = os.path.join(_report_dir, "macro_report.json")

        try:
            from app.framework.database.session import async_session
            from app.models.models import ReportRegistry
            from sqlalchemy import select
            import asyncio as _a

            async def _q():
                async with async_session() as db:
                    res = await db.execute(
                        select(ReportRegistry)
                        .where(ReportRegistry.report_type == "macro",
                               ReportRegistry.status == "valid")
                        .order_by(ReportRegistry.generated_at.desc()).limit(1))
                    return res.scalars().first()
            try:
                loop = _a.get_event_loop()
                if loop.is_running():
                    row = _a.run_coroutine_threadsafe(_q(), loop).result(timeout=5)
                else:
                    row = _a.run(_q())
            except RuntimeError:
                row = _a.run(_q())
            if row and row.valid_until and dt.now() < row.valid_until:
                # registry has filepath, but prefer direct path for reliability
                if os.path.exists(_filepath):
                    with open(_filepath, "r", encoding="utf-8") as f:
                        return _json.load(f)
        except Exception:
            pass
        # Fallback: read file directly
        filepath = _filepath
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    record = _json.load(f)
                valid_until = record.get("valid_until", "")
                if valid_until and dt.now().isoformat() < valid_until:
                    return record
            except Exception: pass
        return None

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "GlobalCapexScanner V5.7"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"
