import asyncio
import logging
import json

import base64
import hashlib
import html
import json
import math
import os
import re
from typing import Dict
import urllib.parse

from aiohttp import ClientSession, ClientResponse
import aiohttp
from aiohttp.client_exceptions import ClientError, ClientResponseError

import requests
import time

import async_timeout

from .account import Account


# https://www.stefaanlippens.net/oauth-code-flow-pkce.html

AUTH_PROVIDER = "https://id.milacares.com"
REDIRECT_URI  = "milacares://anyurl.com/"
CLIENT_ID = "prod-ui"

BASE_URL = "https://api.milacares.com/mms"
SENSOR_TYPES = ["pm_1.0", "pm_2.5", "pm_10", "tvoc", "coppm", "eco2", "temperature", "humidity"]
# Fan Speed Percentage to RPM mapping:
# SPEED_PERCENT_TO_RPM_MAP = {
#     0: 0,
#     10: 600,
#     20: 740,
#     30: 880,
#     40: 1020,
#     50: 1160,
#     60: 1300,
#     70: 1440,
#     80: 1580,
#     90: 1720,
#     100: 2000,
# }
SPEED_PERCENT_TO_RPM_MAP = [0, 600, 740, 880, 1020, 1160, 1300, 1440, 1580, 1720, 2000]
MAX_FAN_RPM = 2000

_LOGGER = logging.getLogger(__name__)

class MilaException(Exception):
    def __init__(self, status, error_message):
        super(MilaException, self).__init__()
        self.status = status
        self.error_message = error_message

class MilaAPI(object):
    def __init__(
        self, username, password, timeout=10, save_location=None, access_token = None, session: ClientSession = None
    ):
        self.username = username
        self.password = password
        self.session = session
        self.access_token = access_token
        self.save_location = save_location
        self.timeout = timeout
        self.data = Account(self, {})

    async def request(self, method, path, base_url=BASE_URL, data=None, data_key="data", json_response = True, allow_redirects = True, extra_headers = {}, auth_header = True) -> Dict:
        if base_url:
            url = f"{base_url}{path}"
        else:
            url = path

        kwargs = {}
        if data:
            kwargs[data_key] = data

        headers = {}
        if auth_header:
            headers = {
                "Authorization": 'Bearer {}'.format(self.access_token)
            }
        headers.update(extra_headers)

        try:
            with async_timeout.timeout(self.timeout):
                _LOGGER.info(f"{method} {url}")
                resp = await self.session.request(
                    method,
                    url,
                    headers=headers,
                    allow_redirects=allow_redirects,
                    raise_for_status=True,
                    **kwargs,
                )
        except Exception as err:
            _LOGGER.info(err)
            if (resp.status == 401):
                self.refresh_access_token()
                with async_timeout.timeout(self.timeout):
                    try:
                        resp = await self.session.request(
                            method,
                            url,
                            headers=headers,
                            allow_redirects=allow_redirects,
                            raise_for_status=True,
                            **kwargs,
                        )
                    except Exception as err:
                        raise MilaException(resp.status, f"Error with {method} {url}") from err
            else:
                raise MilaException(resp.status, f"Error with {method} {url}")

        if json_response:
            response = await resp.json()
            if response.get("data"):
                return response.get("data")
            else:
                return response
        else:
            return resp

    async def save_response(self, response, name="response"):
        if self.save_location and response:
            if not os.path.isdir(self.save_location):
                os.mkdir(self.save_location)
            name = name.replace("/", "_").replace(".", "_")
            with open(f"{self.save_location}/{name}.json", "w") as file:
                json.dump(response, file, default=lambda o: "not-serializable", indent=4, sort_keys=True)
            file.close()

    async def login(self):
        # PKCE code verifier and challenge
        '''
        We need a code verifier, which is a long enough random alphanumeric string, only to be used "client side". We'll use a simple urandom/base64 trick to generate one:
        '''
        nonce = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')
        state = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')

        code_verifier = base64.urlsafe_b64encode(os.urandom(40)).decode('utf-8')
        code_verifier = re.sub('[^a-zA-Z0-9]+', '', code_verifier)
        code_verifier, len(code_verifier)

        '''
        To create the PKCE code challenge we hash the code verifier with SHA256 and encode the result in URL-safe base64 (without padding)
        '''

        code_challenge = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(code_challenge).decode('utf-8')
        code_challenge = code_challenge.replace('=', '')
        code_challenge, len(code_challenge)

        # Request login page
        '''
        We now have all the pieces for the initial request, which will give us the login page of the authentication provider. Adding the code challenge signals to the OAuth provider that we are expecting the PKCE based flow.
        '''
        _LOGGER.info("GET login page")
        resp = await self.request(
                "get",
                path = "/auth/realms/prod/protocol/openid-connect/auth",
                base_url = AUTH_PROVIDER,
                data = {
                    "response_type": "code",
                    "client_id": CLIENT_ID,
                    "nonce": nonce,
                    "scope": "openid,profile",
                    "redirect_uri": REDIRECT_URI ,
                    "state": state,
                    "code_challenge": code_challenge,
                    "code_challenge_method": "S256",
                },
                data_key = 'params',
                json_response = False,
                auth_header = False
        )

        # _LOGGER.info(f"Login Page {resp.text()}")
        # Parse login page (response)
        '''
        Get cookie data from response headers (requires a bit of manipulation).
        '''
        cookie = resp.headers['Set-Cookie']
        cookie = '; '.join(c.split(';')[0] for c in cookie.split(', '))
        # _LOGGER.info(cookie)

        '''
        Extract the login URL to post to from the page HTML code. Because the the Keycloak login page is straightforward HTML we can get away with some simple regexes.
        '''
        page = await resp.text()
        form_action = html.unescape(re.search('<form\s+.*?\s+action="(.*?)"', page, re.DOTALL).group(1))
        _LOGGER.info(f"Form Action URL: {form_action}")


        # Do the login (aka authenticate)
        '''
        Now, we post the login form with the user we created earlier, passing it the extracted cookie as well.
        '''
        _LOGGER.info("POST login")
        resp = await self.request(
                "post",
                path=form_action,
                base_url = None,
                data = {
                    "username": self.username,
                    "password": self.password,
                },
                extra_headers = {
                    "Cookie": cookie
                },
                json_response = False,
                allow_redirects = False,
                auth_header = False
            )

        '''
        As expected we are forwarded, let's get the redirect URL.
        '''
        _LOGGER.info("Response headers %s" % resp.headers)
        try:
            redirect = resp.headers['Location']
            if not redirect.startswith(REDIRECT_URI):
                _LOGGER.error("Redirect URI not found after login")
                raise
        except Exception as err:
            raise MilaException(401, f"No redirect URI found") from err

        # Extract authorization code from redirect
        '''
        The redirect URL contains the authentication code.
        '''
        query = urllib.parse.urlparse(redirect).query
        redirect_params = urllib.parse.parse_qs(query)
        # _LOGGER.info(redirect_params)

        auth_code = redirect_params['code'][0]
        # _LOGGER.info("Auth Code: %s" % auth_code)

        # Exchange authorization code for an access token
        '''
        We can now exchange the authorization code for an access token. In the normal OAuth authorization flow we should include a static secret here, but instead we provide the code verifier here which acts proof that the initial request was done by us.
        '''
        _LOGGER.info("POST auth code exchange")
        resp = await self.request(
                "post",
                path = "/auth/realms/prod/protocol/openid-connect/token",
                base_url = AUTH_PROVIDER,
                data = {
                    "grant_type": "authorization_code",
                    "client_id": CLIENT_ID,
                    "redirect_uri": REDIRECT_URI ,
                    "code": auth_code,
                    "code_verifier": code_verifier,
                },
                allow_redirects=False,
                auth_header = False
            )

        '''
        In the response we get, among others, the access token and id token:
        '''

        # _LOGGER.info("Auth result %s" % resp)
        self.access_token = resp['access_token']
        # _LOGGER.info("Access Token: %s" % self.access_token)
        self.refresh_token = resp['refresh_token']
        # _LOGGER.info("Refresh Token: %s" % refresh_token)
        # expires_in = resp['expires_in']
        # refresh_expires_in = resp['refresh_expires_in']
        return self.access_token

    async def refresh_access_token(self):
        """
        Use refresh token to get new access token
        """
        resp = await self.request(
                "post",
                path = "/auth/realms/prod/protocol/openid-connect/token",
                base_url = AUTH_PROVIDER,
                data={
                    "refresh_token": self.refresh_token,
                    "grant_type": "refresh_token",
                    "client_id": CLIENT_ID,
                },
                auth_header = False
        )

        '''
        In the response we get, among others, the access token
        '''

        # _LOGGER.info("Auth result %s" % resp)
        self.access_token = resp['access_token']
        # _LOGGER.info("Access Token: %s" % self.access_token)
        self.refresh_token = resp['refresh_token']
        # _LOGGER.info("Refresh Token: %s" % refresh_token)
        # expires_in = resp['expires_in']
        # refresh_expires_in = resp['refresh_expires_in']
        return self.access_token

    async def get_profile(self):
        # Get Profile Information
        resp = await self.request(
                "get",
                path = "/profile"
        )
        return resp

    async def get_devices(self):
        # Appliances Meta
        resp = await self.request(
                "get",
                path = "/appliances/meta",
        )
        return resp

    async def get_modes(self, device_id):
        # Appliance Meta
        resp = await self.request(
                "get",
                path = f"/appliance/{device_id}/config",
            )
        return resp

    async def update(self):
        try:
            account = {}
            devices = list()
            device_list = await self.get_devices()
            for d in device_list:
                device = {}
                device["device"] = d
                device["modes"] = await self.get_modes(d["id"])
                device["sensors"] = await self.get_sensors_data(d["appliance_code"])
                devices.append(device)

            account["profile"] = {}
            account["profile"]["data"] = await self.get_profile()
            account["profile"]["data"]["smart_modes"] = await self.get_smart_modes()
            account["devices"] = {}
            account["devices"]["data"] = devices


            await self.save_response(response=account, name="update_data")
            self.data = Account(self, account)
        except MilaException:
            return self.data
        return self.data

    async def get_sensor_data(self, appliance_code, sensor_name):
        resp = await self.request(
            "get",
            path = f"/sensor/appliance?deviceId={appliance_code}&metric={sensor_name}",
        )
        # _LOGGER.info("Sensor data %s: %s" %(sensor_name, result))
        return resp["meta"]["latest_sensor_value"]["value"]

    async def get_sensors_data(self, appliance_code):
        response_data = {}
        for sensor in SENSOR_TYPES:
            response_data[sensor] = await self.get_sensor_data(appliance_code=appliance_code, sensor_name=sensor)
        return response_data

    # Set Fan Mode to Manual
    async def set_mode_manual(self, appliance_code, fan_speed_percentage):
        _LOGGER.info("Setting the fan mode to manual speed")
        if fan_speed_percentage < 0 or fan_speed_percentage > 100:
            return

        fan_speed = SPEED_PERCENT_TO_RPM_MAP[math.floor(fan_speed_percentage / 10)]

        target_aqi = "10"
        _LOGGER.info(f"Fan Speed: {fan_speed_percentage}%, {fan_speed} RPM")

        extra_headers = {
            "Content-Type": 'application/json'
        }
        payload = {
            "target_aqi_float": target_aqi,
            "fan_rpm_int": fan_speed,
            "enable_display_int": -1
        }
        resp = await self.request(
            "post",
            path = "/appliance/" + appliance_code + "/command/control-mode/manual",
            base_url = BASE_URL,
            extra_headers = extra_headers,
            data = json.dumps(payload)
        )

        # It takes a while for the speed to update to the requested fan speed.
        # The app makes multiple requests to /command/force-data until fan speed matches the requested speed.
        cur_fan_speed = 5000
        retry_count = 0
        max_retries = 5
        while abs(cur_fan_speed - fan_speed) >= 30 and retry_count < max_retries:
            await asyncio.sleep(5)
            resp = await self.request(
                "post",
                path = "/appliance/" + appliance_code + "/command/force-data",
                base_url = BASE_URL,
            )
            _LOGGER.info(f"({retry_count}/{max_retries}): Force Data - Current fan speed", cur_fan_speed)
            cur_fan_speed = resp["speed"]
            retry_count += 1

    async def set_mode_auto(self, appliance_code):
        # Set Fan to Auto
        _LOGGER.info("Setting the fan mode to auto")
        resp = await self.request(
                "post",
                path = "/appliance/" + appliance_code + "/command/control-mode/auto",
                base_url = BASE_URL,
                data = {
                    "enable_display_int": -1
                },
        )
        await asyncio.sleep(10)
        resp = await self.request(
                "post",
                path = "/appliance/" + appliance_code + "/command/force-data",
                base_url = BASE_URL,
            )
        cur_fan_speed = resp["speed"]


    async def get_smart_modes(self):
        # Set Smart Mode to enabled/disable
        return await self.request(
                "get",
                path = f"/smart-modes",
                base_url = BASE_URL
        )

    async def set_smart_mode(self, smart_mode, enabled):
        # Set Smart Mode to enabled/disable
        _LOGGER.info(f"Setting the {smart_mode} to {enabled}")
        payload = {
            "is_enabled": enabled
        }
        return await self.request(
                "patch",
                path = f"/smart-modes/{smart_mode}",
                base_url = BASE_URL,
                data = json.dumps(payload),
                extra_headers = { "Content-Type": 'application/json' }
        )


    async def set_sounds_enabled(self, appliance_code, enabled):
        # Set Smart Mode to enabled/disable
        _LOGGER.info(f"Setting the sounds to {enabled}")
        payload = {
            "enabled": enabled,
            "night_enabled": enabled
        }
        return await self.request(
                "post",
                path = "/appliance/" + appliance_code + "/command/mute-toggle",
                base_url = BASE_URL,
                data = json.dumps(payload),
                extra_headers = { "Content-Type": 'application/json' }
        )


