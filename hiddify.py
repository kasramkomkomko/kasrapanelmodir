import time
from datetime import datetime
from urllib.parse import urlparse

import httpx

from .base import Adapter, Created, PanelError, Usage, check_resp


class Hiddify(Adapter):
    """هیدیفای: آدرس = https://domain/PROXYPATH ، رمز = API Key (UUID ادمین)"""
    ptype = "hiddify"

    def _c(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=20, verify=False, headers={"Hiddify-API-Key": self.password})

    @property
    def api(self):
        return self.url + "/api/v2/admin"

    async def check(self) -> bool:
        if not urlparse(self.url).path.strip("/"):
            return False
        try:
            async with self._c() as c:
                r = await c.get(self.api + "/me/")
                return r.status_code == 200 and isinstance(r.json(), dict)
        except Exception:
            return False

    async def create_user(self, name, days, gb):
        async with self._c() as c:
            body = {"name": name, "usage_limit_GB": gb or 1000, "package_days": days or 3650,
                    "mode": "no_reset", "enable": True, "comment": "shopbot"}
            j = check_resp(await c.post(self.api + "/user/", json=body)).json()
            uid = j.get("uuid")
            if not uid:
                raise PanelError("پاسخ نامعتبر از هیدیفای")
            return Created(name, f"{self.url}/{uid}/", {"uuid": uid})

    async def usage(self, name, ref):
        async with self._c() as c:
            j = check_resp(await c.get(f"{self.api}/user/{ref['uuid']}/")).json()
            used = int((j.get("current_usage_GB") or 0) * 1024 ** 3)
            total = int((j.get("usage_limit_GB") or 0) * 1024 ** 3)
            days = j.get("package_days") or 0
            try:
                start = int(datetime.strptime(j["start_date"], "%Y-%m-%d").timestamp()) if j.get("start_date") else int(time.time())
            except Exception:
                start = int(time.time())
            return Usage(used, total, start + days * 86400)

    async def renew(self, name, ref, days, gb):
        async with self._c() as c:
            body = {"package_days": days or 3650, "usage_limit_GB": gb or 1000,
                    "current_usage_GB": 0, "start_date": None, "enable": True}
            check_resp(await c.patch(f"{self.api}/user/{ref['uuid']}/", json=body))

    async def delete(self, name, ref):
        async with self._c() as c:
            check_resp(await c.delete(f"{self.api}/user/{ref['uuid']}/"))
