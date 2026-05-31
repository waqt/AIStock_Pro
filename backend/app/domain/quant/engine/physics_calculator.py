import math
from typing import Dict

def calculate_gdpw(wafer_diameter_mm: float, edge_exclusion_mm: float, die_area_mm2: float) -> int:
    """
    计算晶圆理论最大可用晶粒数 (Gross Dies Per Wafer)
    公式考虑了边缘排除区和划片槽损耗的近似
    """
    if die_area_mm2 <= 0:
        return 0
        
    usable_diameter = wafer_diameter_mm - 2 * edge_exclusion_mm
    usable_radius = usable_diameter / 2
    usable_area = math.pi * (usable_radius ** 2)
    
    # 公式: Area / DieArea - (pi * D_usable) / sqrt(2 * DieArea)
    term1 = usable_area / die_area_mm2
    term2 = (math.pi * usable_diameter) / math.sqrt(2 * die_area_mm2)
    
    gdpw = int(term1 - term2)
    return max(0, gdpw)


def calculate_murphy_yield(die_area_cm2: float, defect_density_cm2: float) -> float:
    """
    利用 Murphy 模型计算良率
    公式: Y = ((1 - exp(-A * D0)) / (A * D0))^2
    """
    if defect_density_cm2 <= 0 or die_area_cm2 <= 0:
        return 1.0
        
    ad0 = die_area_cm2 * defect_density_cm2
    y = ((1 - math.exp(-ad0)) / ad0) ** 2
    return y


def calculate_wafer_cost_per_good_die(wafer_cost_usd: float, wafer_diameter_mm: float, edge_exclusion_mm: float, 
                                      die_area_mm2: float, defect_density_cm2: float) -> Dict:
    """
    计算单颗合格裸晶圆的真实成本 (Wafer Cost Per Good Die)
    """
    gdpw = calculate_gdpw(wafer_diameter_mm, edge_exclusion_mm, die_area_mm2)
    
    die_area_cm2 = die_area_mm2 / 100.0
    yield_rate = calculate_murphy_yield(die_area_cm2, defect_density_cm2)
    
    ndpw = int(gdpw * yield_rate)  # Net Dies Per Wafer
    
    if ndpw <= 0:
        cost_per_die = float('inf')
    else:
        cost_per_die = wafer_cost_usd / ndpw
        
    return {
        "gdpw": gdpw,
        "yield_rate": round(yield_rate, 4),
        "ndpw": ndpw,
        "cost_per_good_die_usd": round(cost_per_die, 2)
    }

def calculate_fabless_margin(asp_usd: float, wafer_cost_per_good_die: float, packaging_test_cost_usd: float, hbm_cost_usd: float = 0.0) -> Dict:
    """
    计算无晶圆厂设计巨头的毛利率 (Fabless Gross Margin)
    通过底层物理成本和高级封装堆栈倒推超额利润截留率
    """
    cogs = wafer_cost_per_good_die + packaging_test_cost_usd + hbm_cost_usd
    if asp_usd <= 0:
        margin = 0.0
    else:
        margin = (asp_usd - cogs) / asp_usd
        
    return {
        "total_cogs_usd": round(cogs, 2),
        "asp_usd": round(asp_usd, 2),
        "gross_margin": round(margin, 4),
        "gross_margin_pct": round(margin * 100, 2)
    }
