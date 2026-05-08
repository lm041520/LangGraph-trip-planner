"""旅行规划API路由 (LangGraph 版本)"""

from fastapi import APIRouter, HTTPException
import logging
from ...models.schemas import (
    TripRequest,
    TripPlanActionRequest,
    TripPlanResponse,
    ReplaceAttractionRequest,
    ErrorResponse
)
# 从新的工作流导入
from ...workflows.trip_planner_graph import get_trip_planner_workflow
from ...services.trip_enhancement_service import enhance_trip_plan, reorder_day, replace_attraction

router = APIRouter(prefix="/trip", tags=["旅行规划"])
logger = logging.getLogger(__name__)


@router.post(
    "/plan",
    response_model=TripPlanResponse,
    summary="生成旅行计划",
    description="根据用户输入的旅行需求,生成详细的旅行计划"
)
async def plan_trip(request: TripRequest):
    """
    生成旅行计划 (LangGraph 版本)

    Args:
        request: 旅行请求参数

    Returns:
        旅行计划响应
    """
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"📥 收到旅行规划请求 (LangGraph):")
        logger.info(f"   城市: {request.city}")
        logger.info(f"   日期: {request.start_date} - {request.end_date}")
        logger.info(f"   天数: {request.travel_days}")
        logger.info(f"{'='*60}\n")

        # 获取工作流实例
        logger.info("🔄 获取 LangGraph 工作流实例...")
        workflow = get_trip_planner_workflow()

        # 执行工作流
        logger.info("🚀 开始执行工作流...")
        trip_plan = workflow.plan_trip(request)

        logger.info("✅ 旅行计划生成成功,准备返回响应\n")

        return TripPlanResponse(
            success=True,
            message="旅行计划生成成功 (LangGraph)",
            data=trip_plan
        )

    except Exception as e:
        logger.error(f"❌ 生成旅行计划失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"生成旅行计划失败: {str(e)}"
        )


@router.post("/enhance", response_model=TripPlanResponse, summary="补齐行程增强信息")
async def enhance_plan(request: TripPlanActionRequest):
    try:
        return TripPlanResponse(
            success=True,
            message="行程增强信息已更新",
            data=enhance_trip_plan(request.trip_plan)
        )
    except Exception as e:
        logger.error(f"增强行程失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"增强行程失败: {str(e)}")


@router.post("/reorder-day", response_model=TripPlanResponse, summary="智能重排某天行程")
async def reorder_trip_day(request: TripPlanActionRequest):
    try:
        return TripPlanResponse(
            success=True,
            message="当天行程已智能重排",
            data=reorder_day(request.trip_plan, request.day_index, request.mode, request.note or "")
        )
    except Exception as e:
        logger.error(f"重排行程失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"重排行程失败: {str(e)}")


@router.post("/adjust-day", response_model=TripPlanResponse, summary="按用户意图调整某天行程")
async def adjust_trip_day(request: TripPlanActionRequest):
    try:
        return TripPlanResponse(
            success=True,
            message="当天行程已调整",
            data=reorder_day(request.trip_plan, request.day_index, request.mode, request.note or "")
        )
    except Exception as e:
        logger.error(f"调整行程失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"调整行程失败: {str(e)}")


@router.post("/replace-attraction", response_model=TripPlanResponse, summary="一键替换景点")
async def replace_trip_attraction(request: ReplaceAttractionRequest):
    try:
        return TripPlanResponse(
            success=True,
            message="景点已替换",
            data=replace_attraction(
                request.trip_plan,
                request.day_index,
                request.attraction_index,
                request.preference or ""
            )
        )
    except Exception as e:
        logger.error(f"替换景点失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"替换景点失败: {str(e)}")


@router.get(
    "/health",
    summary="健康检查",
    description="检查旅行规划服务是否正常"
)
async def health_check():
    """健康检查"""
    try:
        workflow = get_trip_planner_workflow()

        return {
            "status": "healthy",
            "service": "trip-planner-langgraph",
            "framework": "LangGraph",
            "graph_compiled": True,
            "tools_loaded": len(workflow.tools) if hasattr(workflow, 'tools') else 0
        }
    except Exception as e:
        logger.error(f"健康检查失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail=f"服务不可用: {str(e)}"
        )

