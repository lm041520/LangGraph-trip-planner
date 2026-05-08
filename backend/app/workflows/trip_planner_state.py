"""旅行规划工作流状态定义"""

from typing import Dict, Any, List, Optional, Callable
try:
    from typing import Annotated
except ImportError:
    from typing_extensions import Annotated
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from ..models.schemas import TripRequest, TripPlan, Attraction, WeatherInfo, Hotel


def update_step(prev: str, new: str) -> str:
    """更新步骤，总是使用新值"""
    return new


def update_error(prev: Optional[str], new: Optional[str]) -> Optional[str]:
    """Keep the first error reported by parallel branches."""
    return prev or new


class TripPlannerState(TypedDict):
    """旅行规划工作流状态"""
    # 输入
    request: TripRequest
    user_input: str

    # 中间结果
    attractions: List[Attraction]
    weather_info: List[WeatherInfo]
    hotels: List[Hotel]

    # 智能体通信
    messages: Annotated[List[Dict], add_messages]

    # 最终输出
    trip_plan: Optional[TripPlan]
    error: Annotated[Optional[str], update_error]
    current_step: Annotated[str, update_step]  # 跟踪当前执行步骤


# 状态辅助函数
def create_initial_state(request: TripRequest, user_input: str = "") -> TripPlannerState:
    """创建初始状态"""
    return {
        "request": request,
        "user_input": user_input,
        "attractions": [],
        "weather_info": [],
        "hotels": [],
        "messages": [],
        "trip_plan": None,
        "error": None,
        "current_step": "started"
    }


def update_state_with_attractions(state: TripPlannerState, attractions: List[Attraction]) -> TripPlannerState:
    """更新状态中的景点信息"""
    return {
        **state,
        "attractions": attractions,
        "current_step": "attractions_searched",
        "messages": state["messages"] + [
            {"role": "assistant", "content": f"已找到 {len(attractions)} 个景点"}
        ]
    }


def update_state_with_weather(state: TripPlannerState, weather_info: List[WeatherInfo]) -> TripPlannerState:
    """更新状态中的天气信息"""
    return {
        **state,
        "weather_info": weather_info,
        "current_step": "weather_checked",
        "messages": state["messages"] + [
            {"role": "assistant", "content": f"已获取 {len(weather_info)} 天天气信息"}
        ]
    }


def update_state_with_hotels(state: TripPlannerState, hotels: List[Hotel]) -> TripPlannerState:
    """更新状态中的酒店信息"""
    return {
        **state,
        "hotels": hotels,
        "current_step": "hotels_found",
        "messages": state["messages"] + [
            {"role": "assistant", "content": f"已找到 {len(hotels)} 个酒店"}
        ]
    }


def update_state_with_plan(state: TripPlannerState, trip_plan: TripPlan) -> TripPlannerState:
    """更新状态中的旅行计划"""
    return {
        **state,
        "trip_plan": trip_plan,
        "current_step": "plan_completed",
        "messages": state["messages"] + [
            {"role": "assistant", "content": "行程计划生成完成！"}
        ]
    }


def update_state_with_error(state: TripPlannerState, error: str) -> TripPlannerState:
    """更新状态中的错误信息"""
    return {
        **state,
        "error": error,
        "current_step": "error",
        "messages": state["messages"] + [
            {"role": "assistant", "content": f"遇到错误: {error}"}
        ]
    }


def has_error(state: TripPlannerState) -> bool:
    """检查状态是否包含错误"""
    return state.get("error") is not None


def get_current_step(state: TripPlannerState) -> str:
    """获取当前步骤"""
    return state.get("current_step", "unknown")
