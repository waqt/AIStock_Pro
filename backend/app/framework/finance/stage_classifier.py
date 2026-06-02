"""
StageClassifier — LLM 企业生命周期分类器
接收 financial_data_view + 可选上下文, 由 LLM 定性判断生命周期阶段

核心原则: LLM 做定性归类, 不做主观评分。
输出分类标签 + 推理依据, 不输出数字评分。

使用方式:
  classifier = StageClassifier(provider=deepseek_provider)
  result = await classifier.classify(financial_view, context={"industry": "半导体设备"})
"""
from typing import Dict, Any, Optional
from app.framework.logger import logger


# ═══ 生命周期阶段定义 ══════════════════════════════

LIFECYCLE_STAGES = {
    "startup": {
        "label": "初创期",
        "description": "营收规模小(<5000万/年), 可能亏损, 高研发强度(>20%), 产品或技术尚在验证",
        "financial_signals": "低营收, 负利润或微利, 研发强度极高, 毛利率可能高(轻资产)或低(硬件)"
    },
    "inflection": {
        "label": "拐点期",
        "description": "营收下滑但研发投入高(押注下一曲线), 或营收暴增但刚扭亏, 即将进入爆发期的前夜",
        "financial_signals": "营收增速为负或极高(>40%), 研发强度>15%, 可能亏损, 毛利率分化"
    },
    "growth": {
        "label": "成长期",
        "description": "营收高速增长(>20%), 正利润, 毛利率健康, 规模效应开始显现",
        "financial_signals": "营收YoY>20%, 正利润且同步增长, 毛利率>15%, 剪刀差可能为正, OCF逐步改善"
    },
    "mature": {
        "label": "成熟期",
        "description": "营收增速放缓(<20%), 利润稳定, 高毛利率, 现金流充沛, 可能高分红",
        "financial_signals": "营收YoY 0-20%, 利润稳定增长, 毛利率>20%, OCF健康, ROIC较高"
    },
    "cyclical_bottom": {
        "label": "周期底部",
        "description": "营收下滑但幅度收敛, 利润承压但不恶化, 基本面未破坏, 等待反转信号",
        "financial_signals": "营收YoY负增长(> -20%), 利润承压, 毛利率低, 但有企稳迹象, 存货可能在去化"
    },
    "cyclical_decline": {
        "label": "周期衰退",
        "description": "营收和利润持续恶化, 行业格局变化, 可能需要转型或退出",
        "financial_signals": "营收YoY持续负增长, 利润加速恶化, 毛利率持续下降, 现金流紧张, 存货积压"
    },
}


# ═══ 阶段关系 ══════════════════════════════════════

STAGE_PROGRESSION = {
    "startup": ["inflection", "growth"],
    "inflection": ["growth", "startup"],
    "growth": ["mature", "cyclical_decline"],
    "mature": ["cyclical_bottom", "cyclical_decline"],
    "cyclical_bottom": ["growth", "cyclical_decline"],
    "cyclical_decline": ["cyclical_bottom", "inflection"],
}


class StageClassifier:
    """LLM 企业生命周期分类器 — 基于财务数据做定性阶段判定"""

    def __init__(self, provider: Any):
        """
        Args:
            provider: LLM provider, 需有 chat_flash() 和 chat_pro() 方法
        """
        self.provider = provider

    # ═══ 主入口 ═══════════════════════════════════════

    async def classify(
        self,
        financial_view: Dict,
        context: Optional[Dict] = None,
    ) -> Dict:
        """基于财务数据判定生命周期阶段

        Args:
            financial_view: build_financial_data_view() 的输出
            context: 可选上下文, 支持:
                - industry: 行业名称
                - cycle_position: 产业周期阶段 (来自 Step 2/3)
                - stock_name: 股票名称
                - stock_code: 股票代码

        Returns:
            {
                "stage": "startup|inflection|growth|mature|cyclical_bottom|cyclical_decline",
                "confidence": "high|medium|low",
                "reasoning": "详细推理过程",
                "key_signals": ["关键信号1", "关键信号2"],
                "error": None  # 失败时有错误信息
            }
        """
        # 验证数据
        if not financial_view or financial_view.get("error"):
            return self._fallback(financial_view, "数据不足, 无法分类")

        profile = financial_view.get("company_profile", {})
        if not profile.get("quarters_available", 0):
            return self._fallback(financial_view, "无季度数据")

        # 构建 prompt
        prompt = self._build_prompt(financial_view, context or {})

        try:
            text = await self.provider.chat_flash(prompt, max_tokens=2048, timeout=90)
        except Exception as e:
            logger.warning(f"[StageClassifier] LLM call failed: {e}, falling back")
            return self._fallback(financial_view, f"LLM调用失败: {e}")

        # 解析
        try:
            result = self._parse_result(text)
            if result.get("stage") in LIFECYCLE_STAGES:
                logger.info(
                    f"[StageClassifier] "
                    f"{context.get('stock_code', '')} {context.get('stock_name', '')} "
                    f"→ {result['stage']} (conf={result.get('confidence','?')})"
                )
                result["error"] = None
                return result
            else:
                logger.warning(f"[StageClassifier] Invalid stage: {result.get('stage')}")
                return self._fallback(financial_view, f"无效阶段: {result.get('stage')}")
        except Exception as e:
            logger.warning(f"[StageClassifier] Parse failed: {e}")
            return self._fallback(financial_view, f"解析失败: {e}")

    # ═══ Prompt 构建 ═══════════════════════════════════

    def _build_prompt(self, fv: Dict, ctx: Dict) -> str:
        """构建分类 prompt"""
        profile = fv.get("company_profile", {})
        growth = fv.get("growth_trajectory", {})
        profit = fv.get("profitability", {})
        scissor = fv.get("scissor_analysis", {})
        rd = fv.get("rd_impact", {})
        health = fv.get("financial_health", {})
        audit = health.get("audit", {})
        dq = fv.get("data_quality", {})

        # 上下文行
        ctx_lines = []
        if ctx.get("industry"):
            ctx_lines.append(f"- 所属行业: {ctx['industry']}")
        if ctx.get("cycle_position"):
            ctx_lines.append(f"- 产业周期阶段: {ctx['cycle_position']}")
        if ctx.get("stock_name"):
            ctx_lines.append(f"- 公司名称: {ctx['stock_name']}")

        return f"""你是一位企业生命周期分析师。根据以下财务数据, 判断该公司所处的生命周期阶段。

## 可选阶段

{self._stage_definitions_text()}

## 财务数据全景

公司画像:
- 最近4Q营收: {profile.get('revenue_4q_yi', '?')} 亿
- 最近4Q利润: {profile.get('profit_4q_yi', '?')} 亿
- 营收规模: {profile.get('revenue_scale', '?')}
- 毛利率: {profile.get('gross_margin_pct', '?')}%
- 净利率: {profile.get('net_margin_pct', '?')}%
- 研发强度: {profile.get('rd_intensity_pct', '?')}%

增长轨迹:
- 营收同比(最新): {growth.get('rev_yoy_latest', '?')}%
- 利润同比(最新): {growth.get('profit_yoy_latest', '?')}%
- 营收环比(最新): {growth.get('rev_qoq_latest', '?')}%
- 近4Q平均营收增速: {growth.get('avg_rev_yoy_4q', '?')}%
- 近4Q平均利润增速: {growth.get('avg_profit_yoy_4q', '?')}%

盈利能力:
- ROIC: {profit.get('roic', {}).get('roic_pct', '?')}%
- ROIIC: {profit.get('roiic', {}).get('roiic_pct', '?')}%
- ROE: {profit.get('roe', '?')}%
- 研发调整后ROE: {profit.get('adjusted_roe', '?')}%

剪刀差分析:
- 最新剪刀差: {scissor.get('latest_gap_pct', '?')}% (正=利润率扩张)
- 是否扩大: {"是" if scissor.get('is_expanding') else "否"}
- 剪刀差为正的季度数: {scissor.get('scissor_quarters_count', '?')}

研发资本化影响:
- 研发投入强度: {rd.get('rd_intensity_pct', '?')}%
- 研发资本化后利润变动: {rd.get('profit_impact_pct', '?')}%
- 调整影响是否重大: {"是" if rd.get('material') else "否"}

财务健康审计:
- 审计 verdict: {audit.get('verdict', '?')}
- 审计 score: {audit.get('score', '?')}
- 存货趋势: {audit.get('inventory_trend', '?')}
- 合同负债趋势: {audit.get('contract_liability_trend', '?')}
- OCF健康度: {audit.get('ocf_health', '?')}
- Beneish M-Score: {health.get('beneish', {}).get('m_score', '?')}
  - 解读: {health.get('beneish', {}).get('interpretation', '?')}

数据质量: 8Q齐全={'是' if dq.get('all_8q_available') else '否'},
有研发支出={'是' if dq.get('has_rd_expense') else '否'},
有经营现金流={'是' if dq.get('has_op_cashflow') else '否'}
{self._context_block(ctx)}

## 判断规则

1. 只根据上述财务数据做判断, 不要考虑市场情绪、股价、估值
2. 优先关注最近4Q的趋势, 而非单季数据
3. 研发强度>15%是"inflection"的重要信号
4. "cyclical_bottom"和"cyclical_decline"的关键区别:
   - bottom: 营收下滑但幅度在收敛, 基本面未进一步恶化
   - decline: 营收和利润持续加速恶化, 格局性变化
5. 边界情况选择最接近的阶段, 不要创造新阶段
6. 宁可偏向growth/early stage, 不要过早归类到decline

请输出JSON, 不要包含其他内容:
{{
  "stage": "阶段标识",
  "confidence": "high|medium|low",
  "reasoning": "详细推理过程(中文, 2-4句话)",
  "key_signals": ["最关键信号1", "最关键信号2", "最关键信号3"]
}}
"""

    @staticmethod
    def _stage_definitions_text() -> str:
        """生成阶段定义文本"""
        lines = []
        for sid, info in LIFECYCLE_STAGES.items():
            lines.append(f"- {sid} ({info['label']}): {info['description']}")
            lines.append(f"  财务特征: {info['financial_signals']}")
        return "\n".join(lines)

    @staticmethod
    def _context_block(ctx: Dict) -> str:
        """生成上下文信息块"""
        if not ctx:
            return ""
        lines = ["", "## 参考信息"]
        if ctx.get("industry"):
            lines.append(f"- 所属行业: {ctx['industry']}")
        if ctx.get("cycle_position"):
            lines.append(f"- 产业周期阶段: {ctx['cycle_position']}")
        if ctx.get("stock_name"):
            lines.append(f"- 公司: {ctx['stock_name']} ({ctx.get('stock_code', '')})")
        return "\n".join(lines)

    # ═══ 解析 ═════════════════════════════════════════

    @staticmethod
    def _parse_result(text: str) -> Dict:
        """从 LLM 输出中解析 JSON"""
        import json, re

        # 尝试直接解析
        text = text.strip()
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # 提取 ```json ... ``` 块
        m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 提取 { ... } 块
        m = re.search(r'\{[^}]+\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0).strip())
            except json.JSONDecodeError:
                pass

        raise ValueError(f"Cannot parse LLM output: {text[:200]}")

    # ═══ 降级 ═════════════════════════════════════════

    def _fallback(self, financial_view: Dict, reason: str) -> Dict:
        """LLM 失败时用老 decision tree 降级"""
        quarters = (financial_view.get("quarterly_metrics") if financial_view else None) or []
        # 简化降级: 用 profile 做粗略判断
        profile = financial_view.get("company_profile", {}) if financial_view else {}
        rev_scale = profile.get("revenue_scale", "tiny")
        net_margin = profile.get("net_margin_pct", 0) or 0
        rd_intensity = profile.get("rd_intensity_pct", 0) or 0
        growth = financial_view.get("growth_trajectory", {}) if financial_view else {}
        avg_rev_yoy = growth.get("avg_rev_yoy_4q", 0) or 0

        # 粗略 rule-based 判定
        if avg_rev_yoy > 20 and net_margin > 0:
            stage = "growth"
        elif avg_rev_yoy < -10 and rd_intensity > 10:
            stage = "inflection"
        elif avg_rev_yoy < -10:
            stage = "cyclical_bottom"
        elif avg_rev_yoy < 0 and net_margin < 0:
            stage = "cyclical_decline"
        elif rev_scale in ("tiny", "small") and rd_intensity > 15:
            stage = "startup"
        elif net_margin > 15:
            stage = "mature"
        else:
            stage = "growth"

        return {
            "stage": stage,
            "confidence": "low",
            "reasoning": f"降级规则判定 (LLM不可用: {reason})",
            "key_signals": ["降级判定, 建议人工复核"],
            "error": reason,
        }
