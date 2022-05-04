"""Mila API"""
from .device import Device
from .resource import Resource


class Account(Resource):
    def __init__(self, api, data):
        super().__init__(api=api, device=None, data=data)

    @property
    def email(self):
        return self.data.get("email", {}).get("value")

    @property
    def name(self):
        return self.data.get("name")

    @property
    def devices(self):
        devices = []
        for device in self.data.get("devices", {}).get("data", []):
            devices.append(Device(self.api, self, device))
        return devices

    def get_smart_mode(self, smart_mode):
        return (
            self.data.get("profile")
            .get("data")
            .get("smart_modes")
            .get(smart_mode)
            .get("is_enabled")
        )

    async def set_smart_mode(self, smartmode, value):
        return await self.api.set_smart_mode(smartmode, value)

    @property
    def quiet_zone(self):
        return self.get_smart_mode("quiet_zone")

    @property
    def house_keeper_mode(self):
        return self.get_smart_mode("house_keeper_mode")

    @property
    def turn_down_service(self):
        return self.get_smart_mode("turn_down_service")

    @property
    def sleep_mode(self):
        return self.get_smart_mode("sleep_mode")

    @property
    def whitenoise_mode(self):
        return self.get_smart_mode("whitenoise_mode")

    @property
    def quarantine(self):
        return self.get_smart_mode("quarantine")
