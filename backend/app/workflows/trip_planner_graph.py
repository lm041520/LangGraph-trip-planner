"""旅行规划 LangGraph 工作流"""

from typing import Dict, Any, List, Optional
import json
import logging
from datetime import datetime, timedelta
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage

from .trip_planner_state import TripPlannerState, create_initial_state, has_error
from ..agents.langgraph_agents import (
    create_attraction_search_agent,
    create_weather_agent,
    create_hotel_agent,
    create_planner_agent
)
from ..tools.amap_mcp_tools import get_cached_amap_tools
from ..models.schemas import (
    TripRequest, TripPlan, DayPlan, Attraction, Meal, WeatherInfo,
    Location, Hotel, Budget
)

# 设置日志记录
logger = logging.getLogger(__name__)


class TripPlannerWorkflow:
    """多智能体旅行规划工作流 (LangGraph 版本)"""

    def __init__(self):
        """初始化工作流"""
        logger.info("🔄 初始化 LangGraph 旅行规划工作流...")

        try:
            # 初始化工具
            self.tools = get_cached_amap_tools()
            if not self.tools:
                logger.warning("⚠️  未加载到任何工具，工作流可能无法正常工作")
            else:
                logger.info(f"✅ 加载了 {len(self.tools)} 个工具")
                for tool in self.tools:
                    logger.debug(f"  工具: {tool.name} - {tool.description}")

            # 创建智能体
            logger.info("创建智能体...")
            self.attraction_agent = create_attraction_search_agent(self.tools)
            self.weather_agent = create_weather_agent(self.tools)
            self.hotel_agent = create_hotel_agent(self.tools)
            self.planner_agent = create_planner_agent([])  # 行程规划不需要外部工具

            # 构建工作流图
            logger.info("构建 StateGraph...")
            self.graph = self._build_graph()

            logger.info("✅ LangGraph 工作流初始化成功")

        except Exception as e:
            logger.error(f"❌ 工作流初始化失败: {str(e)}", exc_info=True)
            raise

    def _prepare_agent_input(self, user_input: str, chat_history: list) -> dict:
        """准备智能体输入格式，将 input 和 chat_history 转换为 messages 格式"""
        messages = []
        # 添加历史消息（如果存在）
        for msg in chat_history:
            # 假设历史消息格式为 {"role": "...", "content": "..."}
            messages.append(msg)
        # 添加当前用户输入
        messages.append({"role": "user", "content": user_input})
        return {"messages": messages}

    def _extract_agent_output(self, result: dict) -> str:
        """从智能体结果中提取输出文本

        新的 create_agent API 返回的结果包含 'messages' 列表，
        需要提取最后一个 assistant 消息的内容。
        """
        if "messages" in result:
            messages = result["messages"]
            # 查找最后一个 assistant 消息
            for msg in reversed(messages):
                # 处理字典格式的消息
                if isinstance(msg, dict):
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "")
                        # 如果 content 是字典，转换为字符串
                        if isinstance(content, dict):
                            import json
                            content = json.dumps(content, ensure_ascii=False)
                        return str(content)
                else:
                    # 处理 LangChain 消息对象 (AIMessage, HumanMessage 等)
                    # 尝试获取消息类型
                    msg_type = None
                    if hasattr(msg, 'type'):
                        msg_type = msg.type
                    elif hasattr(msg, 'role'):
                        msg_type = msg.role

                    # 检查是否是 assistant/ai 消息
                    if msg_type in ["assistant", "ai"]:
                        content = ""
                        if hasattr(msg, 'content'):
                            content = msg.content
                        elif hasattr(msg, 'get'):
                            content = msg.get("content", "")
                        # 如果 content 是字典，转换为字符串
                        if isinstance(content, dict):
                            import json
                            content = json.dumps(content, ensure_ascii=False)
                        return str(content)
            # 如果没有找到 assistant 消息，返回空字符串
            return ""
        elif "output" in result:
            # 兼容旧格式
            return result["output"]
        else:
            # 尝试查找其他可能的字段
            for key in ["text", "response", "content"]:
                if key in result:
                    return str(result[key])
            # 如果都没有，返回整个结果的字符串表示
            return str(result)

    def _build_graph(self) -> StateGraph:
        """构建 StateGraph"""
        workflow = StateGraph(TripPlannerState)
        # 添加节点
        workflow.add_node("search_attractions", self._search_attractions)
        workflow.add_node("check_weather", self._check_weather)
        workflow.add_node("find_hotels", self._find_hotels)
        workflow.add_node("join_research_results", self._join_research_results)
        workflow.add_node("plan_itinerary", self._plan_itinerary)
        workflow.add_node("handle_error", self._handle_error)
        # 设置入口点
        workflow.add_edge(START, "search_attractions")
        workflow.add_edge(START, "check_weather")
        workflow.add_edge(START, "find_hotels")
        # 添加边（正常流程）
        workflow.add_edge(
            ["search_attractions", "check_weather", "find_hotels"],
            "join_research_results"
        )
        # 添加错误处理边
        workflow.add_conditional_edges(
            "join_research_results",
            self._check_error,
            {
                "continue": "plan_itinerary",
                "error": "handle_error"
            }
        )

        workflow.add_edge("handle_error", END)
        workflow.add_edge("plan_itinerary", END)

        return workflow.compile()

    def _join_research_results(self, state: TripPlannerState) -> Dict[str, Any]:
        """Join parallel research branches before itinerary planning."""
        logger.info("Research agents completed; preparing itinerary planning...")
        return {"current_step": "research_completed"}

    def _search_attractions(self, state: TripPlannerState) -> Dict[str, Any]:
        """搜索景点节点"""
        logger.info("📍 搜索景点...")
        try:
            # 构建查询
            query = self._build_attraction_query(state["request"])

            # 执行智能体
            result = self.attraction_agent.invoke(
                self._prepare_agent_input(query, [])
            )

            # 更新状态
            output = self._extract_agent_output(result)
            attractions = self._parse_attractions(output)

            return {
                "attractions": attractions,
                "messages": [{"role": "assistant", "content": f"已找到 {len(attractions)} 个景点"}]
            }

        except Exception as e:
            logger.error(f"景点搜索失败: {str(e)}", exc_info=True)
            return {
                "error": f"景点搜索失败: {str(e)}",
                "current_step": "error"
            }

    def _check_weather(self, state: TripPlannerState) -> Dict[str, Any]:
        """查询天气节点"""
        logger.info("🌤️  查询天气...")
        try:
            query = f"查询{state['request'].city}的天气信息"

            result = self.weather_agent.invoke(
                self._prepare_agent_input(query, [])
            )

            output = self._extract_agent_output(result)
            weather_info = self._parse_weather(output)

            return {
                "weather_info": weather_info,
                "messages": [{"role": "assistant", "content": f"已获取 {len(weather_info)} 天天气信息"}]
            }

        except Exception as e:
            logger.error(f"天气查询失败: {str(e)}", exc_info=True)
            return {
                "error": f"天气查询失败: {str(e)}",
                "current_step": "error"
            }

    def _find_hotels(self, state: TripPlannerState) -> Dict[str, Any]:
        """搜索酒店节点"""
        logger.info("🏨 搜索酒店...")
        try:
            query = f"搜索{state['request'].city}的{state['request'].accommodation}酒店"

            result = self.hotel_agent.invoke(
                self._prepare_agent_input(query, [])
            )

            output = self._extract_agent_output(result)
            hotels = self._parse_hotels(output)

            return {
                "hotels": hotels,
                "current_step": "hotels_found",
                "messages": [{"role": "assistant", "content": f"已找到 {len(hotels)} 个酒店"}]
            }

        except Exception as e:
            logger.error(f"酒店搜索失败: {str(e)}", exc_info=True)
            return {
                "error": f"酒店搜索失败: {str(e)}",
                "current_step": "error"
            }

    def _plan_itinerary(self, state: TripPlannerState) -> Dict[str, Any]:
        """生成行程计划节点"""
        logger.info("📋 生成行程计划...")
        try:
            # 构建规划查询
            query = self._build_planner_query(
                state["request"],
                state["attractions"],
                state["weather_info"],
                state["hotels"]
            )

            result = self.planner_agent.invoke(
                self._prepare_agent_input(query, [])
            )

            output = self._extract_agent_output(result)
            trip_plan = self._parse_trip_plan(output, state["request"])

            return {
                "trip_plan": trip_plan,
                "current_step": "plan_completed",
                "messages": [{"role": "assistant", "content": "行程计划生成完成！"}]
            }

        except Exception as e:
            logger.error(f"行程规划失败: {str(e)}", exc_info=True)
            return {
                "error": f"行程规划失败: {str(e)}",
                "current_step": "error"
            }

    def _handle_error(self, state: TripPlannerState) -> Dict[str, Any]:
        """错误处理节点"""
        error_msg = state.get('error', '未知错误')
        logger.warning(f"⚠️  处理错误: {error_msg}")

        # 创建备用计划
        fallback_plan = self._create_fallback_plan(state["request"])

        return {
            "trip_plan": fallback_plan,
            "current_step": "error_handled",
            "messages": [{"role": "assistant", "content": f"遇到错误，已生成备用计划: {error_msg}"}]
        }

    def _check_error(self, state: TripPlannerState) -> str:
        """检查是否有错误"""
        return "error" if state.get("error") else "continue"

    # ============ 辅助方法（从原 trip_planner_agent.py 迁移）============

    def _build_attraction_query(self, request: TripRequest) -> str:
        """构建景点搜索查询"""
        if request.preferences:
            keywords = request.preferences[0]
        else:
            keywords = "景点"

        return f"请搜索{request.city}的{keywords}相关景点"

    def _build_planner_query(self, request: TripRequest, attractions: List[Attraction],
                            weather: List[WeatherInfo], hotels: List[Hotel]) -> str:
        """构建行程规划查询"""
        query = f"""请根据以下信息生成{request.city}的{request.travel_days}天旅行计划:

**基本信息:**
- 城市: {request.city}
- 日期: {request.start_date} 至 {request.end_date}
- 天数: {request.travel_days}天
- 交通方式: {request.transportation}
- 住宿: {request.accommodation}
- 偏好: {', '.join(request.preferences) if request.preferences else '无'}

**景点信息:**
已找到 {len(attractions)} 个景点，包括：{', '.join([a.name for a in attractions[:3]]) if attractions else '无'}

**天气信息:**
{len(weather)} 天天气预报

**酒店信息:**
已找到 {len(hotels)} 个酒店，包括：{', '.join([h.name for h in hotels[:2]]) if hotels else '无'}

**要求:**
1. 每天安排2-3个景点
2. 每天必须包含早中晚三餐
3. 每天推荐一个具体的酒店(从酒店信息中选择)
4. 考虑景点之间的距离和交通方式
5. 返回完整的JSON格式数据
6. 景点的经纬度坐标要真实准确
"""
        if request.free_text_input:
            query += f"\n**额外要求:** {request.free_text_input}"

        return query

    def _extract_json(self, response: str) -> str:
        """从响应文本中提取JSON字符串"""
        # 查找JSON代码块
        if "```json" in response:
            json_start = response.find("```json") + 7
            json_end = response.find("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "```" in response:
            json_start = response.find("```") + 3
            json_end = response.find("```", json_start)
            json_str = response[json_start:json_end].strip()
        elif "[" in response and "]" in response:
            # 处理JSON数组
            json_start = response.find("[")
            json_end = response.rfind("]") + 1
            json_str = response[json_start:json_end]
        elif "{" in response and "}" in response:
            # 直接查找JSON对象
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            json_str = response[json_start:json_end]
        else:
            # 如果没有找到JSON，返回原始响应
            json_str = response.strip()
        return json_str

    def _parse_location(self, value: Any) -> Optional[Location]:
        """Parse location from either a dict or the AMap "lng,lat" format."""
        try:
            if isinstance(value, dict):
                longitude = value.get("longitude", value.get("lng", 0.0))
                latitude = value.get("latitude", value.get("lat", 0.0))
                return Location(longitude=float(longitude or 0.0), latitude=float(latitude or 0.0))

            if isinstance(value, str) and "," in value:
                longitude, latitude = value.split(",", 1)
                return Location(longitude=float(longitude.strip()), latitude=float(latitude.strip()))
        except (TypeError, ValueError):
            logger.warning(f"Invalid location value: {value}")

        return None

    def _parse_attractions(self, response: str) -> List[Attraction]:
        """解析景点信息"""
        try:
            # 尝试从响应中提取JSON
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            # 假设数据是景点列表
            attractions = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        # 转换为Attraction对象
                        attraction = Attraction(
                            name=item.get("name", ""),
                            address=item.get("address", ""),
                            location=self._parse_location(item.get("location")) or Location(longitude=0.0, latitude=0.0),
                            visit_duration=item.get("visit_duration", 120),
                            description=item.get("description", ""),
                            category=item.get("category", "景点"),
                            ticket_price=item.get("ticket_price", 0)
                        )
                        attractions.append(attraction)
            return attractions
        except Exception as e:
            logger.error(f"解析景点信息失败: {str(e)}")
            logger.error(f"原始响应长度: {len(response)}")
            logger.error(f"原始响应前500字符: {response[:500]}")
            logger.error(f"提取的JSON字符串长度: {len(json_str) if 'json_str' in locals() else 'N/A'}")
            if 'json_str' in locals():
                logger.error(f"提取的JSON字符串前500字符: {json_str[:500]}")
            # 返回空列表或示例数据
            return []

    def _parse_weather(self, response: str) -> List[WeatherInfo]:
        """解析天气信息"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            weather_info = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        weather = WeatherInfo(
                            date=item.get("date", ""),
                            day_weather=item.get("day_weather", ""),
                            night_weather=item.get("night_weather", ""),
                            day_temp=item.get("day_temp", 0),
                            night_temp=item.get("night_temp", 0),
                            wind_direction=item.get("wind_direction", ""),
                            wind_power=item.get("wind_power", "")
                        )
                        weather_info.append(weather)
            return weather_info
        except Exception as e:
            logger.error(f"解析天气信息失败: {str(e)}")
            return []

    def _parse_hotels(self, response: str) -> List[Hotel]:
        """解析酒店信息"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            hotels = []
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        hotel = Hotel(
                            name=item.get("name", ""),
                            address=item.get("address", ""),
                            location=self._parse_location(item.get("location")),
                            price_range=item.get("price_range", ""),
                            rating=item.get("rating", ""),
                            distance=item.get("distance", ""),
                            type=item.get("type", ""),
                            estimated_cost=item.get("estimated_cost", 0)
                        )
                        hotels.append(hotel)
            return hotels
        except Exception as e:
            logger.error(f"解析酒店信息失败: {str(e)}")
            return []

    def _parse_trip_plan(self, response: str, request: TripRequest) -> TripPlan:
        """解析行程计划"""
        try:
            json_str = self._extract_json(response)
            data = json.loads(json_str)

            # 转换为TripPlan对象
            trip_plan = TripPlan(
                city=data.get("city", request.city),
                start_date=data.get("start_date", request.start_date),
                end_date=data.get("end_date", request.end_date),
                days=[],
                weather_info=[],
                overall_suggestions=data.get("overall_suggestions", ""),
                budget=None
            )

            # 解析天气信息
            for weather_data in data.get("weather_info", []):
                weather_info = WeatherInfo(**weather_data)
                trip_plan.weather_info.append(weather_info)

            # 解析每日行程
            for day_data in data.get("days", []):
                # 解析景点
                attractions = []
                for attr_data in day_data.get("attractions", []):
                    attraction = Attraction(**attr_data)
                    attractions.append(attraction)

                # 解析餐饮
                meals = []
                for meal_data in day_data.get("meals", []):
                    meal = Meal(**meal_data)
                    meals.append(meal)

                # 解析酒店
                hotel_data = day_data.get("hotel")
                hotel = Hotel(**hotel_data) if hotel_data else None

                day_plan = DayPlan(
                    date=day_data.get("date", ""),
                    day_index=day_data.get("day_index", 0),
                    description=day_data.get("description", ""),
                    transportation=day_data.get("transportation", request.transportation),
                    accommodation=day_data.get("accommodation", request.accommodation),
                    hotel=hotel,
                    attractions=attractions,
                    meals=meals
                )
                trip_plan.days.append(day_plan)

            # 解析预算
            budget_data = data.get("budget")
            if budget_data:
                budget = Budget(**budget_data)
                trip_plan.budget = budget

            return trip_plan
        except Exception as e:
            logger.error(f"解析行程计划失败: {str(e)}")
            # 返回备用计划
            return self._create_fallback_plan(request)

    def _create_fallback_plan(self, request: TripRequest) -> TripPlan:
        """创建备用计划(当Agent失败时)"""
        # 解析日期
        try:
            start_date = datetime.strptime(request.start_date, "%Y-%m-%d")
        except ValueError:
            # 如果日期格式错误，使用当前日期
            start_date = datetime.now()

        # 创建每日行程
        days = []
        for i in range(request.travel_days):
            current_date = start_date + timedelta(days=i)

            day_plan = DayPlan(
                date=current_date.strftime("%Y-%m-%d"),
                day_index=i,
                description=f"第{i+1}天行程",
                transportation=request.transportation,
                accommodation=request.accommodation,
                attractions=[
                    Attraction(
                        name=f"{request.city}景点{j+1}",
                        address=f"{request.city}市",
                        location=Location(longitude=116.4 + i*0.01 + j*0.005, latitude=39.9 + i*0.01 + j*0.005),
                        visit_duration=120,
                        description=f"这是{request.city}的著名景点",
                        category="景点"
                    )
                    for j in range(2)
                ],
                meals=[
                    Meal(type="breakfast", name=f"第{i+1}天早餐", description="当地特色早餐"),
                    Meal(type="lunch", name=f"第{i+1}天午餐", description="午餐推荐"),
                    Meal(type="dinner", name=f"第{i+1}天晚餐", description="晚餐推荐")
                ]
            )
            days.append(day_plan)

        return TripPlan(
            city=request.city,
            start_date=request.start_date,
            end_date=request.end_date,
            days=days,
            weather_info=[],
            overall_suggestions=f"这是为您规划的{request.city}{request.travel_days}日游行程,建议提前查看各景点的开放时间。"
        )

    def plan_trip(self, request: TripRequest) -> TripPlan:
        """执行旅行规划工作流"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 开始 LangGraph 旅行规划工作流...")
        logger.info(f"目的地: {request.city}")
        logger.info(f"{'='*60}\n")

        # 初始化状态
        initial_state: TripPlannerState = create_initial_state(request)

        # 执行工作流
        final_state = self.graph.invoke(initial_state)

        # 检查结果
        if final_state.get("error") and not final_state.get("trip_plan"):
            error_msg = final_state.get("error", "未知错误")
            logger.error(f"❌ 旅行规划失败: {error_msg}")
            raise Exception(error_msg)

        logger.info(f"\n{'='*60}")
        logger.info(f"✅ 旅行计划生成完成!")
        logger.info(f"{'='*60}\n")

        return final_state["trip_plan"]


# 全局工作流实例
_trip_planner_workflow: Optional[TripPlannerWorkflow] = None


def get_trip_planner_workflow() -> TripPlannerWorkflow:
    """获取旅行规划工作流实例（单例模式）"""
    global _trip_planner_workflow

    if _trip_planner_workflow is None:
        _trip_planner_workflow = TripPlannerWorkflow()

    return _trip_planner_workflow


def reset_workflow():
    """重置工作流实例（用于测试或重新配置）"""
    global _trip_planner_workflow
    _trip_planner_workflow = None
    logger.info("工作流实例已重置")
