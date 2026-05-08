"""Post-processing and interaction helpers for trip plans."""

from __future__ import annotations

from copy import deepcopy
from math import asin, cos, radians, sin, sqrt
from typing import List, Optional, Tuple

from ..models.schemas import (
    Attraction,
    DayPlan,
    DayRoute,
    DayScore,
    Location,
    RouteLeg,
    TripPlan,
    TripRequest,
    WeatherInfo,
)


INDOOR_KEYWORDS = ("博物馆", "美术馆", "商场", "展馆", "剧院", "书店", "寺", "宫", "馆")
OUTDOOR_KEYWORDS = ("公园", "山", "湖", "海", "园", "长城", "广场", "街", "巷")


def enhance_trip_plan(plan: TripPlan, request: Optional[TripRequest] = None) -> TripPlan:
    """Add route chains, scores, weather tips and packing checklist."""
    enhanced = plan.model_copy(deep=True)

    if request:
        enhanced.travel_style = request.travel_style
        enhanced.budget_level = request.budget_level

    enhanced.weather_alerts = _build_weather_alerts(enhanced.weather_info)
    enhanced.packing_checklist = _build_packing_checklist(enhanced, request)
    enhanced.day_routes = []
    enhanced.daily_scores = []

    for day in enhanced.days:
        weather = _weather_for_day(enhanced.weather_info, day.date, day.day_index)
        route = _build_day_route(day)
        score = _score_day(day, route, weather, enhanced.budget_level)

        day.weather_tip = _weather_tip(weather, day)
        day.route_summary = route.summary
        day.score = score
        enhanced.day_routes.append(route)
        enhanced.daily_scores.append(score)

    return enhanced


def reorder_day(plan: TripPlan, day_index: int, mode: str = "relaxed", note: str = "") -> TripPlan:
    """Reorder one day according to a lightweight interaction mode."""
    updated = plan.model_copy(deep=True)
    if day_index >= len(updated.days):
        return enhance_trip_plan(updated)

    day = updated.days[day_index]
    mode_text = f"{mode} {note}".lower()

    if "雨" in mode_text or "indoor" in mode_text or "室内" in mode_text:
        day.attractions.sort(key=lambda item: 0 if _is_indoor(item) else 1)
        day.description = f"{day.description} 已优先安排室内/避雨景点。"
    elif "轻松" in mode_text or "relaxed" in mode_text:
        day.attractions.sort(key=lambda item: item.visit_duration)
        if len(day.attractions) > 2:
            day.attractions = day.attractions[:2]
        day.description = f"{day.description} 已调整为更轻松的节奏。"
    elif "紧凑" in mode_text or "compact" in mode_text or "顺路" in mode_text:
        day.attractions = _nearest_neighbor(day.attractions, day.hotel.location if day.hotel else None)
        day.description = f"{day.description} 已按空间距离重新排序。"
    else:
        day.attractions = list(reversed(day.attractions))
        day.description = f"{day.description} 已重新排序。"

    return enhance_trip_plan(updated)


def replace_attraction(
    plan: TripPlan,
    day_index: int,
    attraction_index: int,
    preference: str = "",
) -> TripPlan:
    """Replace one attraction with a non-duplicate suggestion."""
    updated = plan.model_copy(deep=True)
    if day_index >= len(updated.days):
        return enhance_trip_plan(updated)

    day = updated.days[day_index]
    if attraction_index >= len(day.attractions):
        return enhance_trip_plan(updated)

    used_names = {attr.name for current in updated.days for attr in current.attractions}
    replacement = _find_replacement_from_plan(updated, used_names, preference)

    if replacement is None:
        old = day.attractions[attraction_index]
        replacement = _make_replacement(updated.city, old, preference, len(used_names) + 1)

    day.attractions[attraction_index] = replacement
    day.description = f"{day.description} 已替换 1 个景点。"
    return enhance_trip_plan(updated)


def _build_weather_alerts(weather_info: List[WeatherInfo]) -> List[str]:
    alerts = []
    for weather in weather_info:
        tip = _weather_tip(weather, None)
        if tip:
            alerts.append(f"{weather.date}: {tip}")
    return alerts


def _build_packing_checklist(plan: TripPlan, request: Optional[TripRequest]) -> List[str]:
    checklist = ["身份证件", "手机充电器/充电宝", "常用药品", "舒适步行鞋"]
    weather_text = " ".join(
        f"{item.day_weather} {item.night_weather} {item.day_temp} {item.night_temp}"
        for item in plan.weather_info
    )
    style = request.travel_style if request else plan.travel_style

    if any(word in weather_text for word in ("雨", "雪", "雷", "阵雨")):
        checklist.extend(["雨伞或轻便雨衣", "防水鞋套/备用袜子"])
    if _max_temp(plan.weather_info) >= 30:
        checklist.extend(["防晒霜", "遮阳帽", "便携水杯"])
    if _min_temp(plan.weather_info) <= 8:
        checklist.extend(["保暖外套", "围巾或手套"])
    if "亲子" in style:
        checklist.extend(["儿童证件", "零食和湿巾", "轻便推车"])
    if "拍照" in style:
        checklist.extend(["相机/备用存储卡", "好看的轻便外套"])
    if "老人" in style:
        checklist.extend(["慢病药物", "折叠手杖", "休息点备选"])

    return list(dict.fromkeys(checklist))


def _build_day_route(day: DayPlan) -> DayRoute:
    stops: List[Tuple[str, Optional[Location]]] = []
    if day.hotel:
        stops.append((day.hotel.name, day.hotel.location))
    stops.extend((attr.name, attr.location) for attr in day.attractions)
    if day.hotel and len(stops) > 1:
        stops.append((day.hotel.name, day.hotel.location))

    legs: List[RouteLeg] = []
    for index in range(len(stops) - 1):
        origin_name, origin = stops[index]
        dest_name, dest = stops[index + 1]
        distance = _distance_km(origin, dest)
        duration = _duration_minutes(distance, day.transportation)
        legs.append(
            RouteLeg(
                origin=origin_name,
                destination=dest_name,
                distance_km=round(distance, 1),
                duration_min=duration,
                transport=day.transportation,
            )
        )

    total_distance = round(sum(leg.distance_km for leg in legs), 1)
    total_duration = sum(leg.duration_min for leg in legs)
    summary = f"约 {total_distance} 公里，路上约 {total_duration} 分钟" if legs else "路线信息不足"
    return DayRoute(
        day_index=day.day_index,
        summary=summary,
        legs=legs,
        total_distance_km=total_distance,
        total_duration_min=total_duration,
    )


def _score_day(day: DayPlan, route: DayRoute, weather: Optional[WeatherInfo], budget_level: str) -> DayScore:
    route_score = max(45, 100 - int(route.total_distance_km * 4))
    visit_minutes = sum(attr.visit_duration for attr in day.attractions)
    intensity_load = visit_minutes + route.total_duration_min
    intensity = max(35, 100 - abs(390 - intensity_load) // 5 - max(0, len(day.attractions) - 3) * 12)
    day_cost = sum(attr.ticket_price or 0 for attr in day.attractions)
    day_cost += sum(meal.estimated_cost or 0 for meal in day.meals)
    if day.hotel:
        day_cost += day.hotel.estimated_cost or 0
    budget_target = {"经济": 450, "舒适": 900, "豪华": 1800}.get(budget_level, 900)
    budget_score = max(35, 100 - max(0, day_cost - budget_target) // 20)
    weather_score = _weather_fit_score(day, weather)
    overall = int((route_score + intensity + budget_score + weather_score) / 4)
    comment = _score_comment(route_score, intensity, budget_score, weather_score)

    return DayScore(
        day_index=day.day_index,
        route_compactness=route_score,
        intensity=intensity,
        budget_friendliness=budget_score,
        weather_fit=weather_score,
        overall=overall,
        comment=comment,
    )


def _weather_tip(weather: Optional[WeatherInfo], day: Optional[DayPlan]) -> str:
    if not weather:
        return ""

    text = f"{weather.day_weather}{weather.night_weather}"
    high = _to_int(weather.day_temp)
    low = _to_int(weather.night_temp)

    if any(word in text for word in ("雨", "雪", "雷", "雾")):
        return "天气不稳定，建议把室外景点放在天气较好的时段，并准备室内备选。"
    if high >= 32:
        return "白天气温较高，建议减少正午户外排队，增加补水和午休。"
    if low <= 5:
        return "早晚偏冷，建议带保暖外套，夜间活动适当缩短。"
    if day and len(day.attractions) >= 3:
        return "行程较满，建议提前确认景点开放时间。"
    return "天气对行程影响较小，按原计划游览即可。"


def _weather_fit_score(day: DayPlan, weather: Optional[WeatherInfo]) -> int:
    if not weather:
        return 80

    text = f"{weather.day_weather}{weather.night_weather}"
    outdoor_count = sum(1 for attr in day.attractions if _is_outdoor(attr))
    if any(word in text for word in ("雨", "雪", "雷")) and outdoor_count:
        return max(45, 90 - outdoor_count * 18)
    if _to_int(weather.day_temp) >= 32 and outdoor_count:
        return max(50, 92 - outdoor_count * 12)
    return 88


def _weather_for_day(weather_info: List[WeatherInfo], date: str, day_index: int) -> Optional[WeatherInfo]:
    for weather in weather_info:
        if weather.date == date:
            return weather
    if 0 <= day_index < len(weather_info):
        return weather_info[day_index]
    return None


def _distance_km(origin: Optional[Location], dest: Optional[Location]) -> float:
    if not origin or not dest:
        return 0

    lon1, lat1, lon2, lat2 = map(radians, [origin.longitude, origin.latitude, dest.longitude, dest.latitude])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    value = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(value))


def _duration_minutes(distance_km: float, transport: str) -> int:
    if distance_km <= 0:
        return 0
    if "步" in transport:
        speed = 4.5
    elif "自驾" in transport or "驾" in transport:
        speed = 28
    else:
        speed = 18
    return max(5, int(distance_km / speed * 60))


def _nearest_neighbor(attractions: List[Attraction], start: Optional[Location]) -> List[Attraction]:
    remaining = attractions[:]
    ordered: List[Attraction] = []
    current = start
    while remaining:
        if current:
            next_attr = min(remaining, key=lambda item: _distance_km(current, item.location))
        else:
            next_attr = remaining[0]
        ordered.append(next_attr)
        remaining.remove(next_attr)
        current = next_attr.location
    return ordered


def _find_replacement_from_plan(plan: TripPlan, used_names: set[str], preference: str) -> Optional[Attraction]:
    for day in plan.days:
        for attr in day.attractions:
            if attr.name in used_names:
                continue
            if preference and preference not in f"{attr.name}{attr.category}{attr.description}":
                continue
            return deepcopy(attr)
    return None


def _make_replacement(city: str, old: Attraction, preference: str, offset: int) -> Attraction:
    category = preference or old.category or "景点"
    return Attraction(
        name=f"{city}{category}备选{offset}",
        address=f"{city}市内",
        location=Location(
            longitude=old.location.longitude + 0.006 * (offset % 5 + 1),
            latitude=old.location.latitude + 0.004 * (offset % 4 + 1),
        ),
        visit_duration=max(60, old.visit_duration),
        description=f"根据当前偏好补充的{category}备选点，可替换原景点并保持当天节奏。",
        category=category,
        ticket_price=old.ticket_price,
    )


def _is_indoor(attr: Attraction) -> bool:
    text = f"{attr.name}{attr.category}{attr.description}"
    return any(word in text for word in INDOOR_KEYWORDS)


def _is_outdoor(attr: Attraction) -> bool:
    text = f"{attr.name}{attr.category}{attr.description}"
    return any(word in text for word in OUTDOOR_KEYWORDS) or not _is_indoor(attr)


def _max_temp(weather_info: List[WeatherInfo]) -> int:
    return max([_to_int(item.day_temp) for item in weather_info] or [0])


def _min_temp(weather_info: List[WeatherInfo]) -> int:
    return min([_to_int(item.night_temp) for item in weather_info] or [20])


def _to_int(value) -> int:
    try:
        return int(str(value).replace("°C", "").replace("℃", "").replace("°", "").strip())
    except (TypeError, ValueError):
        return 0


def _score_comment(route_score: int, intensity: int, budget_score: int, weather_score: int) -> str:
    weak = min(
        [
            ("路线略分散", route_score),
            ("强度需要留意", intensity),
            ("预算压力偏高", budget_score),
            ("天气适配一般", weather_score),
        ],
        key=lambda item: item[1],
    )
    if weak[1] >= 80:
        return "整体安排均衡，适合按计划执行。"
    return f"{weak[0]}，建议按现场情况微调。"
