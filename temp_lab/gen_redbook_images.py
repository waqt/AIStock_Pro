"""
生成小红书配图 — Serenity 瓶颈投资法 → AIStock Pro Pipeline 映射
输出到 Local_data/redbook/ (已从 data/redbook 迁移)
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.font_manager as fm
import os

# ═══ 字体 ═══
FONT_PATH = r'C:\Windows\Fonts\simhei.ttf'
FONT_SONG = r'C:\Windows\Fonts\stsong.ttf'
fp = fm.FontProperties(fname=FONT_PATH)
fp_song = fm.FontProperties(fname=FONT_SONG)

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Local_data', 'redbook')
os.makedirs(OUTPUT_DIR, exist_ok=True)

COLORS = {
    'bg': '#0f0f1a',
    'card_bg': '#1a1a2e',
    'card_border': '#2a2a4a',
    'accent_gold': '#f0c040',
    'accent_blue': '#4a9eff',
    'accent_green': '#4ade80',
    'accent_purple': '#a78bfa',
    'accent_red': '#f87171',
    'accent_cyan': '#22d3ee',
    'text_primary': '#e8e8f0',
    'text_secondary': '#8888aa',
    'text_dim': '#555577',
}


def draw_rounded_rect(ax, x, y, w, h, color, text, text_color='#e8e8f0', fontsize=11,
                       edgecolor=None, linewidth=0, center=False, alpha=0.9):
    """Draw a rounded rectangle with centered text."""
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.15,rounding_size=4",
                          facecolor=color, edgecolor=edgecolor or color,
                          linewidth=linewidth, alpha=alpha)
    ax.add_patch(rect)
    ha = 'center' if center else 'left'
    tx = x + w/2 if center else x + 8
    ax.text(tx, y + h/2, text, fontproperties=fp, fontsize=fontsize,
            color=text_color, ha=ha, va='center', weight='bold')


def draw_arrow(ax, x1, y1, x2, y2, color='#555577', lw=2, style='->'):
    """Draw an arrow between two points."""
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle=style, color=color, lw=lw))


# ═══════════════════════════════════════════════════════════════
# FIGURE 1: Serenity → AIStock Pro Pipeline 核心映射图 (1080x1350)
# ═══════════════════════════════════════════════════════════════
def gen_main_mapping():
    fig, ax = plt.subplots(figsize=(8, 10))
    ax.set_xlim(0, 800)
    ax.set_ylim(0, 1000)
    ax.axis('off')
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])

    y_top = 960

    # ═══ 标题 ═══
    ax.text(400, y_top, 'Serenity 瓶颈投资法 → AIStock Pro 系统映射',
            fontproperties=fp, fontsize=18, color=COLORS['accent_gold'],
            ha='center', va='center', weight='bold')
    ax.text(400, y_top - 30, '从"手工挖瓶颈"到"AI 自动化 Pipeline"',
            fontproperties=fp_song, fontsize=11, color=COLORS['text_secondary'],
            ha='center', va='center')

    # ═══ 左侧：Serenity 手工法 ═══
    left_x = 40
    card_w = 320
    right_x = 440
    rh = 38  # row height

    # 标题头
    draw_rounded_rect(ax, left_x, 900, card_w, 36, '#2a1a0a',
                      '🧠  Serenity 手工挖掘', COLORS['accent_gold'],
                      edgecolor=COLORS['accent_gold'], linewidth=1.5,
                      fontsize=13, center=True)

    serenity_items = [
        ('1️⃣  跟踪 7 大瓶颈层', '光通信 / 封装 / HBM / 电力 / 散热 / 基板 / 能源', COLORS['accent_red']),
        ('2️⃣  识别不可替代环节', 'Nvidia 离不开的供应商 → 卡脖子节点', COLORS['accent_red']),
        ('3️⃣  人工搜索 + 阅读', 'Reddit / 财报 / 行业新闻 → 手动整理', COLORS['accent_red']),
        ('4️⃣  产出 ~38 只标的', '覆盖存储 / 光模块 / 电力 / 能源 / 加密', COLORS['accent_red']),
        ('5️⃣  人工追踪催化事件', '盯着产能 / 交期 / 价格变化', COLORS['accent_red']),
        ('⚠️  瓶颈', '个人精力有限, 无法系统覆盖所有产业链', COLORS['accent_red']),
    ]

    y = 850
    for title, desc, color in serenity_items:
        draw_rounded_rect(ax, left_x, y - rh, card_w, rh, '#1a1520',
                          title, color, fontsize=10, center=False)
        ax.text(left_x + card_w + 5, y - rh/2, desc, fontproperties=fp_song,
                fontsize=7.5, color=COLORS['text_secondary'], va='center')
        y -= rh + 4

    # ═══ 右侧：AIStock Pro Pipeline ═══
    draw_rounded_rect(ax, right_x, 900, card_w, 36, '#0a1a2a',
                      '⚡  AIStock Pro 自动化', COLORS['accent_blue'],
                      edgecolor=COLORS['accent_blue'], linewidth=1.5,
                      fontsize=13, center=True)

    pipeline_items = [
        ('Step 1a+1b  宏观+资本流向', '判断 AI CapEx 周期 → 确定产业大方向', COLORS['accent_cyan']),
        ('Step 2      行业看门人', '4 角度 Web 搜索 → LLM 识别瓶颈产业', COLORS['accent_blue']),
        ('Step 3      产业链拆解 (★核心)', 'L1→L4 自动拆解 → 定位瓶颈 + 利润池 + 资产发现',
         COLORS['accent_green']),
        ('Step 4+5    推演+外溢', '系统动力学 → 瓶颈是缓解还是加剧? 跨产业传导?', COLORS['accent_purple']),
        ('Step 6      核心资产筛选', 'LLM 逐只验证 → 38+ 标的排名 + watch_events',
         COLORS['accent_gold']),
        ('✅  系统覆盖全产业链', '不限精力, 任意行业都可拆解, 结果可复现', COLORS['accent_green']),
    ]

    y = 850
    for title, desc, color in pipeline_items:
        draw_rounded_rect(ax, right_x, y - rh, card_w, rh, '#0a1520',
                          title, color, fontsize=10, center=False)
        ax.text(right_x + card_w + 5, y - rh/2, desc, fontproperties=fp_song,
                fontsize=7.5, color=COLORS['text_secondary'], va='center')
        y -= rh + 4

    # ═══ 中间：双向箭头连接 ═══
    # 从 Serenity 到 System 的几个关键映射标注
    mapping_y = [845, 800, 755, 710, 665, 620]
    labels = ['', '', '★★★ 核心映射', '', '', '']
    for my in mapping_y:
        draw_arrow(ax, left_x + card_w, my, right_x, my, color='#444466', lw=1.5)

    # 中间标注
    ax.text(400, 800, '★★★', fontproperties=fp, fontsize=14,
            color=COLORS['accent_gold'], ha='center', va='center')
    ax.text(400, 785, '核心映射', fontproperties=fp, fontsize=10,
            color=COLORS['accent_gold'], ha='center', va='center')
    ax.text(400, 770, 'Serenity 的瓶颈理论', fontproperties=fp_song, fontsize=8,
            color=COLORS['text_secondary'], ha='center', va='center')
    ax.text(400, 757, '= Step 3 产业链拆解', fontproperties=fp_song, fontsize=8,
            color=COLORS['text_secondary'], ha='center', va='center')

    # ═══ 底部：系统全景扩展能力 ═══
    y_bottom = 560
    ax.text(400, y_bottom, '— 但 AIStock Pro 不止于此 —', fontproperties=fp_song,
            fontsize=11, color=COLORS['text_dim'], ha='center', va='center')

    # 四个扩展能力卡片
    ex_data = [
        ('📊  量化决策', '16算子 + 27财务指标\n21估值方法 + 8策略\n加权投票出买卖信号',
         COLORS['accent_blue']),
        ('🌐  数据中心', '多源行情同步\n宏观追踪 + 行业分类\n数据健康检查',
         COLORS['accent_green']),
        ('📋  持仓管理', 'AI截图导入\n每日快照 + 损益\n交易审计',
         COLORS['accent_purple']),
        ('👁  观察监控', 'Pipeline自动提取\nwatch_events追踪\n机会/风险预警',
         COLORS['accent_gold']),
    ]

    ex_w = 165
    ex_h = 100
    ex_gap = 15
    total_w = ex_w * 4 + ex_gap * 3
    ex_start_x = (800 - total_w) / 2

    for i, (title, desc, color) in enumerate(ex_data):
        ex_x = ex_start_x + i * (ex_w + ex_gap)
        draw_rounded_rect(ax, ex_x, y_bottom - ex_h - 20, ex_w, ex_h,
                          COLORS['card_bg'], '', edgecolor=color, linewidth=1.2, alpha=0.7)
        # Title
        ax.text(ex_x + ex_w/2, y_bottom - 30, title, fontproperties=fp, fontsize=9,
                color=color, ha='center', va='center', weight='bold')
        # Description
        ax.text(ex_x + ex_w/2, y_bottom - 55, desc, fontproperties=fp_song, fontsize=6.5,
                color=COLORS['text_secondary'], ha='center', va='top', linespacing=1.5)

    # ═══ 底部标签 ═══
    ax.text(400, 75, 'AIStock Pro  |  个人级 AI 量化投资操作系统',
            fontproperties=fp_song, fontsize=9, color=COLORS['text_dim'],
            ha='center', va='center')
    ax.text(400, 55, 'V5.16  •  AI 驱动  •  A股+港股  •  投研/量化/数据/持仓 闭环',
            fontproperties=fp_song, fontsize=7, color=COLORS['text_dim'],
            ha='center', va='center')

    # ═══ 保存 ═══
    plt.tight_layout(pad=0.5)
    path = os.path.join(OUTPUT_DIR, '01_serenity_pipeline_mapping.png')
    plt.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print(f'[OK] Generated: {path}')
    return path


# ═══════════════════════════════════════════════════════════════
# FIGURE 2: 系统核心架构 + 能力总览卡片 (1080x1080)
# ═══════════════════════════════════════════════════════════════
def gen_system_overview():
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 800)
    ax.set_ylim(0, 800)
    ax.axis('off')
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])

    # 标题
    ax.text(400, 770, 'AIStock Pro  V5.16', fontproperties=fp, fontsize=20,
            color=COLORS['accent_gold'], ha='center', va='center', weight='bold')
    ax.text(400, 745, 'AI 驱动的个人量化投资操作系统', fontproperties=fp_song, fontsize=12,
            color=COLORS['text_secondary'], ha='center', va='center')

    # ─── 核心层 (环形布局) ───
    modules = [
        (400, 620, '🧠  AI 投研 Pipeline', 'Step 1-6 | 8 Agents | 3 条路径', COLORS['accent_cyan']),
        (210, 460, '📊  量化决策引擎', '16算子 | 8策略 | 21估值 | 27财务', COLORS['accent_blue']),
        (590, 460, '🌐  数据中心', '行情同步 | 宏观 | 基本面 | 健康检查', COLORS['accent_green']),
        (210, 300, '📋  智能持仓', 'AI导入 | 快照 | 损益 | 审计', COLORS['accent_purple']),
        (590, 300, '👁  观察监控', '自动提取 | 催化剂追踪 | 预警', COLORS['accent_gold']),
    ]

    for cx, cy, title, desc, color in modules:
        rect = FancyBboxPatch((cx-120, cy-35), 240, 70,
                              boxstyle="round,pad=0.1,rounding_size=8",
                              facecolor=COLORS['card_bg'], edgecolor=color,
                              linewidth=1.5, alpha=0.8)
        ax.add_patch(rect)
        ax.text(cx, cy+5, title, fontproperties=fp, fontsize=12,
                color=color, ha='center', va='center', weight='bold')
        ax.text(cx, cy-18, desc, fontproperties=fp_song, fontsize=8,
                color=COLORS['text_secondary'], ha='center', va='center')

    # 中心圆
    circle = plt.Circle((400, 460), 42, color=COLORS['bg'], ec=COLORS['accent_gold'], lw=2)
    ax.add_patch(circle)
    ax.text(400, 460, 'AIStock\nPro', fontproperties=fp, fontsize=11,
            color=COLORS['accent_gold'], ha='center', va='center', weight='bold')

    # 连接线
    for cx, cy, _, _, _ in modules:
        dx = cx - 400
        dy = cy - 460
        dist = (dx**2 + dy**2)**0.5
        start_x = 400 + dx * 45 / dist
        start_y = 460 + dy * 45 / dist
        end_x = cx - dx * 122 / dist
        end_y = cy - dy * 37 / dist
        ax.plot([start_x, end_x], [start_y, end_y], color='#333355', lw=1.5, alpha=0.6)

    # ─── 底部技术栈 ───
    y_tech = 210
    ax.text(400, y_tech, '⚙️  技术栈', fontproperties=fp, fontsize=11,
            color=COLORS['text_secondary'], ha='center', va='center')

    techs = [
        ('Python 3.8+', '#4a9eff'), ('FastAPI', '#4a9eff'),
        ('SQLAlchemy 2.0', '#4ade80'), ('Pandas/NumPy', '#4ade80'),
        ('DeepSeek AI', '#a78bfa'), ('Brave Search', '#a78bfa'),
        ('ECharts 5.5', '#f0c040'), ('SQLite 宽表', '#f87171'),
    ]

    tech_w = 155
    tech_h = 26
    tech_gap = 12
    row1_x = (800 - tech_w * 4 - tech_gap * 3) / 2
    for i, (name, color) in enumerate(techs[:4]):
        tx = row1_x + i * (tech_w + tech_gap)
        draw_rounded_rect(ax, tx, y_tech - tech_h - 8, tech_w, tech_h,
                          '#151525', name, color, fontsize=8, center=True,
                          edgecolor=color, linewidth=0.5, alpha=0.6)

    row2_x = (800 - tech_w * 4 - tech_gap * 3) / 2
    for i, (name, color) in enumerate(techs[4:]):
        tx = row2_x + i * (tech_w + tech_gap)
        draw_rounded_rect(ax, tx, y_tech - tech_h * 2 - 16, tech_w, tech_h,
                          '#151525', name, color, fontsize=8, center=True,
                          edgecolor=color, linewidth=0.5, alpha=0.6)

    # ═══ 底部 ═══
    ax.text(400, 85, '个人级系统  |  免费接口  |  A 股 + 港股  |  V5.16',
            fontproperties=fp_song, fontsize=8, color=COLORS['text_dim'],
            ha='center', va='center')
    ax.text(400, 65, '每天自动跑 Pipeline → 量化决策 → 持仓复盘 → 催化监控',
            fontproperties=fp_song, fontsize=8, color=COLORS['text_dim'],
            ha='center', va='center')

    plt.tight_layout(pad=0.5)
    path = os.path.join(OUTPUT_DIR, '02_system_overview.png')
    plt.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print(f'[OK] Generated: {path}')
    return path


# ═══════════════════════════════════════════════════════════════
# FIGURE 3: Pipeline 步骤详解 (1080x1200)
# ═══════════════════════════════════════════════════════════════
def gen_pipeline_detail():
    fig, ax = plt.subplots(figsize=(8, 9))
    ax.set_xlim(0, 800)
    ax.set_ylim(0, 900)
    ax.axis('off')
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])

    ax.text(400, 875, 'AIStock Pro 投研 Pipeline  12 步分析链路',
            fontproperties=fp, fontsize=16, color=COLORS['accent_gold'],
            ha='center', va='center', weight='bold')
    ax.text(400, 855, '从宏观周期 → 产业链拆解 → 核心资产筛选',
            fontproperties=fp_song, fontsize=10, color=COLORS['text_secondary'],
            ha='center', va='center')

    # Pipeline 步骤
    steps = [
        ('Step 1a', '宏观周期分析', 'MAG7 CapEx → 产业景气方向', COLORS['accent_cyan'], '✅'),
        ('Step 1b', '资本流向扫描', '谁在花钱? 花在哪? 约束在哪?', COLORS['accent_cyan'], '✅'),
        ('Step 2', '行业看门人', '6-Block 定性筛选 + 错配分析', COLORS['accent_blue'], '✅'),
        ('', '──  [A] 直挖  [B] 二阶推演  [C] 深挖  ──', '', COLORS['text_dim'], '🔀'),
        ('Step 3', '产业链拆解 ★', 'L1-L4 瓶颈图谱 + 利润池 + 竞争格局', COLORS['accent_green'], '✅'),
        ('Step 4', '系统动力学', '供给/需求/政策三维推演', COLORS['accent_purple'], '✅'),
        ('Step 5', '跨产业关联', '溢出效应 + 传导路径', COLORS['accent_purple'], '✅'),
        ('Step 6', '核心资产筛选', '搜索→LLM→比较→验证→排名, 38+ 标的', COLORS['accent_gold'], '✅'),
        ('Step 7', '财务质量审计', '8Q剪刀差 + Beneish M-Score', '#f87171', '⚡'),
        ('Step 8', '人力资本/估值', '创始人审计 + 21 方法估值', '#f87171', '⚡'),
        ('Step 9-11', '预期差/风险/报告', '📋 规划中', COLORS['text_dim'], '📋'),
    ]

    y = 810
    step_h = 38
    step_gap = 4
    for label, name, desc, color, status in steps:
        y -= step_h + step_gap
        if label == '':
            ax.text(400, y + step_h/2, name, fontproperties=fp_song, fontsize=8,
                    color=COLORS['text_dim'], ha='center', va='center')
            continue

        # Step label
        draw_rounded_rect(ax, 25, y, 85, step_h, '#151525', f'{status} {label}', color,
                          fontsize=8, center=True, edgecolor=color, linewidth=0.5, alpha=0.6)
        # Name
        ax.text(130, y + step_h/2, name, fontproperties=fp, fontsize=10,
                color=color, va='center', weight='bold')
        # Desc
        ax.text(290, y + step_h/2, desc, fontproperties=fp_song, fontsize=7.5,
                color=COLORS['text_secondary'], va='center')

        # 连接箭头
        if y > 100:
            ax.plot([65, 65], [y + step_h, y - step_gap], color='#333355', lw=1.5, alpha=0.5)

    # 底部
    ax.text(400, 60, '✅ 已实现  |  ⚡ 已有, 待更新  |  📋 规划中',
            fontproperties=fp_song, fontsize=8, color=COLORS['text_dim'],
            ha='center', va='center')
    ax.text(400, 40, '核心亮点: Step 3 产业链拆解 = Serenity 瓶颈理论自动化版本',
            fontproperties=fp, fontsize=9, color=COLORS['accent_gold'],
            ha='center', va='center')

    plt.tight_layout(pad=0.5)
    path = os.path.join(OUTPUT_DIR, '03_pipeline_detail.png')
    plt.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print(f'[OK] Generated: {path}')
    return path


# ═══════════════════════════════════════════════════════════════
# FIGURE 4: 量化能力展示 (1080x1080)
# ═══════════════════════════════════════════════════════════════
def gen_quant_capabilities():
    fig, ax = plt.subplots(figsize=(8, 8))
    ax.set_xlim(0, 800)
    ax.set_ylim(0, 800)
    ax.axis('off')
    fig.patch.set_facecolor(COLORS['bg'])
    ax.set_facecolor(COLORS['bg'])

    ax.text(400, 770, '📊  量化决策中心', fontproperties=fp, fontsize=18,
            color=COLORS['accent_blue'], ha='center', va='center', weight='bold')
    ax.text(400, 748, '指标计算 → 策略决策 → 信号输出的完整链路',
            fontproperties=fp_song, fontsize=10, color=COLORS['text_secondary'],
            ha='center', va='center')

    # ─── 4 象限 ───
    quad_data = [
        (60, 520, 320, 200, '技术指标算子  16', [
            '趋势: MA / MACD / KDJ',
            '动量: RSI / ATR / CCI',
            '波动: Bollinger / BB Width',
            '量能: OBV / VolumeMA / VWAP',
            '筹码: 集中度 / 峰值 / 形态',
            '拥挤度: Turnover / Sharpe 60d',
        ], COLORS['accent_cyan']),
        (420, 520, 320, 200, '财务指标  27', [
            '盈利能力: ROE / ROIC / 毛利率',
            '成长: 营收增速 / 剪刀差 / 杠杆',
            '健康: 合同负债 / 存货 / OCF',
            '质量: Beneish M-Score',
            '全部基于季度财报计算',
            '自动滚动窗口, newest-first',
        ], COLORS['accent_green']),
        (60, 280, 320, 200, '估值方法  21', [
            '绝对: DCF / 戈登增长 / NAV',
            '相对: PE分位 / PB分位 / PS',
            '动态: PEG / 剪刀差折价',
            '先进: ROIC Spread / 场景估计',
            '复合: Valuation Health Score',
            '自注册架构, 随时可扩展',
        ], COLORS['accent_purple']),
        (420, 280, 320, 200, '策略 - 决策', [
            '6 传统策略 (代码)',
            '2 AI 链策略 (YAML 热编辑)',
            '决策中心: 并行调度加权投票',
            '传统权重 1.0 / AI 链 1.2',
            'BUY > SELL × 1.5 → 买入',
            '决策结果持久化, 可追溯',
        ], COLORS['accent_gold']),
    ]

    for qx, qy, qw, qh, title, items, color in quad_data:
        rect = FancyBboxPatch((qx, qy), qw, qh,
                              boxstyle="round,pad=0.1,rounding_size=6",
                              facecolor=COLORS['card_bg'], edgecolor=color,
                              linewidth=1.2, alpha=0.7)
        ax.add_patch(rect)
        ax.text(qx + qw/2, qy + qh - 18, title, fontproperties=fp, fontsize=11,
                color=color, ha='center', va='center', weight='bold')
        for j, item in enumerate(items):
            ax.text(qx + 12, qy + qh - 42 - j * 22, f'• {item}',
                    fontproperties=fp_song, fontsize=7.5, color=COLORS['text_secondary'],
                    va='center')

    # 中心连接
    ax.text(400, 470, 'SQLite 宽表存储', fontproperties=fp_song, fontsize=8,
            color=COLORS['text_dim'], ha='center', va='center')
    ax.text(400, 230, '前端 ECharts 图表 | 指标查询 API | 全覆盖检测',
            fontproperties=fp_song, fontsize=8, color=COLORS['text_dim'],
            ha='center', va='center')

    plt.tight_layout(pad=0.5)
    path = os.path.join(OUTPUT_DIR, '04_quant_capabilities.png')
    plt.savefig(path, dpi=200, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close()
    print(f'[OK] Generated: {path}')
    return path


if __name__ == '__main__':
    gen_main_mapping()
    gen_system_overview()
    gen_pipeline_detail()
    gen_quant_capabilities()
    print(f'\nAll images saved to: {OUTPUT_DIR}')
