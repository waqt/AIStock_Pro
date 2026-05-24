from sqlalchemy import Column, Integer, String, Float, DateTime, Date, Text, JSON, ForeignKey, Boolean, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
from app.framework.database.session import Base

class Position(Base):
    """持仓数据表"""
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(20), unique=True, index=True)
    stock_name = Column(String(50))
    volume = Column(Integer, default=0)
    avg_cost = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    market_value = Column(Float, default=0.0)
    profit_loss = Column(Float, default=0.0)
    profit_loss_ratio = Column(Float, default=0.0)
    first_buy_date = Column(Date, nullable=True, comment="首次买入日期")
    updated_at = Column(DateTime, default=datetime.now)

class MarketData(Base):
    """原始行情主表 - 增量同步的核心"""
    __tablename__ = "market_data"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    stock_code = Column(String(20), index=True)
    trade_date = Column(Date, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)
    amount = Column(Float)
    change_pct = Column(Float, nullable=True, comment="涨跌幅(%)")

    __table_args__ = (
        UniqueConstraint('stock_code', 'trade_date', name='uq_market_data_code_date'),
    )

class TaskDefinition(Base):
    """任务定义表 (Registry) - 记录系统拥有的任务能力"""
    __tablename__ = "task_definitions"
    code = Column(String(50), primary_key=True) # 唯一标识，如 sync_data
    name = Column(String(100), nullable=False)
    description = Column(Text)
    cron_expr = Column(String(50), nullable=True) # 定时计划
    is_enabled = Column(Boolean, default=True)
    module_path = Column(String(255)) # 映射的函数路径
    created_at = Column(DateTime, default=datetime.now)

class TaskExecution(Base):
    """任务执行流水 (History) - 记录任务的每一次运行情况"""
    __tablename__ = "task_executions"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_code = Column(String(50), index=True)
    params = Column(JSON, nullable=True) # 调起参数快照
    status = Column(String(20), default="PENDING") # PENDING, RUNNING, STOPPING, SUCCESS, FAILED, CANCELLED
    progress = Column(Integer, default=0)
    pid = Column(Integer, nullable=True)
    result_msg = Column(Text, nullable=True)
    start_time = Column(DateTime, default=datetime.now)
    end_time = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class TradeHistory(Base):
    """交易审计流水"""
    __tablename__ = "trade_history"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    stock_code = Column(String(20), index=True)
    action = Column(String(10)) # BUY, SELL
    price = Column(Float)
    volume = Column(Integer)
    amount = Column(Float, default=0.0, comment="成交金额")
    commission = Column(Float, default=0.0, comment="手续费")
    stamp_tax = Column(Float, default=0.0, comment="印花税")
    trade_date = Column(DateTime, default=datetime.now)
    strategy_id = Column(String(50)) # 记录是由哪个策略触发的
    notes = Column(Text, nullable=True, comment="备注")

class ExchangeRate(Base):
    """汇率与宏观指数 — HKD_CNY, USD_CNY, USD_IDX, XAU, XAG, BRENT, US10YT, US_FED_RATE..."""
    __tablename__ = "exchange_rates"
    code = Column(String(20), primary_key=True)  # 指标代码
    name = Column(String(50), nullable=True, comment="显示名称")
    rate = Column(Float, nullable=False, comment="最新价")
    change_pct = Column(Float, nullable=True, comment="涨跌幅(%)")
    biz_date = Column(Date, nullable=True, comment="数据业务日期")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class MacroHistory(Base):
    """宏观指标历史序列 — 用于趋势图"""
    __tablename__ = "macro_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(30), index=True, comment="指标代码")
    obs_date = Column(Date, comment="观测日期")
    value = Column(Float, comment="指标值")
    created_at = Column(DateTime, default=datetime.now)


class ReportRegistry(Base):
    """报告注册表 — 索引所有 JSON 报告文件的元数据, 供 workflow 检索"""
    __tablename__ = "report_registry"
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_type = Column(String(30), nullable=False, comment="macro/supply_chain/market_scan/capex_scan")
    report_id = Column(String(100), nullable=False, unique=True, comment="文件名(不含.json)")
    title = Column(String(200), nullable=True, comment="可读标题")
    industry = Column(String(80), nullable=True, comment="行业(macro为NULL)")
    agent = Column(String(80), nullable=True, comment="生成方")
    filepath = Column(String(500), nullable=True, comment="相对路径")
    generated_at = Column(DateTime, nullable=False, comment="报告生成时间")
    valid_until = Column(DateTime, nullable=True, comment="有效期(NULL=永不过期)")
    status = Column(String(20), default="valid", comment="valid/expired/regenerated")
    summary = Column(String(200), nullable=True, comment="摘要")
    created_at = Column(DateTime, default=datetime.now)


class StockInfo(Base):
    """股票基础信息 — A股+港股全量代码名称"""
    __tablename__ = "stock_info"
    stock_code = Column(String(10), primary_key=True)
    stock_name = Column(String(50), nullable=False)
    exchange = Column(String(5), comment="SH/SZ/HK")
    industry = Column(String(50), nullable=True)
    list_date = Column(Date, nullable=True)
    pe_ttm = Column(Float, nullable=True, comment="市盈率(TTM)")
    pb = Column(Float, nullable=True, comment="市净率")
    mcap_yi = Column(Float, nullable=True, comment="总市值(亿)")
    float_mcap_yi = Column(Float, nullable=True, comment="流通市值(亿)")
    turnover_pct = Column(Float, nullable=True, comment="换手率(%)")
    roe = Column(Float, nullable=True, comment="净资产收益率(%)")
    dividend_yield = Column(Float, nullable=True, comment="股息率(%)")
    eps_growth_3y = Column(Float, nullable=True, comment="近3年盈利复合增速(%)")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class FinancialStatement(Base):
    """季度财务报告 — 三大表核心字段"""
    __tablename__ = "financial_statements"
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), nullable=False, index=True)
    report_date = Column(Date, nullable=False)
    report_type = Column(String(5), default="Q")
    revenue = Column(Float, default=0.0)
    parent_profit = Column(Float, default=0.0)
    operate_cost = Column(Float, default=0.0)
    sale_expense = Column(Float, default=0.0)
    manage_expense = Column(Float, default=0.0)
    rd_expense = Column(Float, default=0.0)
    op_cashflow = Column(Float, default=0.0)
    inventory = Column(Float, default=0.0)
    contract_liability = Column(Float, default=0.0)
    accounts_receivable = Column(Float, default=0.0)
    total_assets = Column(Float, default=0.0)
    current_assets = Column(Float, default=0.0)
    fixed_assets = Column(Float, default=0.0)
    total_liabilities = Column(Float, default=0.0)
    total_equity = Column(Float, default=0.0)
    announce_date = Column(Date, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    __table_args__ = (UniqueConstraint('stock_code', 'report_date', name='uq_fin_stmt'),)


class WatchlistItem(Base):
    """自选股 — 用户关注的股票 (与持仓独立)"""
    __tablename__ = "watchlist"
    stock_code = Column(String(20), primary_key=True)
    stock_name = Column(String(50), default="")
    group_tag = Column(String(30), default="默认")  # 分组标签
    is_held = Column(Boolean, default=False)  # 是否已持仓
    sort_order = Column(Integer, default=0)
    notes = Column(Text, nullable=True, comment="备注")
    target_price_low = Column(Float, nullable=True, comment="目标价下限")
    target_price_high = Column(Float, nullable=True, comment="目标价上限")
    added_at = Column(DateTime, default=datetime.now)


class PortfolioSnapshot(Base):
    """持仓每日切片 — 历史持仓状态记录, 用于后续分析"""
    __tablename__ = "portfolio_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    snap_date = Column(Date, index=True, comment="切片日期")
    stock_code = Column(String(20), index=True)
    stock_name = Column(String(50))
    volume = Column(Integer, default=0)
    avg_cost = Column(Float, default=0.0)
    current_price = Column(Float, default=0.0)
    market_value = Column(Float, default=0.0)
    profit_loss = Column(Float, default=0.0)
    profit_loss_ratio = Column(Float, default=0.0)
    pe_ttm = Column(Float, nullable=True)
    pb = Column(Float, nullable=True)
    mcap_yi = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.now)


class StrategySignal(Base):
    """策略信号持久化 — 每策略每次执行的结果"""
    __tablename__ = "strategy_signals"
    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(20), index=True)
    strategy_name = Column(String(50))
    strategy_category = Column(String(20), default="traditional")  # traditional | ai_chain
    signal = Column(String(10))  # BUY / SELL / HOLD
    confidence = Column(Float, default=0.5)
    reasoning = Column(Text, default="")
    indicators_snapshot = Column(JSON, default=dict)
    decision_date = Column(Date, index=True)
    generated_at = Column(DateTime, default=datetime.now)


class SystemSetting(Base):
    """系统全局配置"""
    __tablename__ = "system_settings"
    key = Column(String(50), primary_key=True)
    value = Column(JSON)
    description = Column(String(255))
