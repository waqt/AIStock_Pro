import math
from typing import List, Dict

def calculate_cosine_similarity(vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
    """
    计算两个特征向量的余弦相似度
    """
    intersection = set(vec1.keys()) & set(vec2.keys())
    numerator = sum([vec1[x] * vec2[x] for x in intersection])

    sum1 = sum([vec1[x] ** 2 for x in vec1.keys()])
    sum2 = sum([vec2[x] ** 2 for x in vec2.keys()])
    denominator = math.sqrt(sum1) * math.sqrt(sum2)

    if not denominator:
        return 0.0
    return float(numerator) / denominator

def calculate_tech_momentum(target_company_ipc: Dict[str, float], peer_companies_data: List[Dict]) -> Dict:
    """
    计算技术协同动量 (TECHMom)
    :param target_company_ipc: 目标公司的专利 IPC 分布向量，例如 {"H04L": 0.5, "G06F": 0.3}
    :param peer_companies_data: 同行公司数据列表，包含:
        - code: 股票代码
        - ipc_vector: IPC 分布向量
        - momentum_12m: 过去12个月累计收益 (剔除近1月)
        - return_std: 月收益率标准差
    :return: 技术动量得分及同行相似度明细
    """
    numerator_sum = 0.0
    denominator_sum = 0.0
    peer_details = []

    for peer in peer_companies_data:
        peer_ipc = peer.get("ipc_vector", {})
        similarity = calculate_cosine_similarity(target_company_ipc, peer_ipc)
        
        momentum = peer.get("momentum_12m", 0.0)
        std_dev = peer.get("return_std", 1.0)
        if std_dev <= 0:
            std_dev = 1.0  # 防止除以0
            
        numerator_sum += similarity * momentum
        denominator_sum += similarity * std_dev
        
        peer_details.append({
            "peer_code": peer.get("code"),
            "similarity": round(similarity, 4),
            "momentum_12m": momentum,
            "return_std": std_dev
        })
        
    tech_mom_score = numerator_sum / denominator_sum if denominator_sum > 0 else 0.0
    
    return {
        "tech_momentum_score": round(tech_mom_score, 4),
        "peer_details": sorted(peer_details, key=lambda x: x["similarity"], reverse=True)
    }
