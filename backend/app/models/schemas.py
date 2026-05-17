from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, date

class PositionResponse(BaseModel):
    id: int
    stock_code: str
    stock_name: Optional[str]
    volume: float
    avg_cost: float
    current_price: Optional[float] = 0.0
    market_value: float
    profit_loss: float
    profit_loss_ratio: Optional[float] = None
    updated_at: Optional[datetime]
    
    model_config = ConfigDict(from_attributes=True)

class TaskExecutionResponse(BaseModel):
    id: str
    task_code: str
    params: Optional[Dict[str, Any]] = None
    status: str
    progress: int
    pid: Optional[int] = None
    result_msg: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class TaskDefinitionResponse(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    cron_expr: Optional[str] = None
    is_enabled: bool
    module_path: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

# ── Import Schemas (V5.2) ─────────────────

class RecognizedPositionItem(BaseModel):
    stock_code: str
    stock_name: str = ""
    shares: int = 0
    cost_price: float = 0.0
    current_price: float = 0.0

class RecognizedTradeItem(BaseModel):
    stock_code: str
    stock_name: str = ""
    trade_type: str = "BUY"
    shares: int = 0
    price: float = 0.0
    trade_date: Optional[str] = None

class ImagePayload(BaseModel):
    image: str

class TextParsePayload(BaseModel):
    text: str

class BatchImportPayload(BaseModel):
    items: List[Dict[str, Any]]
    clear_old: bool = True

class BatchImportTradesPayload(BaseModel):
    items: List[Dict[str, Any]]

class ImportResultResponse(BaseModel):
    success: bool = True
    imported_count: int = 0
    cleared_count: int = 0
    errors: List[str] = []


class IndicatorResponse(BaseModel):
    stock_code: str
    indicator_type: str
    data_json: Dict[str, Any]
    logic_chain: Optional[Dict[str, Any]]
    analysis_date: date
    
    model_config = ConfigDict(from_attributes=True)
