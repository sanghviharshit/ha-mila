"""Per-appliance entity constants.

Kept here (rather than in the integration's top-level `const.py`)
because these values are only meaningful inside the appliance entity
tree.
"""

# Mila reports the fan's actual RPM via the FanSpeed sensor. The bounds
# below are documented in the gist and observed empirically: real units
# never sit below ~500 RPM (the docs say 600 but my unit idles at 500)
# and never above 2000.
MAX_FAN_RPM = 2000
MIN_FAN_RPM = 500  # docs say 600; empirical floor on at least one unit

# Preset modes exposed by the fan entity. We deliberately keep just the
# two natural ones (Automagic = automatic AQI-driven, Manual = user-set
# speed). Smart modes get their own switch entities rather than turning
# them into preset modes — that way users can stack "Sleep on" with a
# specific manual percentage if Mila allows.
PRESET_MODE_AUTOMAGIC = "Automagic"
PRESET_MODE_MANUAL = "Manual"
PRESET_MODES = [PRESET_MODE_AUTOMAGIC, PRESET_MODE_MANUAL]

# Conversion factor from Mila's VOC reading (parts per billion) to the
# HA-standard `ug/m^3`. The number is the empirical value the official
# app uses for "average" VOC molecular weights; it's not chemistry-pure
# but matches what users see in Mila's UI so the sensor displayed value
# tracks the app.
TVOC_PPB_TO_UGM3 = 3.767
