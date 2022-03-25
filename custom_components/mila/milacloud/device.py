"""Milacares API"""
from .const import PERIOD_DAY, PERIOD_WEEK, PERIOD_MONTH
from .resource import Resource

STATE_DISABLED = "disabled"
STATE_NETWORK = "network"
STATE_PROFILES = "profiles"


class Device(Resource):

    def __init__(self, api, account, data):
        super().__init__(api=api, device=None, data=data)
        self.account = account

    @property
    def id(self):
        return self.data.get("device").get("id")

    @property
    def appliance_code(self):
        return self.data.get("device").get("appliance_code")

    @property
    def name(self):
        return self.data.get("device").get("appliance_name")

    @property
    def os_version(self):
        return self.data.get("device").get("meta").get("fw_version")

    @property
    def is_on(self):
        return self.fan_speed > 0

    @property
    def fan_speed(self):
        return self.data.get("device").get("meta").get("speed") # TODO: set default

    async def set_fan_speed(self, value):
        return await self.api.set_mode_manual(self.appliance_code, value)

    @property
    def fan_mode(self):
        return self.data.get("device").get("meta").get("mode") # TODO: set default

    async def set_fan_mode(self, value, default_speed = 10):
        if value == "automagic":
            return await self.api.set_mode_auto(self.appliance_code)
        else:
            return await self.api.set_mode_manual(self.appliance_code, default_speed)

    def get_mode(self, mode):
        return self.data.get("modes").get(mode)

    # async def set_mode(self, mode, value):
    #     return await self.api.set_mode(mode, value)

    async def set_sounds_enabled(self, value):
        return await self.api.set_sounds_enabled(self.appliance_code, value)

    @property
    def sounds_enabled(self):
        return self.get_mode("sounds_enabled")

    @property
    def night_enabled(self):
        return self.get_mode("night_enabled")

    @property
    def quiet_enabled(self):
        return self.get_mode("quiet_enabled")

    @property
    def housekeeper_enabled(self):
        return self.get_mode("housekeeper_enabled")

    @property
    def quarantine_enabled(self):
        return self.get_mode("quarantine_enabled")

    @property
    def sleep_enabled(self):
        return self.get_mode("sleep_enabled")

    @property
    def turndown_enabled(self):
        return self.get_mode("turndown_enabled")

    @property
    def whitenoise_enabled(self):
        return self.get_mode("whitenoise_enabled")

    @property
    def local_night_start(self):
        return self.get_mode("local_night_start")

    @property
    def local_night_end(self):
        return self.get_mode("local_night_end")

    @property
    def sleep_fan_mode(self):
        return self.get_mode("sleep_fan_mode")

    @property
    def turndown_fan_mode(self):
        return self.get_mode("turndown_fan_mode")

    @property
    def whitenoise_fan_mode(self):
        return self.get_mode("whitenoise_fan_mode")

    def get_sensor_value(self, sensor_name):
        return self.data.get("sensors").get(sensor_name)

    @property
    def aqi(self):
        return self.data.get("device").get("meta").get("latest_aqi").get("value")

    @property
    def pm_1_0(self):
        return self.get_sensor_value("pm_1.0")
    @property
    def pm_2_5(self):
        return self.get_sensor_value("pm_2.5")

    @property
    def pm_10(self):
        return self.get_sensor_value("pm_10")

    @property
    def coppm(self):
        return self.get_sensor_value("coppm")

    @property
    def eco2(self):
        return self.get_sensor_value("eco2")

    @property
    def tvoc(self):
        return self.get_sensor_value("tvoc")

    @property
    def temperature(self):
        return self.get_sensor_value("temperature")

    @property
    def humidity(self):
        return self.get_sensor_value("humidity")
