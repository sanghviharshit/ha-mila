"""The Mila integration."""
import voluptuous as vol
from re import sub

from .const import ERROR_TIME_FORMAT

def snake_case(s):
  return '_'.join(
    sub('([A-Z][a-z]+)', r' \1',
    sub('([A-Z]+)', r' \1',
    s.replace('-', ' '))).split()).lower()

def format_data_usage(value):
    index = 0
    power = 2**10
    units = {
        0: "B",
        1: "KB",
        2: "MB",
        3: "GB",
        4: "TB",
    }
    while value > power:
        value /= power
        index += 1
    return round(value, 1), units[index]


def validate_time_format(value):
    """Validate time format."""
    if isinstance(value, int):
        raise vol.Invalid("Ensure time value is wrapped in quotes.")

    if not isinstance(value, str):
        raise vol.Invalid(ERROR_TIME_FORMAT.format(value))

    if value.startswith("-") or value.startswith("+"):
        raise vol.Invalid(ERROR_TIME_FORMAT.format(value))

    parsed = value.split(":")
    if len(parsed) != 2:
        raise vol.Invalid(ERROR_TIME_FORMAT.format(value))

    try:
        hour, minute = int(parsed[0]), int(parsed[1])
    except ValueError as err:
        raise vol.Invalid(ERROR_TIME_FORMAT.format(value)) from err

    if hour > 23 or minute > 59:
        raise vol.Invalid(ERROR_TIME_FORMAT.format(value))

    if hour < 10:
        hour = f"0{hour}"

    if minute < 10:
        minute = f"0{minute}"

    return f"{hour}:{minute}"
