# Data Source Plugin Architecture
from app.core.data_sources.base import DataSourceProtocol
from app.core.data_sources.sina import SinaSource
from app.core.data_sources.akshare import AkShareSource

__all__ = ["DataSourceProtocol", "SinaSource", "AkShareSource"]
