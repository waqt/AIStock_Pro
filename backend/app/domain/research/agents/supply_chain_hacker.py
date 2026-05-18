"""
SupplyChainHacker V4.0 — 供应链降维穿透专家
单一职责: 顺景气赛道向下递归 L1-L4, 定位技术卡脖子/独占资源/产能真空期
输出: supply_chain_map + temporal + core_stocks (不含财务/估值/人力)
"""
import asyncio
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class SupplyChainHacker(ResearchAgent):
    """供应链黑客 V4.0 — 产业瓶颈降维穿透"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainHacker"

    # ═══ 主入口 ═══════════════════════════════════

    async def analyze(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await self.load_context(ctx)
        industry = ctx.get("industry", "未指定")

        if not self.provider:
            return {"agent": self.name, "error": "No AI provider", "data": ctx}

        logger.info(f"[{self.name}] Hacking supply chain: {industry}")

        # Phase 1: 供应链专项迭代深研
        research_data = await self._hack_supply_chain(industry)

        # Phase 2: 结构化输出 (supply_chain_map + temporal + core_stocks)
        result = await self._structure_output(industry, research_data)

        result["agent"] = self.name
        result["industry"] = industry
        result["search_rounds"] = research_data.get("search_rounds", 0)
        return result

    # ═══ Phase 1: 供应链迭代深研 ═════════════════

    async def _hack_supply_chain(self, industry: str) -> Dict:
        """3 轮迭代: 搜索→瓶颈定位→自检→补搜 (供应链专项)"""
        all_findings = []
        gaps = []
        round_num = 1

        for round_num in range(1, 4):
            # 供应链专项搜索词 (区别于 V3.0 的泛财务搜索)
            if round_num == 1:
                query = f"{industry} 产业链 核心瓶颈 产能 技术壁垒 龙头公司 市占率"
            elif gaps:
                query = f"{industry} {' '.join(gaps[:3])}"
            else:
                break

            search_results = []
            for r in await self.data_loader.search_web(query, num=5):
                search_results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("snippet", "")[:200],
                })

            if not search_results and round_num > 1:
                break

            # LLM 分析 + 供应链自检
            prompt = f"""你是全球半导体/制造业供应链研究员。分析 {industry} 产业链的瓶颈结构和国产替代机会。

## 本轮搜索结果
{_j(search_results)}

## 前几轮发现
{_j(all_findings)}

## 任务
1. 基于搜索结果提取关键供应链信息
2. **供应链自检**: 当前分析够不够深入?
   - 缺产能数据 (晶圆产能/封装产能/材料产能)?
   - 缺设备交期 (光刻/刻蚀/检测设备)?
   - 缺国产化率 (某环节国产占比<20%)?
   - 缺技术代际差 (与国际领先差几代)?
3. 如果缺数据, 列出下一轮搜索关键词 (最多 3 个)

请输出纯 JSON:
{{"findings": [{{"key": "瓶颈发现", "detail": "具体细节"}}],
  "gaps": ["缺口关键词1", "缺口关键词2"],
  "need_more_search": true/false}}"""

            try:
                text = await asyncio.wait_for(
                    self.provider.chat(prompt, max_tokens=2048), timeout=45)
                result = self.parse_json(text)
                if isinstance(result, dict):
                    findings = result.get("findings", [])
                    gaps = result.get("gaps", [])
                    all_findings.extend(findings)
                    if not result.get("need_more_search") and round_num > 1:
                        break
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(f"[{self.name}] Round {round_num} failed: {e}")
                break

        return {"findings": all_findings, "search_rounds": round_num}

    # ═══ Phase 2: 结构化输出 ═════════════════════

    async def _structure_output(self, industry: str, research: Dict) -> Dict:
        """将研究发现转化为 L1-L4 瓶颈图谱 + 核心标的 + 时间预测"""
        findings = research.get("findings", [])

        # 再搜一轮确保新鲜度
        fresh = []
        for r in await self.data_loader.search_web(
            f"{industry} 供应链 最新 瓶颈 产能 缺口 2026", num=5
        ):
            fresh.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", "")[:200],
            })

        prompt = f"""你是买方首席产业研究员。基于以下发现, 输出产业供应链深度穿透报告。

## 行业
{industry}

## 研究发现 ({len(findings)} 条)
{_j(findings, ensure_ascii=False)}

## 最新搜索
{_j(fresh, ensure_ascii=False)}

## 输出要求: 纯 JSON
{{
  "supply_chain_map": [
    {{"level": 1, "name": "显性瓶颈名称", "gap_score": 3, "gap_reason": "已被充分定价"}},
    {{"level": 2, "name": "工艺瓶颈", "gap_score": 8, "gap_reason": "市场未认知"}},
    {{"level": 3, "name": "材料瓶颈", "gap_score": 9, "gap_reason": "消耗倍增未定价"}},
    {{"level": 4, "name": "设备/测试瓶颈", "gap_score": 10, "gap_reason": "全市场忽视, 国产化率极低"}}
  ],
  "temporal": [
    {{"segment": "环节名", "demand_growth": "25%", "supply_gap": "15%",
      "gap_filled": "2027-Q2", "overcapacity_risk": "2028-Q1", "heat_level": "偏热"}}
  ],
  "core_stocks": [
    {{"code": "688012", "name": "中微公司", "exchange": "SH",
      "segment": "所属瓶颈环节",
      "relevance": "国产替代逻辑 (1句话)",
      "monopoly_root": "垄断根源 (技术/客户认证/产能)", "monopoly_score": 8,
      "short_note": "关键判断 (1句话)"}}
  ]
}}

gap_score 评分标准:
1-3: 已被市场充分定价 (估值已反映)
4-6: 市场部分认知, 但深度不够
7-9: 市场未充分定价, 存在显著预期差
10: 全市场完全忽视, 最大超额收益来源

每个 core_stock 必须对应到 supply_chain_map 中的某个瓶颈层级。"""

        try:
            text = await asyncio.wait_for(
                self.provider.chat(prompt, max_tokens=4096), timeout=60)
            result = self.parse_json(text)
            if isinstance(result, dict):
                result["findings_count"] = len(findings)
                logger.info(
                    f"[{self.name}] Structured: "
                    f"{len(result.get('supply_chain_map', []))} layers, "
                    f"{len(result.get('core_stocks', []))} stocks, "
                    f"{len(result.get('temporal', []))} time segments"
                )
                return result
        except asyncio.TimeoutError:
            logger.warning(f"[{self.name}] Phase 2 timeout")
        except Exception as e:
            logger.warning(f"[{self.name}] Phase 2 failed: {e}")

        return {"raw_findings": findings, "error": "Structuring failed"}

    # ═══ 基类实现 ═══════════════════════════════

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        ctx["positions"] = await self.data_loader.load_positions()
        return ctx

    @staticmethod
    def build_prompt(ctx):
        return "SupplyChainHacker V4.0"

    @staticmethod
    async def stream(ctx):
        yield "streaming not implemented"


# ═══ 工具 ═════════════════════════════════════

def _j(obj, **kw):
    """JSON 序列化 (Decimal 安全)"""
    import json
    from decimal import Decimal

    class _SafeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, Decimal):
                return float(o)
            return super().default(o)

    kw.setdefault("ensure_ascii", False)
    kw.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kw)
