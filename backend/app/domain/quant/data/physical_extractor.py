import json
import re
from typing import Dict, Any, Optional
from app.framework.logger import logger
from app.domain.research.services.data_loader import data_loader

class PhysicalParameterExtractor:
    """物理参数实时抽取管道 (Live Physical Parameter Extractor)
    
    利用 Web Search (RAG) + LLM 实时抓取特定硬科技参数 (如缺陷密度, 晶圆价格)。
    """
    
    def __init__(self, llm_provider):
        self.llm = llm_provider

    async def extract_parameters(self, query: str, keys_to_extract: list) -> Dict[str, Optional[float]]:
        """
        实时搜索并抽取数值参数。
        
        Args:
            query: 搜索词, 如 "TSMC 3nm defect density D0"
            keys_to_extract: 需要提取的字段名, 如 ["defect_density"]
            
        Returns:
            Dict: 抽取到的数值字典。如 {"defect_density": 0.075}。未找到则值为 None。
        """
        # 1. 发起网络搜索
        logger.info(f"[PhysicalExtractor] Searching for: '{query}'")
        search_results = await data_loader.search_web(query, num=8)
        
        if not search_results:
            logger.warning(f"[PhysicalExtractor] No search results for '{query}'")
            return {k: None for k in keys_to_extract}
            
        # 2. 组装上下文
        snippets = []
        for i, res in enumerate(search_results):
            title = res.get("title", "")
            snippet = res.get("snippet", "")
            snippets.append(f"Source {i+1}: {title}\n{snippet}")
            
        context_text = "\n\n".join(snippets)
        keys_str = ", ".join(f'"{k}"' for k in keys_to_extract)
        
        # 3. 构造 LLM Prompt
        prompt = f"""
You are a top-tier semiconductor physical-economics data extractor.
Your task is to extract exact numerical values for specific technical parameters based ONLY on the provided search results.

[Search Results]:
{context_text}

[Target Parameters to Extract]:
{keys_str}

[Rules]:
1. Extract the most accurate and recent numerical value for each parameter.
2. If the value is a range (e.g. 0.07-0.08), return the average (e.g. 0.075).
3. If the value is not present in the search results at all, set the value to null.
4. Output your response ONLY as a valid JSON object. No markdown formatting, no explanations, no text outside the JSON block.

[Expected Output Format]:
{{
    "parameter_name": 123.45,
    "another_parameter": null
}}
"""
        
        # 4. 调用 LLM
        try:
            resp_text = await self.llm.chat_pro(prompt)
            # 清理可能的 markdown code blocks
            clean_text = resp_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]
                
            clean_text = clean_text.strip()
            
            # 解析 JSON
            extracted_data = json.loads(clean_text)
            
            # 过滤并校验结果
            final_result = {}
            for k in keys_to_extract:
                val = extracted_data.get(k)
                if val is not None:
                    try:
                        final_result[k] = float(val)
                    except (ValueError, TypeError):
                        final_result[k] = None
                else:
                    final_result[k] = None
                    
            logger.info(f"[PhysicalExtractor] Successfully extracted: {final_result}")
            return final_result
            
        except json.JSONDecodeError:
            logger.error(f"[PhysicalExtractor] Failed to parse LLM response as JSON: {resp_text}")
        except Exception as e:
            logger.error(f"[PhysicalExtractor] LLM extraction failed: {e}")
            
        return {k: None for k in keys_to_extract}
