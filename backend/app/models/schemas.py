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

class TaskStatusResponse(BaseModel):
    id: str
    task_type: str
    status: str
    progress: int
    current_step: Optional[str]
    result_summary: Optional[str]
    error_msg: Optional[str]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class IndicatorResponse(BaseModel):
    stock_code: str
    indicator_type: str
    data_json: Dict[str, Any]
    logic_chain: Optional[Dict[str, Any]]
    analysis_date: date
    
    model_config = ConfigDict(from_attributes=True)
