"""Milacares API"""

import logging
from typing import List, Optional
from benedict import benedict
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfLength,
    PERCENTAGE,
    CONCENTRATION_PARTS_PER_MILLION,
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorStateClass
)
from milasdk import MilaApi, ApplianceSensorKind, SmartModeKind, SoundsConfig

from ..util import camel_case_split, coalesce
from .device import MilaDevice

_LOGGER = logging.getLogger(__name__)

class MilaAppliance(MilaDevice):
    """
    API class to represent a single appliance.
    """    
    def __init__(self, coordinator: DataUpdateCoordinator, api: MilaApi, device_id: str):
        super().__init__(coordinator, api, device_id)

    @property
    def name(self) -> str:
        room_kind = ' '.join(camel_case_split(str(self._device_data['room.kind'])))
        return coalesce(
            self._device_data['name'] or None,
            self._device_data['room.name'] or None,
            room_kind
        )

    @property
    def room_id(self) -> str:
        return self._device_data['room.id']

    @property
    def available(self) -> bool:
        return self._device_data['state.actualMode'] is not None

    @property
    def _device_data(self) -> benedict:
        return self._appliance_data[self.id]

    async def set_smart_mode(self, mode: SmartModeKind, is_enabled: bool):
        await self._api.set_smart_mode(self.id, mode, is_enabled)
        await self._coordinator.async_request_refresh()

    async def set_sound_mode(self, mode: SoundsConfig):
        await self._api.set_sound_mode(self.id, mode)
        await self._coordinator.async_request_refresh()

    async def set_fan_mode(self, mode: str):
        if mode == "Automagic":
            await self._api.set_automagic_mode(self.room_id)
        else:
            await self._api.set_manual_mode(self.room_id, 10)
        await self._coordinator.async_request_refresh()

    async def set_fan_speed(self, percentage: Optional[int]):
        await self._api.set_manual_mode(self.room_id, percentage)
        await self._api.force_room_data(self.room_id)
        await self._coordinator.async_request_refresh()

    def _get_all_entities(self) -> List[Entity]:
        #deal with circular imports by bringing in the sensors here
        from ..entities import (
            MilaAppliancePathSensor, 
            MilaApplianceMeasurementSensor, 
            MilaSmartModeSwitch,
            MilaApplianceFan,
            MilaSoundModeSelect,
            TVOC_PPB_TO_UGM3
        )
        entities = [
            MilaAppliancePathSensor(self, "Mode", "state.actualMode", icon="mdi:state-machine", convert_function=lambda v: str(v)),
            MilaAppliancePathSensor(self, "Wifi Strength", "state.wifiRssi", device_class=SensorDeviceClass.SIGNAL_STRENGTH, uom=SIGNAL_STRENGTH_DECIBELS_MILLIWATT, icon="mdi:wifi"),
            MilaAppliancePathSensor(self, "Filter Kind", "filter.kind", icon="mdi:hvac", convert_function=lambda v: str(v)),
            MilaAppliancePathSensor(self, "Filter Days Left", "filter.daysLeft", uom="days", icon="mdi:counter"),
            MilaAppliancePathSensor(self, "Filter Install Date", "filter.installedAt", device_class=SensorDeviceClass.DATE, icon="mdi:calendar-refresh"),
            MilaAppliancePathSensor(self, "Filter Calibrated Date", "filter.calibratedAt", device_class=SensorDeviceClass.DATE, icon="mdi:calendar"),
            MilaAppliancePathSensor(self, "Bedtime Start", "room.bedtime.localStart", icon="mdi:calendar-start"),
            MilaAppliancePathSensor(self, "Bedtime End", "room.bedtime.localEnd", icon="mdi:calendar-end"),
            
            MilaApplianceMeasurementSensor(self, "Air Changes", ApplianceSensorKind.Ach, uom = "cph", icon="mdi:cloud-refresh", precision=1),
            MilaApplianceMeasurementSensor(self, "Air Quality", ApplianceSensorKind.Aqi, device_class=SensorDeviceClass.AQI),
            MilaApplianceMeasurementSensor(self, "CO", ApplianceSensorKind.Co, device_class=SensorDeviceClass.CO, uom=CONCENTRATION_PARTS_PER_MILLION),
            MilaApplianceMeasurementSensor(self, "CO2", ApplianceSensorKind.Co2, device_class=SensorDeviceClass.CO2, uom=CONCENTRATION_PARTS_PER_MILLION),
            MilaApplianceMeasurementSensor(self, "Fan Speed", ApplianceSensorKind.FanSpeed, uom = "rpm", icon="mdi:fan", precision=1),
            MilaApplianceMeasurementSensor(self, "Humidity", ApplianceSensorKind.Humidity, device_class=SensorDeviceClass.HUMIDITY, uom=PERCENTAGE, precision=1),
            #MilaApplianceMeasurementSensor(self, "Pressure", ApplianceSensorKind.LoadingMg, device_class=SensorDeviceClass.PRESSURE, uom="Unknown"),
            MilaApplianceMeasurementSensor(self, "PM1", ApplianceSensorKind.Pm1, device_class=SensorDeviceClass.PM1, uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            MilaApplianceMeasurementSensor(self, "PM10", ApplianceSensorKind.Pm10, device_class=SensorDeviceClass.PM10, uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            MilaApplianceMeasurementSensor(self, "PM2.5", ApplianceSensorKind.Pm2_5, device_class=SensorDeviceClass.PM25, uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER),
            #MilaApplianceMeasurementSensor(self, "Max Pressure", ApplianceSensorKind.PressureMax, device_class=SensorDeviceClass.PRESSURE, uom="Unknown"),
            #MilaApplianceMeasurementSensor(self, "TTC", ApplianceSensorKind.Ttc, uom = "Unknown"),
            MilaApplianceMeasurementSensor(self, "VOC", ApplianceSensorKind.Voc, device_class=SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS, uom=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, uom_conversion_factor=TVOC_PPB_TO_UGM3),
            MilaApplianceMeasurementSensor(self, "Temperature", ApplianceSensorKind.Temperature, uom=UnitOfTemperature.CELSIUS, device_class=SensorDeviceClass.TEMPERATURE, precision=1),

            MilaSmartModeSwitch(self, SmartModeKind.Quiet, SmartModeKind.Quiet, "mdi:ear-hearing-off"),
            MilaSmartModeSwitch(self, SmartModeKind.Quarantine, SmartModeKind.Quarantine, "mdi:virus"),
            MilaSmartModeSwitch(self, "Child Lock", SmartModeKind.ChildLock, "mdi:lock"),
            MilaSmartModeSwitch(self, SmartModeKind.Housekeeper, SmartModeKind.Housekeeper, "mdi:broom"),
            MilaSmartModeSwitch(self, "Power Saver", SmartModeKind.PowerSaver, "mdi:power"),
            MilaSmartModeSwitch(self, SmartModeKind.Sleep, SmartModeKind.Sleep, "mdi:sleep"),
            MilaSmartModeSwitch(self, SmartModeKind.Turndown, SmartModeKind.Turndown, "mdi:bed"),
            MilaSmartModeSwitch(self, SmartModeKind.Whitenoise, SmartModeKind.Whitenoise, "mdi:waveform"),

            MilaApplianceFan(self),
            MilaSoundModeSelect(self)
        ]

        return entities

    def _get_software_version(self) -> str:
        return self._device_data["state.firmware.version"]
