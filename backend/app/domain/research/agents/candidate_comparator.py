"""
CandidateComparator V1.0 — 独立候选比较智能体
职责: 同源比较 (同一瓶颈节点内的候选) + 全局排名 (跨节点已验证候选)
原则: 只用外部硬事实 (搜索原文 + 财务数据), 不用 pipeline 内部标签, 避免循环论证
"""
import json
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


def _j(obj, **kw):
    from decimal import Decimal
    class _SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return float(o)
            return super().default(o)
    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)


class CandidateComparator(ResearchAgent):
    """候选比较智能体 V1.0 — 独立上下文、自己搜索、定性比较"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "CandidateComparator"

    # ═══ 同源比较 ═══════════════════════════════════

    async def compare_within_source(self, candidates: List[Dict],
                                    node_context: Dict) -> Dict:
        """同一瓶颈节点内的候选比较。

        Args:
            candidates: [{"code":"688012","name":"中微公司","source_type":"a_stock_mapping"}, ...]
            node_context: {
                "name": "刻蚀设备国产化",
                "bottleneck_narrative": "...",
                "profit_pool": "significant_15_30pct",
                "supply_rigidity": "...",
                "china_substitution_rate": "...",
                "global_leaders": [...],
                "value_magnitude": "..."
            }

        Returns:
            {"source": "节点名", "ranked": [{"code","rank","why"}],
             "eliminated": [], "comparison_dimensions": [...]}
        """
        if len(candidates) < 2:
            return {
                "source": node_context.get("name", ""),
                "ranked": self._fallback_rank(candidates),
                "eliminated": [],
                "comparison_dimensions": [],
            }

        names = [c.get("name", c.get("code", "?")) for c in candidates]
        node_name = node_context.get("name", "")
        logger.info(f"[{self.name}] compare_within_source '{node_name}': {names}")

        # 1. 并行搜索 — 每只候选 2 条查询
        search_data = await self._search_for_comparison(candidates, node_context)

        # 2. 拉取基本面 (PE/PB/市值)
        fundamentals = {}
        try:
            codes = [c["code"] for c in candidates if c.get("code")]
            if codes:
                fundamentals = await self.data_loader.load_fundamentals(codes)
        except Exception:
            pass

        # 3. LLM 比较 (★ 失败时自动重试 + 定量兜底)
        prompt = self._build_comparison_prompt(candidates, node_context, search_data, fundamentals)
        result = None
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=120)
            result_parsed = self.parse_json(text)
            if isinstance(result_parsed, dict) and "ranked" in result_parsed:
                result = result_parsed
            else:
                raise ValueError("LLM did not return ranked list")
        except Exception as first_err:
            logger.warning(f"[{self.name}] LLM failed ({first_err}), retrying with simplified prompt...")
            # ★ 重试: 简化 prompt, 仅保留 ranked list, 去掉 comparison_dimensions
            try:
                simple_prompt = self._build_simple_comparison_prompt(
                    candidates, node_context, search_data, fundamentals)
                text2 = await self.provider.chat_pro(simple_prompt, max_tokens=2048, timeout=90)
                result2 = self.parse_json(text2)
                if isinstance(result2, dict) and result2.get("ranked"):
                    result = result2
                    logger.info(f"[{self.name}] Retry succeeded")
            except Exception:
                logger.warning(f"[{self.name}] Retry also failed, using quantitative fallback")

        if result is not None:
            result.setdefault("eliminated", [])
            result.setdefault("comparison_dimensions", [])
            result["source"] = node_name

            # 标准化 ranked
            for i, r in enumerate(result.get("ranked", [])):
                r["rank"] = i + 1

            logger.info(f"[{self.name}] Done: ranked={[r.get('code','?') for r in result['ranked']]}")
            return result

        # ★ 定量兜底: 用基本面数据做客观排序
        logger.warning(f"[{self.name}] Using quantitative fallback for '{node_name}'")
        return self._quantitative_rank(candidates, fundamentals, node_name, node_context)

    async def _search_for_comparison(self, candidates: List[Dict],
                                      node_context: Dict) -> Dict[str, List]:
        """为每只候选搜索比较用信息 (★ snippet 裁剪至 150 字符控制 token)"""
        node_name = node_context.get("name", "")
        results = {}
        for c in candidates:
            name = c.get("name", "")
            code = c.get("code", "")
            queries = [
                f"{name} {code} {node_name} 市场份额 营收 技术 产品 2026",
                f"{name} {code} 客户 供应链 竞争 毛利率 客户 认证 2025 2026",
            ]
            items = []
            for q in queries:
                try:
                    r = await self.data_loader.search_web(q, num=3)
                    for rr in r:
                        snippet = (rr.get("snippet", "") or "")[:150]  # ★ 300→150
                        if snippet:
                            items.append({
                                "query": q,
                                "title": (rr.get("title", "") or "")[:100],
                                "snippet": snippet,
                            })
                except Exception:
                    pass
            results[code] = items
        return results

    def _build_simple_comparison_prompt(self, candidates, node_context,
                                         search_data, fundamentals) -> str:
        """★ 简化版比较 prompt (重试用, 只要求 ranked list, 不要 comparison_dimensions)"""
        node_name = node_context.get("name", "")
        narrative = node_context.get("bottleneck_narrative", "")
        profit_pool = node_context.get("profit_pool", "")
        rigidity = node_context.get("supply_rigidity", "")
        substitution = node_context.get("china_substitution_rate", "")

        cand_lines = [f"- {c.get('name','?')}({c.get('code','?')})" for c in candidates]
        search_lines = []
        for code, items in search_data.items():
            name = next((c.get("name", code) for c in candidates if c.get("code") == code), code)
            for item in items[:3]:
                search_lines.append(f"- {name}: {item['snippet'][:150]}")

        fund_lines = []
        for code, info in fundamentals.items():
            fund_lines.append(
                f"{info.get('name',code)}({code}): PE={info.get('pe_ttm','N/A')} "
                f"营收={info.get('revenue','N/A')} 市值={info.get('market_capital','N/A')}")

        return f"""比较以下公司在"{node_name}"环节的竞争力。

环节: {node_name} | 利润池:{profit_pool} | 供给刚性:{rigidity} | 国产替代率:{substitution}
瓶颈描述: {narrative[:200]}

候选: {chr(10).join(cand_lines)}

搜索证据: {chr(10).join(search_lines) if search_lines else '无'}

基本面: {chr(10).join(fund_lines) if fund_lines else '无'}

先逐票分析每家公司的技术能力、市场地位、盈利能力和竞争壁垒，再按竞争力排序。
最后输出JSON: {{"ranked": [{{"code":"xxx","rank":1,"why":"理由"}}, ...]}}
分析过程写在外面，JSON独立可解析。"""

    def _build_comparison_prompt(self, candidates: List[Dict], node_context: Dict,
                                  search_data: Dict, fundamentals: Dict) -> str:
        """构建同源比较 prompt — 不用 pipeline 标签"""
        node_name = node_context.get("name", "")
        narrative = node_context.get("bottleneck_narrative", "")
        profit_pool = node_context.get("profit_pool", "")
        rigidity = node_context.get("supply_rigidity", "")
        substitution = node_context.get("china_substitution_rate", "")
        leaders = node_context.get("global_leaders", [])
        magnitude = node_context.get("value_magnitude", "")

        # 候选基本信息
        cand_lines = []
        for c in candidates:
            cand_lines.append(
                f"- {c.get('name','?')}({c.get('code','?')}): "
                f"{c.get('investment_logic', c.get('source_type',''))}"
            )

        # 搜索结果
        search_lines = []
        for code, items in search_data.items():
            name = next((c.get("name", code) for c in candidates if c.get("code") == code), code)
            search_lines.append(f"\n## {name}({code})")
            for item in items[:5]:
                s = item["snippet"][:200]
                search_lines.append(f"- {item['query']}: {s}")

        # 基本面
        fund_lines = []
        for code, info in fundamentals.items():
            name = info.get("name", code)
            pe = info.get("pe_ttm") or info.get("pe", "N/A")
            pb = info.get("pb", "N/A")
            mcap = info.get("market_capital", "N/A")
            fund_lines.append(f"{name}({code}): PE={pe} PB={pb} 市值={mcap}")

        prompt = f"""你是资深产业分析师。比较以下候选公司在 "{node_name}" 环节的竞争力和投资价值。

## 环节背景
- 环节: {node_name}
- 利润池: {profit_pool}  |  市场量级: {magnitude}
- 供给刚性: {rigidity}
- 国产替代率: {substitution}
- 全球龙头: {', '.join(leaders) if leaders else 'N/A'}
- 瓶颈描述: {narrative}

## 候选公司
{chr(10).join(cand_lines)}

## 原始搜索结果（关键证据，必须基于此判断）
{chr(10).join(search_lines) if search_lines else "（无搜索结果）"}

## 基本面参考
{chr(10).join(fund_lines) if fund_lines else "（无基本面数据）"}

## 分析方法
先逐票分析，再综合排序。

第一步 — 逐票分析每家公司在该环节的真实竞争壁垒：
1. 技术能力/产品性能 — 制程领先度？产品覆盖度？技术参数？
2. 市场地位 — 市占率？客户质量？订单可见度？认证壁垒？
3. 盈利能力 — 毛利率？营收规模？增长趋势？
4. 竞争壁垒 — 客户切换成本？技术代差？替代难度？

第二步 — 综合排序，引用上述分析中的事实支撑。

## 输出格式
先写一段简要分析过程，然后输出以下JSON：

{{
  "ranked": [
    {{"code": "688012", "rank": 1, "why": "简短理由（引用事实）"}},
    {{"code": "002371", "rank": 2, "why": "简短理由"}}
  ],
  "comparison_dimensions": [
    {{"dimension": "技术能力", "winner": "688012", "evidence": "具体事实"}},
    {{"dimension": "市场地位", "winner": "002371", "evidence": "具体事实"}},
    {{"dimension": "盈利能力", "winner": "688012", "evidence": "具体事实"}},
    {{"dimension": "竞争壁垒", "winner": "688012", "evidence": "具体事实"}}
  ]
}}
JSON 之前的分析过程不会被丢弃，请确保 JSON 部分完整且独立可解析。"""
        return prompt

    @staticmethod
    def _fallback_rank(candidates: List[Dict]) -> List[Dict]:
        """LLM 调用失败时的降级排序"""
        return [{"code": c.get("code", ""), "name": c.get("name", ""),
                 "rank": i + 1, "why": "LLM比较失败, 保留原始顺序"}
                for i, c in enumerate(candidates)]

    def _quantitative_rank(self, candidates: List[Dict], fundamentals: Dict,
                            node_name: str, node_context: Dict) -> Dict:
        """★ 定量排序兜底: 用基本面指标做客观排序 (无需 LLM)"""
        scored = []
        for c in candidates:
            code = c.get("code", "")
            fd = fundamentals.get(code, {})
            score = 0.0
            details = []

            # 维度1: 营收规模 (归一化到组内)
            rev = fd.get("revenue") or 0
            if rev:
                score += min(rev / 100, 30)  # 最多30分
                details.append(f"营收={rev}亿")

            # 维度2: 营收增速
            growth = fd.get("revenue_growth") or fd.get("profit_growth") or 0
            if growth:
                score += min(growth * 2, 25)  # 最多25分
                details.append(f"增速={growth}%")

            # 维度3: 净利润率
            margin = fd.get("net_margin") or 0
            if margin:
                score += min(margin, 20)  # 最多20分
                details.append(f"利润率={margin}%")

            # 维度4: PE (低的优先)
            pe = fd.get("pe_ttm") or fd.get("pe") or 0
            if pe and pe > 0:
                pe_score = max(0, 15 - pe / 10)
                score += pe_score
                details.append(f"PE={pe}")

            # 维度5: 市值 (流动性)
            mcap = fd.get("market_capital") or 0
            if mcap:
                mcap_score = min(mcap / 500, 10)
                score += mcap_score
                details.append(f"市值={mcap}亿")

            scored.append((code, c.get("name", code), score, "; ".join(details)))

        # 按得分降序
        scored.sort(key=lambda x: -x[2])

        ranked = []
        for i, (code, name, score, detail) in enumerate(scored):
            ranked.append({
                "rank": i + 1,
                "code": code,
                "name": name,
                "why": f"定量排序 ({detail}, 总分={score:.1f})",
            })

        # 维度比较从基本面数据提取
        dims = []
        if len(scored) >= 2:
            top_code = scored[0][0]
            dims = [
                {"dimension": "营收规模", "winner": top_code,
                 "evidence": f"最高({scored[0][3]})"},
                {"dimension": "基本面总分", "winner": top_code,
                 "evidence": f"{scored[0][2]:.1f} vs {'/'.join(f'{s[2]:.1f}' for s in scored[1:])}"},
            ]

        logger.info(f"[{self.name}] Quantitative rank for '{node_name}': "
                     f"top={ranked[0]['code'] if ranked else 'none'} score={scored[0][2] if scored else 0:.1f}")
        return {
            "source": node_name,
            "ranked": ranked,
            "eliminated": [],
            "comparison_dimensions": dims,
        }

    # ═══ 全局排名 ═══════════════════════════════

    async def global_ranking(self, all_candidates: List[Dict]) -> Dict:
        """跨节点全局排序。

        Args:
            all_candidates: 已验证候选列表，每项含:
                {code, name, node, node_context, verification, eliminated_by, eliminated_reason}

        Returns:
            {"ranked_stocks": [{"rank":1,"code":"688012","why":"..."}], "runner_ups": [...]}
        """
        if not all_candidates:
            return {"ranked_stocks": [], "runner_ups": []}

        active = [c for c in all_candidates if not c.get("eliminated_by")]
        logger.info(f"[{self.name}] Global ranking: {len(active)} active of {len(all_candidates)} total")

        prompt = self._build_global_ranking_prompt(all_candidates)
        try:
            text = await self.provider.chat_pro(prompt, max_tokens=4096, timeout=120)
            result = self.parse_json(text)
            if isinstance(result, dict) and result.get("ranked_stocks"):
                for i, r in enumerate(result["ranked_stocks"]):
                    r["rank"] = i + 1
                logger.info(f"[{self.name}] Done: top={result['ranked_stocks'][0].get('code','?')}")
                return result
            raise ValueError("Invalid LLM output")
        except Exception as e:
            logger.warning(f"[{self.name}] Failed ({e}), fallback to pool order")
            return self._fallback_global(all_candidates)

    def _build_global_ranking_prompt(self, candidates: List[Dict]) -> str:
        """构建全局排名 prompt"""
        cand_lines = []
        for c in candidates:
            code = c.get("code", "")
            name = c.get("name", "")
            node = c.get("node", "")
            eliminated = c.get("eliminated_by")
            elim_reason = c.get("eliminated_reason", "")

            nc = c.get("node_context", {})
            profit_pool = nc.get("profit_pool", "?")
            severity = nc.get("bottleneck_severity", "?")
            magnitude = nc.get("value_magnitude", "?")

            v = c.get("verification", {})
            audit = v.get("audit", {})
            audit_v = audit.get("verdict", "?")
            audit_s = audit.get("score", "?")
            roic = v.get("roic", "?")
            moat = v.get("moat_profile", {})
            strong_n = sum(1 for val in moat.values() if isinstance(val, str) and val == "strong")
            val_u = v.get("valuation", {}).get("upside_pct", "?")

            if eliminated:
                status = f"[同源淘汰→输给{eliminated}] {elim_reason}"
            else:
                status = f"[活跃] 审计={audit_v}({audit_s}) ROIC={roic} 护城河={strong_n}维强 上行={val_u}"

            cand_lines.append(
                f"[{candidates.index(c)+1}] {name}({code}) — 节点:{node} "
                f"(利润池:{profit_pool} 严重度:{severity} 量级:{magnitude})\n"
                f"    {status}"
            )

        return f"""你是首席投资官。综合以下各节点的已验证候选，给出全局投资价值排序。

## 候选公司列表
{chr(10).join(cand_lines)}

## 排序原则
1. 首要: 节点的利润池大小 + 供给刚性（利润的量和确定性）
2. 次要: 公司在节点内的不可替代性（护城河证据 + 竞争格局）
3. 辅助: 财务健康度（审计结果 + ROIC）、估值上行空间
4. 如果某节点内多家公司，只考虑该节点排名最高的
5. 被同源淘汰的公司排在最后（若仍有投资价值）
6. 每档排序必须引用事实证据

## 输出JSON
{{
  "ranked_stocks": [
    {{"rank": 1, "code": "688012", "name": "中微公司", "why": "不超过80字的事实依据"}}
  ],
  "runner_ups": [
    {{"code": "688525", "name": "佰维存储", "why": "不入选理由"}}
  ]
}}
只输出JSON。"""

    @staticmethod
    def _fallback_global(candidates: List[Dict]) -> Dict:
        """降级排序 — 按利润池大小"""
        pool_order = {"dominant_30_50pct": 5, "significant_15_30pct": 4,
                      "moderate_5_15pct": 3, "marginal_below_5pct": 2}
        sorted_c = sorted(candidates, key=lambda c: (
            -(pool_order.get(c.get("node_context", {}).get("profit_pool", ""), 1)),
            0 if c.get("eliminated_by") else 1,
        ))
        ranked = []
        for i, c in enumerate(sorted_c):
            if c.get("eliminated_by"):
                break
            ranked.append({"rank": i + 1, "code": c.get("code", ""),
                           "name": c.get("name", ""),
                           "why": "LLM排序失败, 按节点利润池降序"})
        return {"ranked_stocks": ranked, "runner_ups": []}
