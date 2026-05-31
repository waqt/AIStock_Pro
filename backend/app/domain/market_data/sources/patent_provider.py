import abc
import asyncio
import httpx
from typing import Dict, List, Optional
from app.framework.logger import logger
from app.framework.config import settings

class BasePatentProvider(abc.ABC):
    """专利数据提供者基类"""
    
    @abc.abstractmethod
    async def fetch_ipc_vectors(self, company_name: str, years_lookback: int = 5) -> Dict[str, float]:
        """
        获取指定公司过去 N 年专利的 IPC 子类分类频次向量
        返回如: {"H04L": 0.45, "G06F": 0.35, "H01L": 0.20}
        数值为归一化后的频率
        """
        pass

    def _normalize_vector(self, raw_counts: Dict[str, int]) -> Dict[str, float]:
        """将绝对数量归一化为频次分布 (和为1.0)"""
        total = sum(raw_counts.values())
        if total == 0:
            return {}
        return {k: round(v / total, 4) for k, v in raw_counts.items()}


class PatentsViewProvider(BasePatentProvider):
    """美国专利获取接口 (PatentsView API)"""
    
    BASE_URL = "https://api.patentsview.org/patents/query"
    
    async def fetch_ipc_vectors(self, company_name: str, years_lookback: int = 5) -> Dict[str, float]:
        """利用 PatentsView 获取美股/跨国公司的 IPC 向量"""
        # 构建查询条件
        query = {
            "_and": [
                {"_text_any": {"assignee_organization": company_name}}
            ]
        }
        # 需提取字段: patent_number, ipc_section, ipc_class, ipc_subclass
        fields = ["patent_number", "ipc_section", "ipc_class", "ipc_subclass"]
        
        params = {
            "q": str(query).replace("'", '"'),
            "f": str(fields).replace("'", '"'),
            "o": '{"per_page": 500}' # 取最近 500 个样本计算分布即可
        }
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(self.BASE_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    patents = data.get("patents", [])
                    if not patents:
                        return {}
                        
                    ipc_counts = {}
                    for patent in patents:
                        ipcs = patent.get("ipc", [])
                        for ipc in ipcs:
                            # 拼接为 IPC 子类代码，如 "H04L"
                            section = ipc.get("ipc_section", "")
                            cls = ipc.get("ipc_class", "")
                            subcls = ipc.get("ipc_subclass", "")
                            if section and cls and subcls:
                                ipc_code = f"{section}{cls}{subcls}".upper()
                                ipc_counts[ipc_code] = ipc_counts.get(ipc_code, 0) + 1
                                
                    return self._normalize_vector(ipc_counts)
                else:
                    logger.warning(f"[PatentsView] API HTTP {resp.status_code}: {resp.text[:100]}")
        except Exception as e:
            logger.error(f"[PatentsView] Failed to fetch data for {company_name}: {e}")
            
        return {}


class EPOProvider(BasePatentProvider):
    """欧洲专利局 (EPO) Open Data API"""
    
    BASE_URL = "http://ops.epo.org/rest-services/published-data/search"
    
    async def fetch_ipc_vectors(self, company_name: str, years_lookback: int = 5) -> Dict[str, float]:
        """欧洲专利查询 (需 OAuth 2.0 Auth, 此处做基础请求结构示例)"""
        # OPS 接口需要 Consumer Key 和 Secret
        if not hasattr(settings, "EPO_CONSUMER_KEY") or not settings.EPO_CONSUMER_KEY:
            logger.info("[EPO] API credentials not configured, skipping.")
            return {}
            
        # 假设已获取 access_token
        access_token = "MOCK_TOKEN" 
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        
        # CQL 查询语句: assignee = company_name
        cql_query = f'pa="{company_name}"'
        
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(f"{self.BASE_URL}?q={cql_query}", headers=headers)
                if resp.status_code == 200:
                    # 实际 EPO 返回格式极度复杂 (XML为主, JSON有限)，这里做伪代码处理提取
                    # 真实落地中需要解析返回的文献 IPC 字段
                    pass
        except Exception as e:
            logger.error(f"[EPO] Failed to fetch data for {company_name}: {e}")
            
        return {}


class CNIPAProvider(BasePatentProvider):
    """中国国家知识产权局 (CNIPA) 接口"""
    
    async def fetch_ipc_vectors(self, company_name: str, years_lookback: int = 5) -> Dict[str, float]:
        """
        国知局接口往往需要企业级鉴权或者通过天眼查/企查查等三方数据商中转。
        目前构建结构占位，等待接入第三方数据商(如天眼查 API)。
        """
        if not hasattr(settings, "QCC_API_KEY") or not settings.QCC_API_KEY:
            logger.info(f"[CNIPA] No third-party API key configured to query CNIPA data for {company_name}.")
            return {}
            
        # TODO: 接入天眼查/企查查的专利查询接口 (如: 获取企业专利详情 API)
        return {}


class GlobalPatentAggregator:
    """全球专利数据聚合器"""
    
    def __init__(self):
        self.providers = [
            PatentsViewProvider(),
            EPOProvider(),
            CNIPAProvider()
        ]
        
    async def get_aggregated_ipc_vectors(self, company_name: str) -> Dict[str, float]:
        """并行获取多家专利局数据，合并后计算全局频次"""
        tasks = [provider.fetch_ipc_vectors(company_name) for provider in self.providers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        aggregated_counts = {}
        for result in results:
            if isinstance(result, dict):
                for ipc, weight in result.items():
                    # 这里 weight 是独立归一化过的，为了简单聚合，我们等权重相加
                    aggregated_counts[ipc] = aggregated_counts.get(ipc, 0.0) + weight
                    
        # 再次进行全局归一化
        total_weight = sum(aggregated_counts.values())
        if total_weight == 0:
            return {}
            
        return {k: round(v / total_weight, 4) for k, v in aggregated_counts.items()}
