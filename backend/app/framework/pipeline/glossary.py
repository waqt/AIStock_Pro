"""
Pipeline 术语表 — 跨 Step 语义一致的唯一权威来源。
每增加一个新概念，只在这里定义一次。所有 Agent prompt 自动注入相关条目。
"""
from typing import Dict, List

# ═══ 术语定义 ═══════════════════════════════════════

GLOSSARY: Dict[str, Dict[str, str]] = {

    # ── 产业周期阶段 (Step 2 → Step 3/4/8) ──
    "cycle_phase": {
        "theme_emergence": "主题形成期 — 技术验证阶段, 收入未体现, 市场不信, Alpha最大但不确定性也最大",
        "demand_explosion": "需求爆发期 — 订单暴增, 渗透率快速拉升, 股价开始涨, 市场开始关注",
        "bottleneck_formation": "瓶颈形成期 — 交期暴涨, 价格上涨, 供给响应不足, 利润向瓶颈环节集中, 这是超额利润最丰厚的阶段",
        "capital_frenzy": "资本狂热期 — 全行业扩产, 新进入者涌入, VC/政府补贴加码, 高利润吸引过度投资, 危险开始积累",
        "capacity_release": "产能释放期 — 新增供给大量投放, 价格开始松动, 供需缺口收敛, 超额利润消退",
        "commoditization": "商品化期 — 价格战, ROE崩塌, 行业出清, 只有成本最低者幸存",
        "sub_phase": {
            "early": "该阶段的初期, 市场尚未充分认知变化",
            "mid": "该阶段的中期, 趋势已经被确认但仍有空间",
            "late": "该阶段的末期, 即将切换到下一阶段, 需关注 phase_switch_trigger",
        },
    },

    # ── 景气类型 (Step 2 → Step 3/4/8) ──
    "prosperity_type": {
        "demand_explosion": "需求爆发型 — 下游需求出现结构性跃升(AI/新能源/国产替代), 供给暂时无法响应, 持续性取决于需求曲线斜率",
        "supply_shock": "供给冲击型 — 供给端受到约束(资源枯竭/设备禁令/认证壁垒/政策限制), 需求稳定但供给减少, 持续性远超市场预期",
        "policy_driven": "政策驱动型 — 补贴/配额/政府采购推动景气, 持续性取决于政策稳定性, 可能突然终止",
        "replacement_cycle": "更新周期型 — 存量设备的自然更新换代, 周期性强, 一轮一轮",
        "capex_cycle": "资本开支周期型 — 产能扩张→过剩→出清→再扩产, 典型的周期品逻辑",
        "inventory_cycle": "库存周期型 — 补库→去库, 周期最短, 容易把补库误判为终端需求爆发",
    },

    # ── 需求质量 (Step 2 → Step 4/9) ──
    "demand_quality": {
        "real_demand": "真实终端需求 — 最终消费者的实际使用在增长(DAU上升/用电量增加/终端出货增长), 非渠道行为",
        "inventory_restock": "库存回补 — 渠道从去库转向补库, 短期拉动出货但终端需求未变, 补完即结束",
        "policy_pull_forward": "政策透支 — 补贴退坡前抢装/抢购, 透支未来需求, 政策窗口关闭后需求骤降",
        "channel_stuffing": "渠道压货 — 厂商向渠道压货美化财报, 渠道库存积压, 后续必然去库存",
    },

    # ── 赔率 (Step 2 → Step 6) ──
    "payoff_asymmetry": {
        "强非对称": "上涨空间远大于下跌空间 — 如: 若景气兑现利润5x, 若证伪需求只是推迟非消失, 下行有限",
        "对称": "涨跌空间大致相当 — 风险和收益基本平衡, 适合作为组合配置但不宜重仓",
        "负非对称": "下跌空间大于上涨空间 — 如: CAPEX即将大量释放, 下行风险显著, 上行已被充分定价",
    },

    # ── 传导深度 (Step 2 → Step 3/4) ──
    "propagation_depth": {
        "深": "产业链传导超过5层, 每解决一个瓶颈就创造新瓶颈, 多轮轮动机会",
        "中": "产业链传导3-5层, 有轮动空间但有限",
        "浅": "产业链传导不到3层, 利润集中在少数环节, 轮动空间小",
    },

    # ── 重新定价阶段 (Step 2 → Step 9) ──
    "market_repricing_stage": {
        "早期": "市场刚开始意识到变化, 股价反映不到30%, 预期差最大",
        "中期": "市场已部分定价, 股价反映了50-70%, 还有空间但需催化剂",
        "晚期": "接近充分定价, 股价反映了80%+, 即使景气兑现上行空间也有限",
    },

    # ── Priority (Step 2 → Pipeline) ──
    "priority": {
        "高": "五错配全部满足, 强烈建议进入Step3深度推演",
        "中": "满足3-4条错配, 值得关注但可能不如高优先级行业确定",
        "低": "仅满足1-2条错配, 存在较大不确定性或已被市场充分定价",
        "跳过": "不满足核心错配条件, 或者属于不适合本系统分析的资产类型(如纯金融资产)",
    },

    # ── Kill Reason (Step 2) ──
    "kill_reason": {
        "需求来自渠道补库存": "景气是假的, 只是库存周期波动",
        "已进入资本狂热后期": "全行业都在扩产, 未来必然过剩",
        "估值透支3年增长": "即使景气兑现, 当前价格也已充分反映, 无安全边际",
        "政策抢装非真实需求": "景气来自补贴窗口, 持续性存疑",
        "供给扩张>需求": "产能增速超过需求增速, 供需缺口正在收敛而非扩大",
        "传导链<3层Alpha空间有限": "产业链太短, 轮动空间小, 不值得深度推演",
    },

    # ── 利润迁移方向 (Step 2) ──
    "profit_redistribution_direction": {
        "upstream": "利润向上游迁移（原材料/设备/资源瓶颈受益）",
        "midstream": "利润在中游集中（制造/加工/封装测试）",
        "downstream": "利润向下游迁移（渠道/品牌/应用/解决方案）",
        "分散": "利润全线受益, 无明显集中方向",
    },

    # ── 论文杀手 (Step 2) ──
    "thesis_killers": {
        "substitution_risk": "替代技术/商业模式在3年内颠覆该产业链的风险",
        "policy_block_risk": "政策/地缘政治因素阻断投资逻辑的风险",
        "investable_exposure": "A股可投资标的的敞口充足程度",
    },

    # ── 供给刚性严重程度 (Step 3 → Step 4/6/8) ──
    "supply_rigidity_severity": {
        "extreme": "供给完全刚性 — 独家供应, 零替代, 扩产>18个月",
        "high": "供给严重受限 — CR2垄断, 替代方案不成熟, 扩产>12个月",
        "moderate": "供给偏紧 — CR3-5竞争, 扩产6-12个月, 有替代但成本高",
        "low": "供给充裕 — 充分竞争, 扩产<6个月, 多替代方案",
        "oversupply": "供给过剩 — 产能严重过剩, 价格战风险",
    },

    # ── 供给刚性根因 (Step 3 → Step 4/6) ──
    "rigidity_root_cause": {
        "equipment_constraint": "设备交期约束 — EUV光刻机/CoWoS封装设备等关键设备供应受限",
        "natural_resource": "自然资源稀缺 — 高纯石英砂/稀土/锂矿等不可再生或地理集中资源",
        "certification_barrier": "客户认证壁垒 — 车规(3-5年)/航空/医疗等长周期认证",
        "policy_restriction": "政策/出口管制 — 美国设备禁令/日本材料限制/国产化政策要求",
        "capital_scale": "资本规模门槛 — 晶圆厂($10B+)/面板厂等高CAPEX壁垒",
    },

    # ── 扩产周期 (Step 3 → Step 4/9, V1.1 三档对齐) ──
    "expand_cycle": {
        "under_12m": "12个月内可扩产",
        "12_24m": "12-24个月可扩产",
        "over_24m": "超过24个月才能实质性扩产",
    },

    # ── 替代性 (Step 3 → Step 4) ──
    "substitutability_level": {
        "none_short_term": "短期(2年内)无任何替代方案",
        "partial_high_cost": "有替代方案但成本/性能显著劣势, 无法大规模切换",
        "partial_emerging": "替代方案正在验证中, 2-3年内可能成熟",
        "multiple_options": "存在多个成熟替代方案, 切换成本低",
    },

    # ── 供应商集中度 (Step 3 → Step 6) ──
    "supplier_concentration": {
        "monopoly_single_supplier": "独家供应 — 单一供应商>90%份额",
        "duopoly": "双寡头 — CR2>80%",
        "oligopoly": "寡头竞争 — CR3-5>60%",
        "fragmented": "分散竞争 — CR5<40%",
    },

    # ── 利润池份额 (Step 3 → Step 6/8) ──
    "profit_pool_share": {
        "dominant_30_50pct": "占据行业30-50%利润, 是产业链最大利润池",
        "significant_15_30pct": "占据行业15-30%利润",
        "moderate_5_15pct": "占据行业5-15%利润",
        "marginal_below_5pct": "不足行业5%利润, 对整体利润影响有限",
    },

    # ── 毛利率水平 (Step 3 → Step 8) ──
    "margin_level": {
        "very_high_above_40pct": "毛利率>40%, 典型轻资产/高技术壁垒特征",
        "high_25_40pct": "毛利率25-40%",
        "moderate_15_25pct": "毛利率15-25%",
        "low_below_15pct": "毛利率<15%, 低附加值/重资产特征",
    },

    # ── 关注度质量 (Step 3 → Step 9) ──
    "attention_quality": {
        "profit_real": "热度高且利润确实集中 — 稀缺溢价合理, 非泡沫",
        "profit_diverted": "热度高但利润被上游抽走 — 警惕炒作, 利润不在关注焦点上",
        "under_the_radar": "关注度低但利润捕获好 — 预期差最大, Alpha来源",
        "deservedly_low": "关注度低且确实不赚钱 — 合理回避",
    },

    # ── 国产化率 (Step 3 → Step 6) ──
    "china_substitution_rate": {
        "below_5pct": "国产化率<5% — 几乎完全依赖进口, 国产替代空间极大但难度最高",
        "5_20pct": "国产化率5-20% — 开始替代但技术差距显著",
        "20_50pct": "国产化率20-50% — 快速追赶中, 部分环节已具备竞争力",
        "above_50pct": "国产化率>50% — 已具备全球竞争力, 国产替代空间有限",
    },

    # ── 未来2-3年展望 (Step 3 → Step 4/9) ──
    "future_outlook": {
        "bottleneck_persists": "瓶颈持续 — 2-3年内供给侧无实质性缓解, 景气窗口清晰",
        "bottleneck_easing": "瓶颈缓解 — 新增产能/替代方案正在落地, 超额利润窗口收窄",
        "bottleneck_resolved": "瓶颈解除 — 供给将追上甚至超过需求, 警惕周期反转",
        "new_bottleneck_emerging": "新瓶颈形成 — 当前宽松但2-3年内可能收紧, 前瞻布局机会",
    },

    # ── 瓶颈严重程度 (Step 3 V5.11b, 替换 chokepoint_score 数值评分) ──
    "bottleneck_severity": {
        "very_high": "极度瓶颈 — 独家或双寡头垄断, 供给侧完全无弹性, 景气窗口最清晰",
        "high": "严重瓶颈 — CR3控制>80%产能, 扩产周期>12个月, 供给侧弹性有限",
        "moderate": "中度瓶颈 — 供给偏紧但有替代方案, 扩产6-12个月可部分缓解",
        "low": "轻度瓶颈 — 供给充裕或竞争激烈, 定价权有限",
        "none": "非瓶颈 — 充分竞争或产能过剩, 供给侧不是约束因素",
    },

    # ── 竞争行为模式 (Step 3 V5.11b sub_processes) ──
    "pricing_behavior": {
        "monopoly": "独家垄断 — 完全定价权, 无竞争约束",
        "collusive_oligopoly": "寡头合谋 — 产能协同/人为控量, 不打价格战, 事实上的垄断定价权",
        "capacity_war": "产能竞赛 — 大家都在扩产抢份额, 定价权恶化中, 价格竞争激烈",
        "price_taker": "价格接受者 — 充分竞争, 无定价权, 跟随市场价格",
    },

    # ── 价值量级 (Step 3 V5.11b sub_processes) ──
    "value_magnitude": {
        "100B+": "千亿美元级市场 (如 HBM 制造、AI 加速卡)",
        "10B_100B": "百亿美元级市场 (如 CoWoS 封装、ABF 载板)",
        "1B_10B": "十亿美元级市场 (如 TSV 设备、先进封装材料)",
        "<1B": "十亿美元以下 (如 TIM 散热、探针卡等小众环节)",
        "unknown": "无搜索结果, 无法估算",
    },

    # ── 价值份额 (Step 3 V5.11b sub_processes) ──
    "value_share": {
        "dominant": "主导地位 (>50% 份额)",
        "major": "重要参与者 (15-50%)",
        "challenger": "挑战者 (<15%, 但增速快或有技术突破)",
        "niche": "小众/边缘参与者",
    },
}


# ═══ Prompt 注入 ═══════════════════════════════════════

def inject_glossary(prompt: str, categories: List[str] = None) -> str:
    """在 LLM prompt 末尾注入相关术语定义。

    Args:
        prompt: 原始 prompt
        categories: 需要注入的术语类别, 如 ["cycle_phase", "prosperity_type"]
                   为 None 时注入全部
    """
    cats = categories or list(GLOSSARY.keys())
    lines = ["\n## 术语定义 (你必须严格遵守以下枚举值, 不要自创)\n"]
    for cat in cats:
        if cat in GLOSSARY:
            lines.append(f"### {cat}")
            for key, val in GLOSSARY[cat].items():
                if isinstance(val, dict):
                    lines.append(f"  {key}:")
                    for sk, sv in val.items():
                        lines.append(f"    {sk} — {sv}")
                else:
                    lines.append(f"  {key} — {val}")
            lines.append("")
    return prompt + "\n".join(lines)


def step2_glossary() -> str:
    """Step 2 (Gatekeeper) 需要的术语"""
    return inject_glossary("", [
        "cycle_phase", "prosperity_type", "demand_quality",
        "payoff_asymmetry", "propagation_depth", "market_repricing_stage",
        "priority", "kill_reason",
        "profit_redistribution_direction", "thesis_killers",
    ])


def step3_glossary() -> str:
    """Step 3 (SupplyChain) 需要的术语"""
    return inject_glossary("", [
        "cycle_phase", "prosperity_type",
        "supply_rigidity_severity", "rigidity_root_cause", "expand_cycle",
        "substitutability_level", "supplier_concentration",
        "profit_pool_share", "margin_level",
        "attention_quality", "china_substitution_rate", "future_outlook",
        # V5.11b
        "bottleneck_severity", "pricing_behavior", "value_magnitude", "value_share",
    ])


def step4_glossary() -> str:
    """Step 4 (System Dynamics) 需要的术语 — V5.12 扩展"""
    return inject_glossary("", [
        "cycle_phase", "prosperity_type", "demand_quality",
        "propagation_depth",
        # V5.12: Step 2 交叉验证 + sub_processes 消费
        "supply_rigidity_severity",
        "bottleneck_severity",
        "pricing_behavior",
        "substitutability_level",
        "value_magnitude",
        "value_share",
        "future_outlook",
        "attention_quality",
        "profit_pool_share",
        "margin_level",
        "china_substitution_rate",
    ])
