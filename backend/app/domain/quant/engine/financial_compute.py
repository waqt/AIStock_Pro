"""
财务指标批量计算核心逻辑 — 单一来源, 供 API 和 Task 共享调用
消除 indicators.py 和 tasks.py 中的重复代码
"""
from typing import List, Optional
from app.framework.logger import logger

# ETF 代码前缀 (6位A股中排除 ETF 和 港股)
# TODO V6: 使用 stock_info 表的 asset_type 字段替代硬编码前缀
ETF_CODE_PREFIXES = ('159', '510', '512', '513', '560', '588')


async def compute_financial_for_codes(
    codes: List[str],
    mode: str = "local",
    progress_callback=None,
) -> dict:
    """
    核心计算函数: 对指定股票列表批量计算全部财务指标并落库
    
    参数:
        codes: 股票代码列表 (已过滤 ETF/港股)
        mode: "local" (仅DB) / "auto" (DB→akshare→web)
        progress_callback: async fn(pct: int, msg: str) 进度回调 (可选)
    返回:
        {"computed": int, "total": int, "results": [...]}
    """
    from app.domain.quant.engine.indicator_store import store_financial_indicator
    from app.domain.research.services.financial_data_loader import load_financials
    from app.domain.quant.indicators.fundamental import FINANCIAL_REGISTRY

    # 全部注册指标统一遍历 (ROIC/ROIIC 内部自行处理研发资本化调整)
    fin_indicators = list(FINANCIAL_REGISTRY.items())

    results = []
    db_count, web_count = 0, 0

    for idx, code in enumerate(codes):
        try:
            fin = await load_financials(code, periods=20, mode=mode)
            data_source = fin.get("source", "db")
            quarters = fin.get("quarters", [])

            if len(quarters) < 4:
                results.append({"code": code, "status": "skipped", "reason": f"仅{len(quarters)}Q数据"})
                continue

            # quarters 已是 newest-first (data_loader ORDER BY report_date DESC)
            stored_count = 0

            for i in range(len(quarters) - 3):
                rpt_date = quarters[i].get("report_date", "")[:10]
                record = {"source": data_source}

                # ── 全部注册指标统一遍历 (ROIC/ROIIC 自行处理窗口长度判定+RD调整) ──
                full_window = quarters[i:]
                for name, cls in fin_indicators:
                    try:
                        result = cls.compute(full_window)
                        record.update(result)
                    except Exception as e:
                        logger.warning(f"[FinCompute] {code}: {cls.__name__}.compute failed: {e}")

                if store_financial_indicator(code, rpt_date, record):
                    stored_count += 1

            if data_source == "db":
                db_count += 1
            else:
                web_count += 1

            # 取最新 ROIC 作为汇总展示
            latest_record = {}
            for name, cls in fin_indicators:
                if name == "roic":
                    try:
                        latest_record = cls.compute(quarters[:4])
                    except Exception:
                        pass

            results.append({
                "code": code, "status": "ok" if stored_count > 0 else "store_failed",
                "periods": stored_count,
                "latest_date": quarters[0].get("report_date", "")[:10],
                "data_source": data_source,
                "roic_pct": latest_record.get("roic_pct"),
            })
        except Exception as e:
            results.append({"code": code, "status": "error", "reason": str(e)[:100]})
            logger.warning(f"[FinCompute] {code} failed: {e}")

        # 进度回调
        if progress_callback:
            await progress_callback(
                int((idx + 1) / len(codes) * 100),
                f"{idx+1}/{len(codes)}"
            )

    ok_count = sum(1 for r in results if r["status"] == "ok")
    logger.info(f"[FinCompute] Done: {ok_count}/{len(codes)} (DB={db_count}, Web={web_count})")
    return {"computed": ok_count, "total": len(codes), "results": results}


def filter_a_share_codes(codes: List[str]) -> List[str]:
    """过滤: 只保留 A 股 6 位代码, 排除 ETF / 港股"""
    return [c for c in codes if len(str(c)) == 6
            and not str(c).startswith(ETF_CODE_PREFIXES)]
