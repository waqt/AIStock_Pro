"""监控执行引擎 — 定时检查活跃监控计划 → 搜索 → LLM 评估 → 生成信号事件"""
import json, uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

from app.framework.logger import logger
from app.framework.ai.providers.deepseek import DeepSeekProvider
from app.domain.research.services.data_loader import ResearchDataLoader
from app.domain.observation.monitor.store import MonitorStore


EVALUATE_PROMPT = """你是一位投资研究监控分析师。你的任务是根据一个监控计划的配置和最新的搜索内容，判断该监控计划是否被触发。

## 监控计划
名称: {plan_name}
描述: {plan_description}

### 触发判断指令
{trigger_instruction}

### 搜索配置
{search_config}

### 最新搜索结果
{search_results}

### 历史触发记录
{history}

## 分析要求

1. 仔细阅读搜索结果, 判断是否有信息与监控目标相关
2. 根据 trigger_instruction 中的标准, 判断是否达到触发条件
3. 区分信号强度:
   - strong: 官方公告、财报数据、监管文件等确凿证据
   - medium: 可靠媒体报道、分析师报告、产业链调研
   - weak: 传闻、猜测、未证实的信息
4. 如果触发, 清晰说明理由和证据

## 输出格式

返回 JSON:
```json
{{
  "is_triggered": true/false,
  "confidence": "high/medium/low",
  "title": "信号标题, 简短概括触发事件",
  "description": "详细说明触发理由和判断依据, 引用具体证据",
  "evidence": [
    {{
      "url": "来源URL",
      "snippet": "关键内容摘要",
      "source": "brave/financial/other",
      "relevance": "high/medium/low"
    }}
  ],
  "reasoning": "一步步推理过程"
}}
```

只返回 JSON, 不要其他说明。"""


class MonitorEngine:
    """监控执行引擎"""

    def __init__(self):
        self.store = MonitorStore()
        self.provider = DeepSeekProvider()
        self.data_loader = ResearchDataLoader()

    async def run_once(self) -> Dict[str, int]:
        """执行一次全面检查: 遍历所有到期的 active 计划

        Returns:
            {"checked": N, "triggered": M, "errors": K}
        """
        plans = self.store.get_due_plans()
        if not plans:
            logger.debug(f"[MonitorEngine] No due plans to check")
            return {"checked": 0, "triggered": 0, "errors": 0}

        logger.info(f"[MonitorEngine] Checking {len(plans)} due plans")

        checked = 0
        triggered = 0
        errors = 0

        for plan in plans:
            try:
                result = await self._check_plan(plan)
                checked += 1
                if result:
                    triggered += 1
            except Exception as e:
                logger.error(f"[MonitorEngine] Plan {plan['id']}: {e}")
                errors += 1

        logger.info(f"[MonitorEngine] Done: {checked} checked, {triggered} triggered, {errors} errors")
        return {"checked": checked, "triggered": triggered, "errors": errors}

    async def check_plan(self, plan_id: str) -> Optional[dict]:
        """检查单个监控计划 (手动触发)"""
        plan = self.store.get_plan(plan_id)
        if not plan:
            logger.warning(f"[MonitorEngine] Plan not found: {plan_id}")
            return None
        return await self._check_plan(plan)

    async def _check_plan(self, plan: dict) -> Optional[dict]:
        """执行单个计划的检查

        Returns:
            如果触发, 返回 signal_event dict; 否则 None
        """
        plan_id = plan['id']
        plan_name = plan.get('name', '')

        # 1. 执行搜索
        search_config = self._safe_json(plan.get('search_config', '[]'))
        if not search_config:
            logger.debug(f"[MonitorEngine] {plan_id}: no search config, skipping")
            self.store.update_plan_status(plan_id, 'active', last_check_at=datetime.now().isoformat())
            return None

        all_results = []
        for sc in search_config:
            engine = sc.get('engine', 'brave')
            query = sc.get('query', '')
            if not query:
                continue
            try:
                if engine == 'brave':
                    results = await self._search_web(query)
                elif engine == 'financial':
                    results = await self._search_financial(sc)
                else:
                    results = []
                all_results.append({"query": query, "engine": engine, "results": results})
            except Exception as e:
                logger.warning(f"[MonitorEngine] {plan_id}: search '{query}' failed: {e}")
                all_results.append({"query": query, "engine": engine, "results": [], "error": str(e)})

        now = datetime.now().isoformat()

        # 2. 检查冷却期
        last_triggered = plan.get('last_triggered_at')
        cooldown = plan.get('cooldown_days', 30)
        if last_triggered:
            from dateutil.parser import parse as dt_parse
            try:
                last = dt_parse(last_triggered)
                days_since = (datetime.now() - last).days
                if days_since < cooldown:
                    logger.debug(f"[MonitorEngine] {plan_id}: cooldown ({days_since}/{cooldown}d), skip LLM eval")
                    self.store.update_plan_status(
                        plan_id, 'active',
                        last_check_at=now,
                        total_checks=plan.get('total_checks', 0) + 1,
                    )
                    return None
            except Exception:
                pass

        # 3. LLM 评估搜索结果
        has_content = any(r.get('results') for r in all_results)
        if not has_content:
            self.store.update_plan_status(
                plan_id, 'active',
                last_check_at=now,
                total_checks=plan.get('total_checks', 0) + 1,
            )
            logger.debug(f"[MonitorEngine] {plan_id}: no search results, skip LLM eval")
            return None

        # 历史触发记录
        history = self.store.list_signals(plan_id=plan_id, limit=5)

        prompt = EVALUATE_PROMPT.format(
            plan_name=plan_name,
            plan_description=plan.get('description', ''),
            trigger_instruction=plan.get('trigger_instruction', '请根据搜索结果判断'),
            search_config=json.dumps(search_config, ensure_ascii=False, indent=2),
            search_results=json.dumps(all_results, ensure_ascii=False, indent=2, default=str),
            history=json.dumps([{
                "title": s.get('title'),
                "triggered_at": s.get('triggered_at'),
                "signal_direction": s.get('signal_direction'),
                "confidence": s.get('confidence'),
            } for s in history], ensure_ascii=False, indent=2),
        )

        try:
            response = await self.provider.chat_flash(prompt)
            verdict = self._parse_eval_response(response)
        except Exception as e:
            logger.warning(f"[MonitorEngine] {plan_id}: LLM eval failed: {e}")
            self.store.update_plan_status(
                plan_id, 'active',
                last_check_at=now,
                total_checks=plan.get('total_checks', 0) + 1,
            )
            return None

        # 4. 更新状态
        updates = {
            'last_check_at': now,
            'total_checks': plan.get('total_checks', 0) + 1,
        }

        if verdict and verdict.get('is_triggered'):
            # 创建信号事件
            signal = {
                'plan_id': plan_id,
                'plan_name': plan_name,
                'triggered_at': now,
                'signal_direction': plan.get('signal_direction', 'neutral'),
                'signal_strength': verdict.get('signal_strength', plan.get('signal_strength', 'medium')),
                'confidence': verdict.get('confidence', 'medium'),
                'title': verdict.get('title', plan_name),
                'description': verdict.get('description', ''),
                'evidence': json.dumps(verdict.get('evidence', []), ensure_ascii=False),
                'related_stock_code': plan.get('target_stock_code'),
                'related_stock_name': plan.get('target_stock_name'),
                'target_industry': plan.get('target_industry'),
                'status': 'pending_review',
            }
            self.store.save_signal(signal)

            updates['last_triggered_at'] = now
            logger.info(f"[MonitorEngine] Triggered: {plan_id} → {verdict.get('title', '')}")

            # 行业级计划: 级联到个股
            cascade = self._safe_json(plan.get('cascade_to_stocks', '[]'))
            if cascade and plan.get('level') == 'industry':
                for stock_code in cascade:
                    cascade_signal = dict(signal)
                    cascade_signal['id'] = str(uuid.uuid4())
                    cascade_signal['related_stock_code'] = stock_code
                    cascade_signal['title'] = f"{verdict.get('title', '')} → {stock_code}"
                    cascade_signal['description'] = f"行业级监控触发, 影响个股 {stock_code}\n\n{verdict.get('description', '')}"
                    self.store.save_signal(cascade_signal)
                    logger.info(f"[MonitorEngine] Cascade: {plan_id} → stock {stock_code}")

        self.store.update_plan_status(plan_id, 'active', **updates)
        return verdict

    async def _search_web(self, query: str, num: int = 10) -> List[dict]:
        """执行 Web 搜索"""
        try:
            results = await self.data_loader.search_web(query, num=num)
            return results if isinstance(results, list) else []
        except Exception as e:
            logger.warning(f"[MonitorEngine] Web search failed: {query[:50]}... | {e}")
            return []

    async def _search_financial(self, config: dict) -> List[dict]:
        """查询财务指标

        financial 引擎: {"field":"revenue_yoy", "threshold":0.3, "direction":"above", "stock_code":"688012"}
        """
        stock_code = config.get('stock_code')
        field = config.get('field')
        if not stock_code or not field:
            return []
        try:
            from app.domain.quant.engine.financial_query_service import FinancialQueryService
            svc = FinancialQueryService()
            data = await svc.query(stock_code, indicators=[field])
            return [{
                "url": "",
                "snippet": f"{stock_code} {field}={data.get(field, 'N/A')}",
                "source": "financial",
                "relevance": "high",
            }]
        except Exception as e:
            logger.warning(f"[MonitorEngine] Financial query failed: {stock_code}/{field} | {e}")
            return []

    @staticmethod
    def _safe_json(val) -> list:
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except (json.JSONDecodeError, TypeError):
                return []
        return []

    @staticmethod
    def _parse_eval_response(response: str) -> Optional[dict]:
        """解析 LLM 评估结果"""
        text = response.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        try:
            data = json.loads(text)
            return data
        except json.JSONDecodeError:
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end + 1])
                except json.JSONDecodeError:
                    pass
            return None
