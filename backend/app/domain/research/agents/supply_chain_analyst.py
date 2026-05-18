"""
供应链深度分析师 — 5步推理: 景气信号→供应链图谱→供需瓶颈→垄断标的→定量估值
全球视角: 覆盖 A股/美股/台股/韩股, LLM 补全球行业知识
"""
import json
from decimal import Decimal
from typing import Dict, Any, List
from app.domain.research.agents.base import ResearchAgent
from app.domain.research.services.data_loader import data_loader
from app.framework.logger import logger


class _SafeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _json_dumps(obj, **kwargs):
    kwargs.setdefault("ensure_ascii", False)
    kwargs.setdefault("cls", _SafeEncoder)
    return json.dumps(obj, **kwargs)


class SupplyChainAnalyst(ResearchAgent):
    """供应链深度分析智能体 — 全球价值链下钻"""

    def __init__(self, provider=None):
        super().__init__(provider=provider, data_loader=data_loader)
        self.name = "SupplyChainAnalyst"
        self._steps = []  # 记录每步输出供前端展示

    async def analyze(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行完整的5步供应链分析 (每步 45s 超时, 失败不中断)"""
        self._steps = []
        ctx = await self.load_context(context)
        industry = ctx.get("industry", "未指定")
        codes = ctx.get("stock_codes", [])

        results = {
            "agent": self.name,
            "industry": industry,
            "stock_codes": codes,
        }

        if not self.provider:
            results["error"] = "No AI provider configured"
            results["data"] = ctx
            return results

        import asyncio

        async def _safe_step(name, coro):
            try:
                return await asyncio.wait_for(coro, timeout=45)
            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] {name} timed out")
                return {"error": "timeout", "step": name}
            except Exception as e:
                logger.warning(f"[{self.name}] {name} failed: {e}")
                return {"error": str(e), "step": name}

        # ── Step 1-5: 各自超时保护 ──
        step1 = await _safe_step("prosperity", self._analyze_prosperity_signals(ctx))
        self._steps.append({"step": 1, "name": "景气信号识别", "output": step1})
        results["prosperity_signals"] = step1

        step2 = await _safe_step("supply_chain", self._map_supply_chain(ctx, step1))
        self._steps.append({"step": 2, "name": "供应链映射", "output": step2})
        results["supply_chain"] = step2

        step3 = await _safe_step("bottleneck", self._locate_bottleneck(ctx, step2))
        self._steps.append({"step": 3, "name": "供需瓶颈定位", "output": step3})
        results["bottleneck"] = step3

        step4 = await _safe_step("core_targets", self._select_core_targets(ctx, step3))
        self._steps.append({"step": 4, "name": "核心标的锁定", "output": step4})
        results["core_targets"] = step4

        # ── Step 3.5: 时间维度分析 ──
        step35 = await _safe_step("temporal", self._temporal_analysis(ctx, step3))
        self._steps.append({"step": 4, "name": "景气周期预测", "output": step35})
        results["temporal"] = step35

        step5 = await _safe_step("valuation", self._quantitative_valuation(ctx, step4))
        self._steps.append({"step": 5, "name": "定量估值", "output": step5})
        results["valuation"] = step5

        # ── Summary ──
        summary = await _safe_step("summary", self._generate_summary(results))
        results["summary"] = summary.get("raw_text", "") if isinstance(summary, dict) else summary
        results["steps"] = self._steps

        return results

    # ═══ 各步骤实现 ═════════════════════════════

    async def _analyze_prosperity_signals(self, ctx: Dict) -> Dict:
        """Step 1: 识别全球高景气信号"""
        industry = ctx.get("industry", "")
        macro = ctx.get("macro", {})
        fundamentals = ctx.get("fundamentals", {})
        market_data = ctx.get("market_data", {})

        # 汇总可用的定量数据
        pe_list = [f"{c}: PE={f.get('pe_ttm','?')}" for c, f in fundamentals.items() if f.get('pe_ttm')]
        volume_trends = []
        for code, rows in market_data.items():
            if len(rows) >= 10:
                recent_vol = sum(r.get("volume", 0) for r in rows[:5])
                prev_vol = sum(r.get("volume", 0) for r in rows[5:10])
                if prev_vol > 0:
                    trend = "放量" if recent_vol > prev_vol * 1.2 else ("缩量" if recent_vol < prev_vol * 0.8 else "持平")
                    volume_trends.append(f"{code}: {trend} (近期/前期={recent_vol/prev_vol:.2f})")

        # 🔍 多轮深研: 行业最新动态
        research = await self.data_loader.deep_research(
            f"{industry} 全球 capex 资本开支 最新动态 2025 2026", rounds=2
        )
        # 扁平化搜索结果: [{title, url, snippet}]
        search_refs = []
        for src in research.get("sources", []):
            for r in src.get("results", []):
                search_refs.append({"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("snippet","")[:200]})

        prompt = f"""你是一位全球科技产业研究员。请分析 {industry} 行业的高景气信号。

## 宏观环境
{_json_dumps(macro, ensure_ascii=False)}

## A股映射标的估值
{_json_dumps(pe_list, ensure_ascii=False) if pe_list else "暂无A股映射数据"}

## 成交量趋势
{_json_dumps(volume_trends, ensure_ascii=False) if volume_trends else "暂无"}

## 🔍 网络实时搜索结果 ({len(search_refs)} 条)
{_json_dumps(search_refs[:8], ensure_ascii=False) if search_refs else "搜索不可用, 使用你的训练知识"}

## 你的任务
综合以上数据和搜索结果, 请分析:
**重要: 引用搜索结果时请附带来源 URL, 格式为 [来源标题](URL)**
1. **国际龙头资本开支**: {industry} 领域全球 Top3 公司(NVDA/TSMC/ASML/Intel等)的最新资本开支计划和扩产动态
2. **全球资金流向**: 该赛道是否在吸引全球热钱? (参考美股科技ETF资金流入/SOX指数走势)
3. **产业事件催化**: 近期是否有重大订单、技术突破、政策扶持?
4. **景气度综合评分** (1-10分)
5. **推荐关注的高景气子环节**: 列出最受益的上游/中游/下游环节

请输出结构化 JSON:
{{"capex_analysis": "...", "capital_flow": "...", "catalysts": "...", "prosperity_score": N, "hot_segments": ["环节1","环节2"]}}"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "prosperity")

    async def _map_supply_chain(self, ctx: Dict, signals: Dict) -> Dict:
        """Step 2: 多级递归穿透 — 从显性瓶颈逐层上探到材料/工艺/设备"""
        industry = ctx.get("industry", "")
        hot_segments = signals.get("hot_segments", [])

        # 🔍 搜索供应链最新动态
        sc_research = await self.data_loader.deep_research(
            f"{industry} 供应链 上游 材料 设备 工艺瓶颈", rounds=2
        )
        sc_refs = []
        for src in sc_research.get("sources", []):
            for r in src.get("results", []):
                sc_refs.append({"title": r.get("title",""), "url": r.get("url",""), "snippet": r.get("snippet","")[:200]})

        prompt = f"""你是一位拥有硅谷硬核技术视角的半导体/材料/设备资深产业专家。请对 {industry} 行业做**多级递归穿透分析**。

## 高景气子环节 (显性 Layer 1)
{_json_dumps(hot_segments, ensure_ascii=False)}

## 🔍 供应链实时搜索结果 ({len(sc_refs)} 条)
{_json_dumps(sc_refs[:6], ensure_ascii=False) if sc_refs else "搜索暂不可用"}

## 核心方法: 多级递归追问

对每个高景气子环节, **向上游连追 3-4 层"为什么"**:

Layer 1 (显性瓶颈): 市场都知道的技术痛点
  ↓ 追问: "是什么物理/材料/工艺限制导致了这个瓶颈?"
Layer 2 (工艺瓶颈): 解决 Layer 1 必须突破的制造工艺
  ↓ 追问: "这个工艺又依赖什么更上游的材料/设备?"
Layer 3 (材料/辅材瓶颈): Layer 2 依赖的核心耗材/辅材/零部件
  ↓ 追问: "这些材料的品质由什么测试/设备保证?"
Layer 4 (测试与辅具瓶颈): 保证 Layer 3 质量的检测设备/探针/夹具

**案例 (AI算力)**:
- Layer 1: HBM 高带宽存储 ← 市场热炒, 龙头已被充分定价
- Layer 2: 混合键合(Hybrid Bonding) ← 16层堆叠必须用, TCB不够
- Layer 3: 原子级 CMP 抛光液 + ALD 沉积 ← 键合要求表面零缺陷
- Layer 4: MEMS 探针卡 ← KGD 测试必须, 混合键合对探针损伤零容忍
- **预期差**: Layer 3/4 的消耗量翻倍, 但估值还在传统半导体周期

## 输出要求

对每个 Layer, 列出:
1. 环节名称 + 层级 (L1/L2/L3/L4)
2. 技术壁垒描述 (为什么难做)
3. 全球主要公司 + A股映射标的
4. **预期差评分** (1-10): 技术需求增长倍数 vs 当前市场关注度
5. 预期差理由: 为什么这个环节还没被充分定价
6. 供需状况 + 扩产周期
7. 产能集中度

请输出纯JSON数组 (不要Markdown, 不要解释):
[{{"level":1,"name":"HBM","barriers":"TSV堆叠技术","gap_score":3,"gap_reason":"已被市场充分定价","global_leader":"SK Hynix(000660.KR)","a_share_code":"","supply":"供不应求","expand_mo":24,"concentration":"SK+三星+美光95%"}},{{"level":2,"name":"混合键合","barriers":"原子级对准+铜-铜键合","gap_score":9,"gap_reason":"市场未认知TCB→Hybrid键合的颠覆性","global_leader":"Besi(BESI.AS)","a_share_code":"688012","supply":"供不应求","expand_mo":18,"concentration":"Besi+ASMPT 80%"}},{{"level":3,"name":"CMP抛光液","barriers":"原子级平整度, 缺陷零容忍","gap_score":9,"gap_reason":"消耗量翻倍但估值仍在传统周期","global_leader":"Cabot(CBT.US)","a_share_code":"300054","supply":"供不应求","expand_mo":12,"concentration":"Cabot+Hitachi 70%"}},{{"level":4,"name":"量检测设备","barriers":"纳米缺陷检测, 混合键合无探针损伤","gap_score":10,"gap_reason":"全市场抢HBM, 量检测需求暴增被忽视","global_leader":"KLA Corp(KLAC.US)","a_share_code":"688361","supply":"供不应求","expand_mo":12,"concentration":"KLA+Onto+Camtek 85%"}}]"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "supply_chain")

    async def _locate_bottleneck(self, ctx: Dict, chain: Dict) -> Dict:
        """Step 3: 预期差验证 — 双重过滤 (技术壁垒 + 财务信号)"""
        layers = chain.get("recursive_layers", chain.get("layers", []))
        fundamentals = ctx.get("fundamentals", {})
        positions = ctx.get("positions", [])

        # 筛选高预期差环节 (score >= 7, 即尚未被市场充分定价)
        high_gap = [l for l in layers if l.get("expectation_gap_score", 0) >= 7]
        if not high_gap:
            # Fallback: 供不应求的环节
            high_gap = [l for l in layers if "供不应求" in l.get("supply_status", "")]
        if not high_gap:
            high_gap = layers[:4]

        # 🔍 搜索瓶颈环节最新动态
        search_refs = []
        for b in high_gap[:3]:
            name = b.get("name","")
            if name:
                results = await self.data_loader.search_web(f"{name} 产能 供需 扩产 技术壁垒")
                for r in results:
                    r["segment"] = name
                    search_refs.append(r)

        prompt = f"""你是一位全球供应链投资专家。请深度分析以下供不应求的瓶颈环节。

## 🔍 实时搜索到的行业动态 ({len(search_refs)} 条)
{_json_dumps(search_refs[:8], ensure_ascii=False)}

## 瓶颈环节
{_json_dumps(high_gap, ensure_ascii=False, indent=2)}

## A股映射基本面
{_json_dumps({c: f for c, f in fundamentals.items() if f.get('pe_ttm')}, ensure_ascii=False)}

## 持仓数据
{_json_dumps(positions, ensure_ascii=False, indent=2) if positions else '无'}

**重要: 引用搜索结果/数据源时请附带 URL, 格式为 [来源](URL)**

## 你的任务: 双重硬核过滤 — 借鉴 Gemini Deep Research 方法论

**过滤 1 — 超级背景审计 (Human Capital Audit)**
对每个标的的创始人/CTO/核心技术团队进行基因审计:
1. 是否具备全球前三巨头 (KLA/ASML/AMAT/Teradyne/DuPont等) 的核心研发履历?
2. 是否具备全球顶尖学术实验室的底层物理/材料学验证背景?
3. 不具备以上背景的标的 → 其"技术突破"大概率是伪概念，必须无情剔除
4. 具备以上背景的标的 → 技术上具备颠覆产业的可能，重点跟踪

**过滤 2 — 财务剪刀差交叉验证 (Scissor-Gap Verification)**
对通过背景审计的标的，冷酷验证财务数据:
1. **经营杠杆释放**: 是否观察到净利润增速 >> 营收增速? (例: 净利润+600% vs 营收+48%)
2. **毛利率验证**: 综合毛利率是否在上升? (壁垒提升 → 毛利率应同步爬升)
3. **合同负债雷达**: 合同负债/预付款是否出现非线性激增? (这是下游需求爆发的先行指标)
4. **期间费用率**: 研发费率是否随着营收增长而快速下降? (经营杠杆释放的核心指标)
5. **现金流压力测试**: 扣非净利润是否持续为正? 经营现金流是否健康? 若严重依赖政府补助，必须标注为高风险

**过滤 3 — 伪概念资产剥离**
以下类型的标的必须无情剔除:
- 财务营收高增但利润滞胀 (毛利率下滑 + 利润增速 << 营收增速) → 缺乏定价权
- 创始人背景与核心技术赛道存在"基因鸿沟" (如传统电测背景却宣称能做纳米级光检测)
- 利润严重依赖政府补贴，扣非净利润持续巨额亏损

请输出:
[{{"segment":"环节名","level":2,"monopoly_root":"专利+2年认证+创始人KLA履历","monopoly_score":8,"human_capital":"创始人XXX, KLA前资深科学家, 布朗大学物理学博士","scissor_gap":{"revenue_growth":"48%","profit_growth":"609%","gross_margin":"49.9%(↑1pct)","contract_liability_growth":"55.8%","rd_ratio":"32%(↓4pct)","operating_cashflow":"-0.2亿","verdict":"PASS — 经典经营杠杆释放"},"pricing_power":"利润增速>营收增速 12倍","a_share_picks":[{{"code":"688361","name":"中科飞测","logic":"KLA核心科学家回国创业, 光学+电子束+X光三路线全覆盖","verification_signal":"合同负债8.81亿(+55.8%)","risk":"扣非仍亏损, 现金流紧绷"}}]}}]"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "bottleneck")

    async def _temporal_analysis(self, ctx: Dict, high_gap: List) -> Dict:
        """Step 3.5: 时间维度分析 — 景气持续性 + 供需缺口量化 + 产能过剩预警"""
        bn_list = high_gap if isinstance(high_gap, list) else []
        if not bn_list:
            return {"note": "无瓶颈数据, 跳过时间分析"}

        fundamentals = ctx.get("fundamentals", {})

        # 汇总 PE 数据用于热度判断
        pe_summary = []
        for code, f in fundamentals.items():
            if f.get("pe_ttm") and f["pe_ttm"] > 0:
                pe_summary.append({"code": code, "name": f.get("name",""), "pe_ttm": f["pe_ttm"], "pb": f.get("pb")})

        prompt = f"""你是一位半导体/科技产业分析师, 擅长产能周期和供需模型。请对以下瓶颈环节做时间维度量化分析。

## 瓶颈环节
{_json_dumps(bn_list, ensure_ascii=False)}

## A股标的 PE 数据 (用于热度判断)
{_json_dumps(pe_summary, ensure_ascii=False)}

## 分析任务 (每个环节)

1. **当前需求增速**: 估计年化需求增速 (%)
2. **当前产能利用率**: 估计全球产能利用率 (%)
3. **在建产能**: 在建新产能占现有产能的比例 (%)
4. **新产能投产时间**: 预计新产能何时开始释放 (YYYY-QQ 或 月份数)
5. **供需缺口**: 当前缺口百分比 (%)
6. **缺口填补时间**: 缺口何时被填补 (YYYY-QQ 或 月份数)
7. **产能过剩预警**: 如果新产能继续投入, 何时可能过剩 (YYYY-QQ 或 "暂无风险")
8. **景气持续性评分** (1-10): 高景气还能持续多久
9. **热度判断**: 基于 PE 数据和行业生命周期, 判断当前热度是 "合理/偏热/过热"

请输出纯JSON数组:
[{{"segment":"环节名","demand_growth":"25%","capacity_util":"95%","pipeline_pct":"30%","new_capacity_online":"2026-Q4","supply_gap":"15%","gap_filled":"2027-Q2","overcapacity_risk":"2028-Q1","sustainability_score":7,"sustainability_quarters":6,"heat_level":"合理","heat_reason":"PE30处于历史中位, 行业成长期"}}]"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "temporal")

    async def _select_core_targets(self, ctx: Dict, high_gap: List) -> Dict:
        """Step 4: 锁定核心标的"""
        all_picks = []
        for b in high_gap if isinstance(high_gap, list) else []:
            all_picks.extend(b.get("a_share_picks", []))

        if not all_picks:
            return {"picks": [], "note": "未找到A股映射标的, 建议关注全球龙头"}

        # 查询这些标的的基本面
        pick_codes = [p["code"] for p in all_picks if p.get("code")]
        fund = await self.data_loader.load_fundamentals(pick_codes)

        picks_with_data = []
        for p in all_picks:
            code = p.get("code", "")
            f = fund.get(code, {})
            picks_with_data.append({
                **p,
                "pe_ttm": f.get("pe_ttm"), "pb": f.get("pb"),
                "mcap_yi": f.get("mcap_yi"),
            })

        prompt = f"""你是一位投资组合经理。请从以下候选中选出 3-5 只最值得配置的标的。

## 候选标的
{_json_dumps(picks_with_data, ensure_ascii=False, indent=2)}

## 选择标准
1. 在供应链瓶颈环节中占据最核心位置
2. 估值合理 (PE相对行业均值不过分高估)
3. 业绩确定性高 (有订单/产能/客户支撑)
4. 与用户现有持仓风格匹配

请输出:
{{"picks": [{{"code":"","name":"","score":N,"reason":"","position_suggest":"10%","risk":""}}]}}"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "core_picks")

    async def _quantitative_valuation(self, ctx: Dict, targets: Dict) -> Dict:
        """Step 5: 定量估值"""
        picks = targets.get("picks", [])
        if not picks:
            return {"note": "无标的可估值"}

        # 加载估值数据
        codes = [p["code"] for p in picks if p.get("code")]
        fund = await self.data_loader.load_fundamentals(codes)

        valuations = []
        for p in picks:
            code = p.get("code", "")
            f = fund.get(code, {})
            valuations.append({
                "code": code, "name": p.get("name", ""),
                "pe_ttm": f.get("pe_ttm"), "pb": f.get("pb"),
                "mcap_yi": f.get("mcap_yi"),
                "score": p.get("score", 5),
            })

        prompt = f"""你是一位买方分析师。请为以下标的做定量估值, 遵循**全球坐标系对标**原则。

## 标的估值数据
{_json_dumps(valuations, ensure_ascii=False, indent=2)}

## 估值方法
1. **全球对标**: 为每只标的找到其"物理本尊"(全球做同样业务的对标公司)
   - 例: 中国探针卡 → 对标 FormFactor (FORM), 中国 CMP 耗材 → 对标 Cabot (CBT)
2. **估值模型选择**:
   - 如果是设备/硬件 (重置成本高, 技术迭代快): 用 PEG 模型, 重点捕捉技术跨代溢价
   - 如果是耗材/零部件 (晶圆厂开工即消耗, 黏性极高): 用 PS→DCF 模型, 赚取稼动率提升的复利
3. **估值折溢价分析**: 对比对标公司的 PE/PS 倍数, 计算 A 股标的的合理折溢价
4. **预期差定价**: 如果该标的技术壁垒提升 3 倍, 但估值还在传统周期, 给出合理重估空间
5. 给出 6-12 个月目标价 + 上涨空间 (%)

请输出:
[{{"code":"","name":"","global_peer":"对标公司+代码","peer_pe":25,"peer_ps":5,"current_pe":30,"fair_pe":40,"upside_pct":30,"valuation_method":"PEG/PS-DCF","target_price":120,"catalyst":"2026Q2 大客户验证通过"}}]"""

        text = await self.provider.chat(prompt)
        return self._extract_json_block(text, "valuation")

    async def _generate_summary(self, results: Dict) -> str:
        """汇总生成最终投资建议"""
        prompt = f"""你是一位首席投资官(CIO)。请基于以下分析结果, 生成最终投资建议。

## 分析报告
{_json_dumps({
    "prosperity": results.get("prosperity_signals"),
    "core_picks": results.get("core_targets"),
    "valuation": results.get("valuation"),
}, ensure_ascii=False, indent=2)}

## 输出要求 (Markdown格式)
1. **核心结论** (1-2句话)
2. **推荐标的及配置比例**
3. **买入逻辑** (为什么现在买)
4. **风险提示**
5. **后续跟踪指标** (什么数据变化时需要重新评估)"""

        try:
            return await self.provider.chat(prompt)
        except Exception:
            return "AI 汇总生成失败, 请查看各步骤独立报告"

    # ═══ Helpers ══════════════════════════════════

    def _extract_json_block(self, text: str, fallback_key: str) -> Dict:
        """从 LLM 返回中提取 JSON — 处理多种格式"""
        import re
        text = text.strip()

        # 1. 去 markdown 代码块 (含中文属性)
        if "```" in text:
            # 匹配 ```json ... ``` 或 ``` ... ```
            m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
            if m:
                text = m.group(1).strip()

        # 2. 提取第一个 JSON 对象或数组
        if text.startswith('{'):
            # 找匹配的结束括号
            depth = 0
            end = 0
            for i, ch in enumerate(text):
                if ch == '{': depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                text = text[:end]
        elif text.startswith('['):
            depth = 0
            end = 0
            for i, ch in enumerate(text):
                if ch == '[': depth += 1
                elif ch == ']':
                    depth -= 1
                    if depth == 0:
                        end = i + 1
                        break
            if end > 0:
                text = text[:end]

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"[{self.name}] JSON parse failed for {fallback_key}, returning raw")
            return {"raw_text": text[:800], "step": fallback_key}

    async def load_context(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        ctx = await super().load_context(ctx)
        ctx["macro"] = await self.data_loader.load_macro()
        return ctx

    def build_prompt(self, ctx: Dict[str, Any]) -> str:
        return "SupplyChainAnalyst — see _analyze_prosperity_signals etc."

    async def stream(self, context: Dict[str, Any]):
        yield "Supply chain analysis streaming not implemented"
