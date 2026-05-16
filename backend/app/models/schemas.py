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
    profit_loss_ratio: float
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

class IndicatorResponse(BaseModel):
    stock_code: str
    indicator_type: str
    data_json: Dict[str, Any]
    logic_chain: Optional[Dict[str, Any]]
    analysis_date: date
    
    model_config = ConfigDict(from_attributes=True)
