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

class StockIndicator(Base):
    """量化指标与分析结论"""
    __tablename__ = "stock_indicators"
    id = Column(Integer, primary_key=True, index=True)
    stock_code = Column(String(20), index=True)
    indicator_type = Column(String(50)) # e.g., 'HYBRID_LOGIC'
    data_json = Column(JSON) # 存储 MA, RSI, MACD 等数值快照
    logic_chain = Column(JSON) # 存储 AI 推演过程
    analysis_date = Column(Date, index=True)

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
    """汇率与宏观指数 — HKD_CNY, USD_CNY, USD_IDX, XAU, XAG, BRENT"""
    __tablename__ = "exchange_rates"
    code = Column(String(20), primary_key=True)  # HKD_CNY, USD_CNY, USD_IDX, XAU, XAG, BRENT
    name = Column(String(50), nullable=True, comment="显示名称")
    rate = Column(Float, nullable=False, comment="最新价")
    change_pct = Column(Float, nullable=True, comment="涨跌幅(%)")
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


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
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class SystemSetting(Base):
    """系统全局配置"""
    __tablename__ = "system_settings"
    key = Column(String(50), primary_key=True)
    value = Column(JSON)
    description = Column(String(255))
