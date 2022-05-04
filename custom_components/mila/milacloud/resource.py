"""Milacares API"""
from .const import URL_ACCOUNT


class Resource(object):
    def __init__(self, api, device, data):
        self.api = api
        self.device = device
        self.data = data

    @property
    def id(self):
        return self.device["id"] if self.is_device else None

    @property
    def is_account(self):
        return self.__class__.__name__ == "Account"

    @property
    def is_device(self):
        return self.__class__.__name__ == "Device"
