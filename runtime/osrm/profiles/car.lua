-- Minimal car profile for OSRM
local vehicle = {
  access = {"motorcar", "motorcycle", "motor_vehicle"},
  speed = {
    ["motorway"] = 90,
    ["motorway_link"] = 60,
    ["trunk"] = 80,
    ["trunk_link"] = 50,
    ["primary"] = 65,
    ["primary_link"] = 45,
    ["secondary"] = 55,
    ["secondary_link"] = 35,
    ["tertiary"] = 45,
    ["tertiary_link"] = 30,
    ["residential"] = 35,
    ["unclassified"] = 30,
    ["living_street"] = 15,
    ["service"] = 20,
    ["road"] = 40
  },
  turn_penalty = 90,
  speed_factor = 1.0,
  stop_penalty = 10,
  use_turn_restriction = true,
  weight_to_duration = nil,
  max_speed = nil,
  max_weight = nil,
  max_axle_load = nil,
  max_height = nil,
  max_width = nil,
  max_length = nil
}

local pedestrian = {
  speed = {["foot"] = 5, ["pedestrian"] = 5},
  speed_factor = 1.0,
  stop_penalty = 0,
  use_turn_restriction = false
}

return {
  vehicle = vehicle,
  pedestrian = pedestrian,
  bicycle = nil
}
