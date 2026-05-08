// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface RouteLeg {
  origin: string
  destination: string
  distance_km: number
  duration_min: number
  transport: string
}

export interface DayRoute {
  day_index: number
  summary: string
  legs: RouteLeg[]
  total_distance_km: number
  total_duration_min: number
}

export interface DayScore {
  day_index: number
  route_compactness: number
  intensity: number
  budget_friendliness: number
  weather_fit: number
  overall: number
  comment: string
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
  weather_tip?: string
  route_summary?: string
  score?: DayScore
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
  travel_style?: string
  budget_level?: string
  weather_alerts?: string[]
  packing_checklist?: string[]
  day_routes?: DayRoute[]
  daily_scores?: DayScore[]
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
  travel_style: string
  budget_level: string
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

