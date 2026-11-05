# Fan Services
MAX_FAN_RPM = 2000
MIN_FAN_RPM = 500 #docs say 600, but mine seems like 500, make into an option?
PRESET_MODE_AUTOMAGIC = "Automagic"
PRESET_MODE_MANUAL = "Manual"

TVOC_PPB_TO_UGM3 = 3.767

# Room Goal / Performance Profiles
ROOM_GOAL_ENERGY_EFFICIENCY = "Energy Efficiency"
ROOM_GOAL_QUIETEST = "Quietest"
ROOM_GOAL_NORMAL_HUMAN = "Normal Human"
ROOM_GOAL_MODERATE = "Moderate"
ROOM_GOAL_MAX_FILTRATION = "Max Filtration"

PRESET_MODES = [
    PRESET_MODE_MANUAL,
    ROOM_GOAL_ENERGY_EFFICIENCY,
    ROOM_GOAL_QUIETEST,
    ROOM_GOAL_NORMAL_HUMAN,
    ROOM_GOAL_MODERATE,
    ROOM_GOAL_MAX_FILTRATION,
]

ROOM_GOAL_TO_PROFILE = {
    ROOM_GOAL_ENERGY_EFFICIENCY: "EnergyEfficient",
    ROOM_GOAL_QUIETEST: "Quietest",
    ROOM_GOAL_NORMAL_HUMAN: "Normal",
    ROOM_GOAL_MODERATE: "Moderate",
    ROOM_GOAL_MAX_FILTRATION: "MaxFiltration",
}

PROFILE_TO_ROOM_GOAL = {v: k for k, v in ROOM_GOAL_TO_PROFILE.items()}

ROOM_GOAL_DETAILS = {
    ROOM_GOAL_ENERGY_EFFICIENCY: {
        "air_changes_per_day": 24,
        "description": "For users who want to minimize energy consumption and prioritize power savings, accepting slower air cleaning as a tradeoff.",
    },
    ROOM_GOAL_QUIETEST: {
        "air_changes_per_day": 48,
        "description": "For users who are sensitive to noise and prioritize a quiet environment. Reduces noise to a minimum, even if it means slightly less air cleaning speed.",
    },
    ROOM_GOAL_NORMAL_HUMAN: {
        "air_changes_per_day": 60,
        "description": "For users looking for balanced performance—a good mix of clean air, reasonable noise, and energy efficiency. Suitable for most households.",
    },
    ROOM_GOAL_MODERATE: {
        "air_changes_per_day": 72,
        "description": "For users who prefer boosted performance but don't need the maximum setting. Balances effective purification with moderate noise and energy use.",
    },
    ROOM_GOAL_MAX_FILTRATION: {
        "air_changes_per_day": 96,
        "description": "For users who want the highest level of air cleaning, even if it means more noise. Ideal for those seeking to achieve hospital grade air quality ratings.",
    },
}
