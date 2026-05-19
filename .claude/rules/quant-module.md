# 量化模块开发范式

## 指标库 — 每算子一文件, 装饰器自注册

### 目录结构
```
indicators/
├── base.py          # BaseIndicator + @register 装饰器 + _registry
├── trend/           # 趋势类: ma.py, macd.py, kdj.py
├── momentum/        # 动量类: rsi.py, atr.py, cci.py
├── volatility/      # 波动类: bollinger.py, bollinger_width.py
├── volume/          # 量能类: obv.py, volume_ma.py, vwap.py
├── chip/            # 筹码: concentration.py, peak_price.py, pattern.py
└── crowding/        # 拥挤度: turnover_ratio.py, sharpe_60d.py
```

### 新增指标步骤
1. 在对应分类目录下新建 `<name>.py`
2. 继承 `BaseIndicator`, 设置类属性 (name/category/params/output/requires)
3. 实现 `compute(cls, df: pd.DataFrame) -> dict` 类方法
4. 加 `@register` 装饰器
5. **无需手动更新注册表** — `__init__.py` 自动发现

### 代码模板
```python
# indicators/trend/macd.py
from ..base import BaseIndicator, register

@register
class MACDIndicator(BaseIndicator):
    name = "macd"
    category = "trend"
    params = {"fast": 12, "slow": 26, "signal": 9}
    output = ["macd", "macd_signal", "macd_hist"]
    requires = ["close"]

    @classmethod
    def compute(cls, df):
        ema_fast = df["close"].ewm(span=cls.params["fast"]).mean()
        ema_slow = df["close"].ewm(span=cls.params["slow"]).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=cls.params["signal"]).mean()
        return {"macd": macd, "macd_signal": signal, "macd_hist": macd - signal}
```

### 约束
- ✅ 纯函数: 输入 DataFrame, 输出 dict of Series
- ✅ 向量化: pandas rolling/ewm/diff/shift, 禁止逐行循环
- ✅ 类属性即元信息, 不需要额外配置
- ❌ 算子内禁止 I/O (DB/网络/文件)
- ❌ 算子不持有状态

## 策略库 — 每策略一文件, 装饰器自注册

### 目录结构
```
strategies/
├── base.py              # TimingStrategy + SignalResult + @register_strategy
├── traditional/         # 传统策略 (每文件一个)
│   ├── macd_cross.py
│   ├── rsi_oversold.py
│   └── ...
└── ai_chain/            # AI逻辑链策略 (独立架构)
    ├── engine.py         # 执行引擎
    ├── prompt_builder.py # LLM prompt构建
    ├── parser.py         # 输出解析
    └── definitions/      # 策略定义 (YAML, 可热编辑)
        └── *.yaml
```

### 传统策略代码模板
```python
# strategies/traditional/macd_cross.py
from ..base import TimingStrategy, SignalResult, register_strategy

@register_strategy
class MACDCrossStrategy(TimingStrategy):
    name = "macd_cross"
    description = "MACD金叉买入, 死叉卖出"
    required_indicators = ["macd", "volume_ma"]

    async def analyze(self, stock_code: str) -> SignalResult:
        ind = await self.load_indicators(stock_code)
        # ... 策略逻辑 ...
        return SignalResult(stock_code=stock_code, signal="BUY",
            confidence=0.75, reasoning="MACD零轴上金叉", ...)
```

### AI链策略定义模板 (YAML)
```yaml
# definitions/aggressive_short.yaml
name: aggressive_short
persona: "A股激进短线交易员"
temperature: 0.3
required_indicators: [macd, rsi, kdj, volume_ma]
logic_chain: |
  基于指标数据给出交易判断:
  1. MACD零轴上方金叉 + 成交量放大 → BUY (0.85)
  2. MACD死叉或RSI>80 → SELL
  输出JSON: {"signal":"BUY/SELL/HOLD","confidence":0.8,"reasoning":"..."}
```

### AI链策略与传统的架构差异
- 传统策略: Python代码 → 编译时生效, 修改需重启
- AI链策略: YAML文本 → 运行时热加载, API编辑即刻生效
- AI链的执行引擎是共享的, 策略定义只是数据

### 约束
- ✅ 策略声明 required_indicators, 引擎负责加载
- ✅ SignalResult 包含完整快照
- ❌ 策略不做数据同步/指标计算
- ❌ 策略间不可互相依赖
- ❌ AI链策略 logic_chain 不接受用户直接输入(防注入), 数据走JSON序列化

## 决策中心

### 加权投票规则
- 传统策略权重 = 1.0, AI链策略权重 = 1.2
- BUY_score > SELL_score * 1.5 → BUY, 反之 SELL, 否则 HOLD
- 不设一票否决, 筹码/拥挤异常仅标记 risk flag

### 执行模式
- 手动: POST /quant/decide/{stock_code}
- 批量: POST /quant/decide/portfolio
- 定时: 交易日 15:30 APScheduler
- 结果全部持久化, 支持历史查询/清理/重跑

### 检查清单 (新增策略时)
- [ ] 策略文件放在正确的目录 (traditional/ 或 ai_chain/definitions/)
- [ ] 继承 TimingStrategy, 加 @register_strategy
- [ ] required_indicators 准确声明
- [ ] SignalResult 数据完整
- [ ] 传统策略: 代码逻辑正确
- [ ] AI链策略: YAML格式正确, logic_chain 清晰, temperature 合理
