# 明日计划 — 2026-05-25

## 上午: Step 3 设计

1. 按 Step 2 的标准格式重写 03_Step3_SupplyChain.md
   - I/O contract: 输入来自 Step 2 的 cycle_position/prosperity/propagation
   - 输出 schema: supply_chain_map 增强 (profit_pool_share / pricing_power / supply_rigidity / rigidity_structure / value_capture / scarcity_indicators)
   - 行为规范: 3 轮搜索策略 + LLM prompt 结构
   - 上下游接口: 消费 Step 2 → 提供给 Step 4/6/8

2. 引入 6 个强制问题到 Step 3 prompt (从 GPT 评审吸收):
   谁被抽血？谁被忽略？谁不能扩产？谁会意外涨价？谁是最后一个瓶颈？利润会转移给谁？

3. 术语表注入: 编写 step3_glossary(), 自动挂载 cycle_phase + prosperity_type 定义

## 下午: Step 3 实现

4. 重写 supply_chain_hacker.py 的 _hack_supply_chain prompt
5. 运行 Step 3 测试: "半导体设备国产替代" (Step 2 选出的 top industry)
6. 验证输出结构符合设计，每个环节包含全部新增字段

## 目录清理 (已完成)

- 删除 temp_lab/ 过期脚本 10 个
- 删除 backend/temp_lab/ 过期测试脚本 30+ 个
- 保留: run_step.py, test_step2_auto.py, SOFC/CPU 缓存数据, chip 分布图

## 遗留待办 (不紧急)

- IDEA-003: US_FED_RATE 数据源修复
- IDEA-004: CPI/ISM PMI 数据接入
- Server 重启加载 _parse_biz_date 修复
- scan API 端点适配新参数 (mode/target_industry)
