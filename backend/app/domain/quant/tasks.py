import asyncio
from app.framework.database.session import async_session
from app.domain.quant.engine.engine import QuantEngine
from app.domain.portfolio.services.ai_import import AIImportService
from app.framework.logger import logger
from app.framework.tasks.engine import task_manager

@task_manager.register(code="sync_market", name="行情数据同步", description="同步持仓股票的最新行情并重算技术指标")
async def sync_market_data_task(mode: str = "AUTO", exec_id: str = None, target_codes: list = None):
    """V5.1 行情同步任务 — 增量感知 + 节点追踪"""
    async with async_session() as db:
        engine = QuantEngine(db)
        if mode == "PRICE_ONLY":
            await engine.sync_prices_only(exec_id=exec_id)
        else:
            await engine.batch_sync_and_analyze(exec_id=exec_id, mode=mode, target_codes=target_codes)

@task_manager.register(code="calc_indicators", name="指标重算", description="计算全部量化指标 (含筹码/拥挤度)")
async def calculate_indicators_task(
    exec_id: str = None,
    target_codes: list = None,
    mode: str = "incremental",
    indicator_names: list = None,
):
    """V5.3 统一指标计算任务 — 支持 target_codes / mode / indicator_names 参数化
    mode: snapshot(快照) | incremental(增量) | historical(全量历史)
    target_codes=None → 全部持仓+自选股
    indicator_names=None → 全部16个指标
    """
    from app.framework.database.session import async_session
    from app.models.models import Position, WatchlistItem, MarketData
    from app.domain.quant.engine.indicator_runner import IndicatorRunner
    from sqlalchemy import select, func
    from typing import List as _List

    if target_codes:
        codes = target_codes
    else:
        async with async_session() as db:
            pos_res = await db.execute(select(Position.stock_code))
            wl_res = await db.execute(select(WatchlistItem.stock_code))
            codes = list(set([r[0] for r in pos_res.all()] + [r[0] for r in wl_res.all()]))

    if not codes:
        logger.warning("[CalcIndicators] No stocks to compute")
        if exec_id:
            await task_manager.update_progress(exec_id, 100, "无待计算股票")
        return

    import time as _time
    mode_label = {"snapshot": "快照", "incremental": "增量", "historical": "全量"}.get(mode, mode)
    ind_label = f"indicators={len(indicator_names)}" if indicator_names else "indicators=all"
    t0 = _time.time()
    logger.info(f"[CalcIndicators] START | stocks={len(codes)} mode={mode_label} {ind_label}")

    total = len(codes)
    success = 0
    errors = []

    for idx, code in enumerate(codes):
        await asyncio.sleep(0)
        t1 = _time.time()

        async with async_session() as db:
            has_data = await db.execute(
                select(func.count(MarketData.id)).where(MarketData.stock_code == code))
            if has_data.scalar() == 0:
                errors.append(f"{code}: no market data")
                logger.warning(f"[CalcIndicators] {code}: SKIP no market data")
                continue

        try:
            if mode == "historical":
                r = await IndicatorRunner.compute_historical(code, indicator_names)
                days = r.get("days_computed", 0)
            elif mode == "snapshot":
                r = await IndicatorRunner.compute_snapshot(code, indicator_names)
                days = r.get("computed", 0)
            else:
                r = await IndicatorRunner.compute_incremental(code, indicator_names)
                days = r.get("days_computed", 0)

            elapsed = _time.time() - t1
            if days > 0:
                success += 1
                logger.success(f"[CalcIndicators] {code}: OK {days}d {elapsed:.1f}s")
            else:
                errors.append(f"{code}: 0d computed")
                logger.warning(f"[CalcIndicators] {code}: 0d computed in {elapsed:.1f}s")
        except Exception as e:
            elapsed = _time.time() - t1
            err_msg = f"{code}: {type(e).__name__}({e})"
            errors.append(err_msg)
            logger.error(f"[CalcIndicators] {code}: FAIL {err_msg} ({elapsed:.1f}s)")

        if exec_id:
            await task_manager.update_progress(
                exec_id, int(((idx + 1) / total) * 100),
                f"{mode_label} {idx+1}/{total} | {code} | OK:{success} ERR:{len(errors)}")

    total_t = _time.time() - t0
    summary = f"{mode_label}完成 | OK:{success} ERR:{len(errors)}/{total} | {total_t:.0f}s"
    if success == 0 and errors:
        summary += f" | 首错: {errors[0]}"
    if exec_id:
        await task_manager.update_progress(exec_id, 100, summary)
    logger.info(f"[CalcIndicators] DONE | {summary}")


@task_manager.register(code="research_analyze", name="投研深度分析", description="产业链穿透+审计+定价+综合报告 (支持多模式)")
async def research_analyze_task(exec_id: str = None, industry: str = "", question: str = "",
                                  analysis_type: str = "supply_chain", codes_str: str = "",
                                  agent_id: str = "", mode_id: str = "", target: str = ""):
    """V5.8 投研异步任务 — 兼容旧 Pipeline + 新 agent/mode 系统"""
    import json as _json, os, time as _time

    # 新参数优先 (agent_id + mode_id + target) — 支持多步 Pipeline 串联
    if agent_id and mode_id:
        logger.info(f"[ResearchTask] Starting: agent={agent_id}, mode={mode_id}, target={target}")
        t0 = _time.time()
        if exec_id: await task_manager.update_progress(exec_id, 5, f"Step2: 正在搜索分析 {target or mode_id}")

        try:
            from app.domain.research.api.routes import ScanRequest, _do_scan
            result = await _do_scan(ScanRequest(agent_id=agent_id, mode_id=mode_id, target=target))
            step2_data = result.get("data", {})
            enter_step3 = step2_data.get("verdict", {}).get("enter_step3", False)
            run_id = result.get("run_id", "")
            step2_elapsed = _time.time() - t0

            if exec_id:
                await task_manager.update_progress(exec_id, 40,
                    f"Step2完成: {step2_data.get('verdict',{}).get('priority','?')}, enter_step3={enter_step3}, {step2_elapsed:.0f}s")

            # Step 3: 产业链拆解 (仅当 enter_step3=true 且非 auto_scan)
            if enter_step3 and mode_id in ("manual_industry", "stock_deep"):
                if exec_id: await task_manager.update_progress(exec_id, 45, "Step3: 产业链系统拆解...")
                logger.info(f"[ResearchTask] Chain Step2->Step3: {target or mode_id}")
                try:
                    from app.domain.research.agents.supply_chain_hacker import SupplyChainHacker
                    from app.framework.ai.providers.deepseek import DeepSeekProvider
                    from app.framework.pipeline.checkpoint import save_checkpoint, hash_input
                    from app.framework.pipeline.trace import TraceContext

                    hacker = SupplyChainHacker(provider=DeepSeekProvider())
                    step2_guidance = step2_data.get("_step3_guidance", {})
                    ctx = {"industry": target or mode_id, "step2_guidance": step2_guidance}
                    trace = TraceContext(run_id)
                    step3_result = await hacker.analyze(ctx, trace=trace)

                    ih = hash_input({"industry": target or mode_id, "step2_phase": step2_guidance.get("cycle_phase",""),
                                     "date": _time.strftime("%Y%m%d"), "agent_version": "supply_chain_hacker_v5.8"})
                    save_checkpoint("step3_sc_hacker", run_id, ih, step3_result, {"elapsed": 0})
                    trace.write("step3_sc_hacker")

                    if exec_id: await task_manager.update_progress(exec_id, 98, "Step3完成, 落盘中...")
                    logger.info(f"[ResearchTask] Step3 DONE: {len(step3_result.get('supply_chain_map',[]))} layers")
                except Exception as e:
                    logger.warning(f"[ResearchTask] Step3 failed (non-fatal): {e}")
                    if exec_id: await task_manager.update_progress(exec_id, 50, f"Step3失败(不阻塞): {e}")

            total_elapsed = _time.time() - t0
            summary = f"完成: {target or mode_id}"
            if enter_step3 and mode_id in ("manual_industry", "stock_deep"):
                summary += " (Step2+Step3串联)"
            if exec_id: await task_manager.update_progress(exec_id, 100, summary + f", {total_elapsed:.0f}s")
            logger.info(f"[ResearchTask] DONE: {summary}, {total_elapsed:.0f}s")
        except Exception as e:
            logger.error(f"[ResearchTask] Failed: {e}")
            if exec_id: await task_manager.update_progress(exec_id, 100, f"失败: {e}")
            raise
        return

    # 旧参数兼容
    industry = industry or question
    if not industry and not codes_str:
        raise RuntimeError("必须指定 industry / question / codes_str 参数")
    logger.info(f"[ResearchTask] Starting: analysis_type={analysis_type}, industry={industry or codes_str}")
    t0 = _time.time()

    from app.framework.ai.providers.deepseek import DeepSeekProvider
    from app.domain.research.pipelines import PIPELINES
    provider = DeepSeekProvider()

    if exec_id:
        await task_manager.update_progress(exec_id, 5, f"Pipeline: {analysis_type}")

    pipeline = PIPELINES.get(analysis_type)
    if not pipeline:
        raise RuntimeError(f"Unknown analysis_type: {analysis_type}")

    try:
        result = await pipeline["func"](
            industry=industry, provider=provider,
            params={"codes_str": codes_str, "skip_phase1": False})
        if exec_id:
            await task_manager.update_progress(exec_id, 90, "分析完成, 落盘中...")

        from app.domain.research.api.routes import save_report
        save_report(pipeline["label"], industry or codes_str, result)

        elapsed = _time.time() - t0
        n_stocks = len(result.get("top_picks", []))
        summary = f"投研完成[{analysis_type}]: {industry or codes_str}, {n_stocks}标的, {elapsed:.0f}s"
        if exec_id:
            await task_manager.update_progress(exec_id, 100, summary)
        logger.info(f"[ResearchTask] DONE: {summary}")
    except Exception as e:
        logger.error(f"[ResearchTask] Pipeline failed: {e}")
        if exec_id:
            await task_manager.update_progress(exec_id, 100, f"失败: {e}")
        raise


@task_manager.register(code="ai_recognize", name="AI 截图识别", description="调用 AI 模型识别持仓/交易截图")
async def ai_recognize_image_task(exec_id: str = None, image_base64: str = "",
                                   recognize_type: str = "position"):
    """V5.2 AI 识别异步任务 — 豆包 → DeepSeek → Gemini 链式调用"""
    logger.info(f"[🚀] AI recognition task started (type={recognize_type}, image={len(image_base64)//1024}KB)")

    if exec_id:
        await task_manager.update_progress(exec_id, 5, "正在压缩图片并调用 AI...")

    if recognize_type == "trade":
        result = await AIImportService.recognize_trade_image(image_base64)
    else:
        result = await AIImportService.recognize_stock_image(image_base64)

    if exec_id:
        if result:
            await task_manager.update_progress(exec_id, 100, f"识别完成: {len(result)} 条记录")
            logger.info(f"[✅] AI recognition complete: {len(result)} records")
        else:
            logger.error("[❌] AI recognition returned empty")
            raise RuntimeError("所有 AI 引擎均未识别到有效数据，请检查 API Key 配置或截图清晰度")
