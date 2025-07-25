"""MobileLink API Client for Generac."""
import json
import logging
from typing import Any
from typing import Mapping

import aiohttp
from bs4 import BeautifulSoup
from dacite import from_dict

from .const import API_BASE
from .const import LOGIN_BASE
from .models import Apparatus
from .models import ApparatusDetail
from .models import Item
from .models import SelfAssertedResponse
from .models import SignInConfig


_LOGGER: logging.Logger = logging.getLogger(__package__)


class InvalidCredentialsException(Exception):
    pass


class SessionExpiredException(Exception):
    pass


def get_setting_json(page: str) -> Mapping[str, Any] | None:
    for line in page.splitlines():
        if line.startswith("var SETTINGS = ") and line.endswith(";"):
            return json.loads(line.removeprefix("var SETTINGS = ").removesuffix(";"))


class GeneracApiClient:
    def __init__(
        self, username: str = None, password: str = None, session: aiohttp.ClientSession = None,
        cookies: str = None, auth_token: str = None
    ) -> None:
        """MobileLink API Client for Generac."""
        self._username = username
        self._password = password
        self._session = session
        self._cookies = cookies
        self._auth_token = auth_token
        self._logged_in = False
        self.csrf = ""
        
        # Determine authentication method
        if auth_token:
            self._auth_method = "token"
            self._headers = {
                "Host": "app.mobilelinkgen.com",
                "Accept": "application/json",
                "Authorization": f"Bearer {auth_token}",
                "User-Agent": "mobilelink/75633 CFNetwork/3826.600.41 Darwin/24.6.0",
                "Accept-Language": "en-US,en;q=0.9"
            }
            self._logged_in = True  # JWT tokens are pre-authenticated
        elif cookies:
            self._auth_method = "cookies"
            self._headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Cookie": cookies
            }
        else:
            self._auth_method = "username_password"
            self._headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive"
            }

    async def async_get_data(self) -> dict[str, Item] | None:
        """Get data from the API."""
        try:
            if not self._logged_in:
                await self.login()
                self._logged_in = True
        except SessionExpiredException:
            self._logged_in = False
            return await self.async_get_data()
        return await self.get_generator_data()

    async def get_generator_data(self):
        # Try v5 API first (mobile app version), fallback to v2
        apparatuses = await self.get_endpoint("/v5/Apparatus/list")
        if apparatuses is None:
            # Fallback to v2 API  
            apparatuses = await self.get_endpoint("/v2/Apparatus/list")
        if apparatuses is None:
            _LOGGER.debug("Could not decode apparatuses response")
            return None
        if not isinstance(apparatuses, list):
            _LOGGER.error("Expected list from /v2/Apparatus/list got %s", apparatuses)

        data: dict[str, Item] = {}
        for apparatus in apparatuses:
            apparatus = from_dict(Apparatus, apparatus)
            if apparatus.type != 0:
                _LOGGER.debug(
                    "Unknown apparatus type %s %s", apparatus.type, apparatus.name
                )
                continue
            # Try v5 apparatus details first, fallback to v1
            detail_json = await self.get_endpoint(
                f"/v5/Apparatus/{apparatus.apparatusId}"
            )
            if detail_json is None:
                # Fallback to v1 API
                detail_json = await self.get_endpoint(
                    f"/v1/Apparatus/details/{apparatus.apparatusId}"
                )
            if detail_json is None:
                _LOGGER.debug(
                    f"Could not decode respose from /v1/Apparatus/details/{apparatus.apparatusId}"
                )
                continue
            detail = from_dict(ApparatusDetail, detail_json)
            data[str(apparatus.apparatusId)] = Item(apparatus, detail)
        return data

    async def get_endpoint(self, endpoint: str):
        try:
            headers = {**self._headers}
            if self.csrf:
                headers["X-Csrf-Token"] = self.csrf
                
            response = await self._session.get(
                API_BASE + endpoint, headers=headers
            )
            if response.status == 204:
                # no data
                return None

            if response.status != 200:
                raise SessionExpiredException(
                    "API returned status code: %s " % response.status
                )

            data = await response.json()
            _LOGGER.debug("getEndpoint %s", json.dumps(data))
            return data
        except SessionExpiredException:
            raise
        except Exception as ex:
            raise IOError() from ex

    async def login(self) -> None:
        """Login to API"""
        # Skip login for JWT token auth (already authenticated)
        if self._auth_method == "token":
            return
            
        # For cookies auth, test if cookies are still valid
        if self._auth_method == "cookies":
            try:
                test_response = await self.get_endpoint("/v5/Apparatus/list")
                if test_response is not None:
                    return  # Cookies are valid
            except SessionExpiredException:
                pass  # Cookies expired, fall through to username/password
        
        # Original username/password login flow
        if not self._username or not self._password:
            raise InvalidCredentialsException("Username and password required for login")
            
        headers = {**self._headers}
        login_response = await (
            await self._session.get(
                f"{API_BASE}/Auth/SignIn?email={self._username}",
                headers=headers,
                allow_redirects=True
            )
        ).text()

        if await self.submit_form(login_response):
            return

        parse_settings = get_setting_json(login_response)
        if parse_settings is None:
            _LOGGER.debug(
                "Unable to find csrf token in login page:\n%s", login_response
            )
            raise IOError("Unable to find csrf token in login page")
        sign_in_config = from_dict(SignInConfig, parse_settings)

        form_data = aiohttp.FormData()
        form_data.add_field("request_type", "RESPONSE")
        form_data.add_field("signInName", self._username)
        form_data.add_field("password", self._password)
        if sign_in_config.csrf is None or sign_in_config.transId is None:
            raise IOError(
                "Missing csrf and/or transId in sign in config %s", sign_in_config
            )
        self.csrf = sign_in_config.csrf

        headers = {**self._headers}
        headers["X-Csrf-Token"] = sign_in_config.csrf

        self_asserted_response = await self._session.post(
            f"{LOGIN_BASE}/SelfAsserted",
            headers=headers,
            params={
                "tx": "StateProperties=" + sign_in_config.transId,
                "p": "B2C_1A_SignUpOrSigninOnline",
            },
            data=form_data,
        )

        if self_asserted_response.status != 200:
            raise IOError(
                f"SelfAsserted: Bad response status: {self_asserted_response.status}"
            )
        satxt = await self_asserted_response.text()

        sa = from_dict(SelfAssertedResponse, json.loads(satxt))

        if sa.status != "200":
            raise InvalidCredentialsException()

        confirmed_response = await self._session.get(
            f"{LOGIN_BASE}/api/CombinedSigninAndSignup/confirmed",
            headers=headers,
            params={
                "csrf_token": sign_in_config.csrf,
                "tx": "StateProperties=" + sign_in_config.transId,
                "p": "B2C_1A_SignUpOrSigninOnline",
            },
        )

        if confirmed_response.status != 200:
            raise IOError(
                f"CombinedSigninAndSignup: Bad response status: {confirmed_response.status}"
            )

        loginString = await confirmed_response.text()
        if not await self.submit_form(loginString):
            raise IOError("Error parsing HTML submit form")

    async def submit_form(self, response: str) -> bool:
        login_page = BeautifulSoup(response, features="html.parser")
        form = login_page.select("form")
        login_state = login_page.select("input[name=state]")
        login_code = login_page.select("input[name=code]")

        if len(form) == 0 or len(login_state) == 0 or len(login_code) == 0:
            _LOGGER.info("Could not load login page")
            return False

        form = form[0]
        login_state = login_state[0]
        login_code = login_code[0]

        action = form.attrs["action"]

        form_data = aiohttp.FormData()
        form_data.add_field("state", login_state.attrs["value"])
        form_data.add_field("code", login_code.attrs["value"])

        login_response = await self._session.post(action, data=form_data, headers=self._headers)

        if login_response.status != 200:
            raise IOError(f"Bad api login response: {login_response.status}")
        return True
