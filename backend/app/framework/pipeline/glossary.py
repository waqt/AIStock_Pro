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
    ])


def step3_glossary() -> str:
    """Step 3 (SupplyChain) 需要的术语"""
    return inject_glossary("", [
        "cycle_phase", "prosperity_type",
    ])


def step4_glossary() -> str:
    """Step 4 (System Dynamics) 需要的术语"""
    return inject_glossary("", [
        "cycle_phase", "prosperity_type", "demand_quality",
        "propagation_depth",
    ])
