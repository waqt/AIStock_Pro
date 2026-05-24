"""筹码分布图生成 — 用于与手机软件比对验证"""
import sys
sys.path.insert(0, r'E:\workspace\AIResearch\AIStock_Pro\backend')

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('TkAgg')
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
matplotlib.rcParams['axes.unicode_minus'] = False

from app.framework.database.session import async_session
from app.models.models import MarketData
from sqlalchemy import select
import asyncio


def calc_chip_distribution(df, window=0, bins=400, decay_half=45):
    """
    换手衰减法计算筹码分布 (接近通达信 COST 算法)

    改进版: 全历史数据 + 指数衰减 (半衰期=45天, 经688012验证对齐通达信)
      - 老筹码随时间指数衰减: decay = 0.5^(1/45)
      - 新成交量按三角分布叠加
      - 价格范围覆盖全历史高低点 + 当前价

    返回:
      chip, price_grid, avg_cost, COST(N), WINNER(P), concentration
    """
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    volume = df["volume"].values
    n = len(df)

    # 使用全部数据, 但只取有效天数
    if window > 0 and n > window:
        start = n - window
    else:
        start = 0
    close_w = close[start:]
    high_w = high[start:]
    low_w = low[start:]
    vol_w = volume[start:]
    w = len(close_w)

    # 价格范围: 覆盖全历史, 确保当前价格在范围内
    p_min = float(np.min(low_w))
    p_max = float(np.max(high_w))
    cur_price = float(close_w[-1])
    if cur_price > p_max: p_max = cur_price
    if cur_price < p_min: p_min = cur_price
    if p_max <= p_min:
        p_max = p_min + 0.01
    # 上下各扩展5%留边
    margin = (p_max - p_min) * 0.05
    price_min = p_min - margin
    price_max = p_max + margin

    bw = (price_max - price_min) / bins
    price_grid = np.array([price_min + (j + 0.5) * bw for j in range(bins)])
    chip = np.zeros(bins, dtype=float)

    # 指数衰减因子: 半衰期 decay_half 天
    decay = 0.5 ** (1.0 / decay_half)

    for i in range(w):
        if vol_w[i] <= 0:
            chip *= decay
            continue

        # 半衰期指数衰减
        chip *= decay

        # 当日筹码分布: 三角形, peak at close
        lo = max(0, int((low_w[i] - price_min) / bw))
        hi = min(bins - 1, int((high_w[i] - price_min) / bw) + 1)
        if hi <= lo:
            hi = lo + 1
        mid = int((close_w[i] - price_min) / bw)
        mid = max(lo, min(hi - 1, mid))

        for j in range(lo, hi):
            weight = 1.0 - 0.7 * abs(j - mid) / max(hi - lo, 1)
            chip[j] += vol_w[i] * max(0.0, weight)

    total = float(chip.sum())
    if total <= 0:
        return None

    # 平均成本
    avg_cost = float(np.average(price_grid, weights=chip))

    # 计算 COST(N) / WINNER(P)
    sorted_idx = np.argsort(price_grid)
    cum_chip = np.cumsum(chip[sorted_idx]) / total

    def cost_n(pct):
        """N% 获利盘对应的价格, 0<N<100"""
        idx = np.searchsorted(cum_chip, pct / 100.0)
        idx = min(idx, bins - 1)
        return float(price_grid[sorted_idx[idx]])

    def winner_n(price):
        """价格 <= price 的筹码占比, 0-100"""
        mask = price_grid <= price
        return float(chip[mask].sum() / total * 100)

    # 90% 成本集中度: (COST(95)-COST(5)) / COST(50)
    c95 = cost_n(95)
    c50 = cost_n(50)
    c5 = cost_n(5)
    concentration_90 = (c95 - c5) / c50 * 100 if c50 > 0 else 0

    return {
        "chip": chip,
        "price_grid": price_grid,
        "bw": bw,
        "avg_cost": avg_cost,
        "cost_5": c5,
        "cost_50": c50,
        "cost_95": c95,
        "cost_15": cost_n(15),
        "cost_85": cost_n(85),
        "concentration_90": concentration_90,
        "winner_close": winner_n(close_w[-1]),
        "close": float(close_w[-1]),
        "price_min": price_min,
        "price_max": price_max,
    }


def plot_chip(result, stock_code, stock_name=""):
    """绘制筹码分布图 (模仿通达信/同花顺样式)"""
    chip = result["chip"]
    price_grid = result["price_grid"]
    bw = result["bw"]
    close = result["close"]

    fig, ax = plt.subplots(1, 1, figsize=(8, 12))

    # 右侧: 价格轴
    ax.set_ylabel("价格 (元)")
    ax.set_xlabel("筹码占比")

    # 归一化筹码为百分比
    chip_pct = chip / chip.sum() * 100

    # 绘制筹码分布水平柱状图
    bar_height = bw * 0.9
    colors = np.where(price_grid < result["avg_cost"], "#14b143", "#ef232a")
    ax.barh(price_grid, chip_pct, height=bar_height, color=colors, alpha=0.7, edgecolor='none')

    # 标记平均成本线
    ax.axhline(y=result["avg_cost"], color='#f59e0b', linestyle='--', linewidth=1.5, label=f'平均成本 {result["avg_cost"]:.2f}')

    # 标记当前价格
    ax.axhline(y=close, color='#60a5fa', linestyle='-', linewidth=2, label=f'现价 {close:.2f}')

    # 标记 90% 成本区间
    c5, c95 = result["cost_5"], result["cost_95"]
    ax.axhspan(c5, c95, alpha=0.08, color='yellow', label=f'90%成本 [{c5:.2f}, {c95:.2f}]')

    # 标记 70% 成本区间
    c15, c85 = result["cost_15"], result["cost_85"]
    ax.axhspan(c15, c85, alpha=0.12, color='orange', label=f'70%成本 [{c15:.2f}, {c85:.2f}]')

    # 设置显示范围: 把峰值显示清楚
    y_margin = (result["price_max"] - result["price_min"]) * 0.1
    ax.set_ylim(result["price_min"] - y_margin, result["price_max"] + y_margin)

    title = f'{stock_code} {stock_name} 筹码分布'
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.legend(loc='upper right', fontsize=9)

    # 左上角信息框
    info_text = (
        f'平均成本: {result["avg_cost"]:.2f}\n'
        f'获利比例: {result["winner_close"]:.1f}%\n'
        f'90%成本: {c5:.2f} ~ {c95:.2f}\n'
        f'70%成本: {c15:.2f} ~ {c85:.2f}\n'
        f'90%集中度: {result["concentration_90"]:.1f}%\n'
        f'价格区间: {result["price_min"]:.2f} ~ {result["price_max"]:.2f}'
    )
    ax.text(0.98, 0.98, info_text, transform=ax.transAxes, fontsize=10,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))

    plt.tight_layout()
    out_path = f'E:/workspace/AIResearch/AIStock_Pro/backend/temp_lab/chip_{stock_code}.png'
    plt.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f'\n图表已保存: {out_path}')


async def main(stock_code="603773"):
    async with async_session() as db:
        res = await db.execute(
            select(MarketData)
            .where(MarketData.stock_code == stock_code)
            .order_by(MarketData.trade_date.asc()))
        rows = res.scalars().all()

    if not rows:
        print(f"无行情数据: {stock_code}")
        return

    df = pd.DataFrame([{
        "trade_date": r.trade_date,
        "open": float(r.open or 0), "high": float(r.high or 0),
        "low": float(r.low or 0), "close": float(r.close or 0),
        "volume": float(r.volume or 0),
    } for r in rows])

    print(f"{stock_code}: {len(df)} 天行情, {df.iloc[-1]['trade_date']} 最新")

    result = calc_chip_distribution(df, window=90)
    if not result:
        print("计算失败")
        return

    print(f"\n=== 筹码分布结果 ===")
    print(f"现价: {result['close']:.2f}")
    print(f"平均成本: {result['avg_cost']:.2f}")
    print(f"获利比例: {result['winner_close']:.1f}%")
    print(f"90%成本区间: {result['cost_5']:.2f} ~ {result['cost_95']:.2f}")
    print(f"70%成本区间: {result['cost_15']:.2f} ~ {result['cost_85']:.2f}")
    print(f"90%成本集中度: {result['concentration_90']:.1f}%")

    plot_chip(result, stock_code)


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "603773"
    asyncio.run(main(code))
