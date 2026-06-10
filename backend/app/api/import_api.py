from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional

from app.framework.database.session import get_db
from app.domain.portfolio.services.ai_import import AIImportService
from app.framework.tasks.engine import task_manager
from app.framework.logger import logger
from app.models.schemas import (
    TextParsePayload, BatchImportPayload, BatchImportTradesPayload
)

router = APIRouter(prefix="/api/ai", tags=["AI 导入"])


# 1. 恢复缓存
@router.get("/get-cache")
async def get_cache():
    cache = AIImportService.get_cache()
    if not cache:
        return {"success": False, "message": "暂无缓存记录"}
    return {"success": True, "data": cache.get("data"), "type": cache.get("type")}


@router.delete("/cache")
async def clear_cache():
    """清除导入缓存 (导入成功后调用)"""
    AIImportService.clear_cache()
    return {"success": True, "message": "缓存已清除"}


# 2. 持仓截图识别 (异步任务)
@router.post("/recognize-image")
async def recognize_image(payload: Dict[str, Any]):
    image = payload.get("image", "")
    if not image:
        raise HTTPException(status_code=400, detail="未提供图片数据")
    try:
        task_id = await task_manager.run_task(
            "ai_recognize",
            params={"image_base64": image, "recognize_type": "position"}
        )
        return {"success": True, "task_id": task_id, "message": "AI 识别任务已提交，请轮询进度"}
    except Exception as e:
        logger.error(f"[❌] Image recognition error: {e}")
        raise HTTPException(status_code=500, detail=f"识别引擎异常: {str(e)}")


# 3. 交易截图识别 (异步任务)
@router.post("/recognize-trades")
async def recognize_trades(payload: Dict[str, Any]):
    image = payload.get("image", "")
    if not image:
        raise HTTPException(status_code=400, detail="未提供图片数据")
    try:
        task_id = await task_manager.run_task(
            "ai_recognize",
            params={"image_base64": image, "recognize_type": "trade"}
        )
        return {"success": True, "task_id": task_id, "message": "AI 识别任务已提交，请轮询进度"}
    except Exception as e:
        logger.error(f"[❌] Trade image recognition error: {e}")
        raise HTTPException(status_code=500, detail=f"识别引擎异常: {str(e)}")


# 4. 文本解析
@router.post("/parse-text")
async def parse_text(payload: TextParsePayload):
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="未提供文本数据")
    results = AIImportService.parse_raw_text(payload.text)
    return {"success": True, "data": results, "count": len(results)}


# 5. 批量导入持仓
@router.post("/batch-import")
async def batch_import(
    payload: BatchImportPayload,
    db: AsyncSession = Depends(get_db)
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="没有要导入的数据")
    try:
        result = await AIImportService.batch_import_positions(db, payload.items, payload.clear_old)
        return result
    except Exception as e:
        logger.error(f"[❌] Batch import error: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


# 6. 批量导入交易记录
@router.post("/batch-import-trades")
async def batch_import_trades(
    payload: BatchImportTradesPayload,
    db: AsyncSession = Depends(get_db)
):
    if not payload.items:
        raise HTTPException(status_code=400, detail="没有要导入的数据")
    try:
        result = await AIImportService.batch_import_trades(db, payload.items)
        return result
    except Exception as e:
        logger.error(f"[❌] Batch import trades error: {e}")
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


# 7. Excel 上传解析
@router.post("/upload-excel")
async def upload_excel(
    file: UploadFile = File(...),
    sheet_type: Optional[str] = Form("position")
):
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls 格式")
    try:
        contents = await file.read()
        results = await AIImportService.ai_parse_excel(contents, sheet_type)
        return {"success": True, "data": results, "count": len(results)}
    except Exception as e:
        logger.error(f"[❌] Excel parse error: {e}")
        raise HTTPException(status_code=500, detail=f"Excel 解析异常: {str(e)}")
