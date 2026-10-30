import re

import httpx

from .base import GB, Adapter, Created, PanelError, Usage, check_resp, expire_ts, new_expire


class Marzban(Adapter):
    """Marzban و فورک‌هایش (PasarGuard و ...)"""
    ptype = "marzban"
    token_path = "/api/admin/token"

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.url = re.sub(r"/dashboard/?$", "", self.url)

    async def _client(self) -> httpx.AsyncClient:
        c = httpx.AsyncClient(base_url=self.url, timeout=20, verify=False)
        try:
            r = await c.post(self.token_path, data={"username": self.username, "password": self.password})
            if r.status_code != 200 or "access_token" not in r.text:
                raise PanelError("ورود ناموفق")
            c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
            return c
        except Exception:
            await c.aclose()
            raise

    async def check(self) -> bool:
        try:
            c = await self._client()
            await c.aclose()
            return True
        except Exception:
            return False

    async def create_user(self, name, days, gb):
        c = await self._client()
        try:
            ib = check_resp(await c.get("/api/inbounds")).json()
            payload = {
                "username": name,
                "proxies": {p: {} for p in ib},
                "inbounds": {p: [i["tag"] for i in lst] for p, lst in ib.items()},
                "expire": expire_ts(days),
                "data_limit": gb * GB,
                "data_limit_reset_strategy": "no_reset",
                "status": "active",
            }
            j = check_resp(await c.post("/api/user", json=payload)).json()
            sub = j.get("subscription_url", "")
            if sub.startswith("/"):
                sub = self.url + sub
            return Created(name, sub, {})
        finally:
            await c.aclose()

    async def usage(self, name, ref):
        c = await self._client()
        try:
            j = check_resp(await c.get(f"/api/user/{name}")).json()
            return Usage(j.get("used_traffic") or 0, j.get("data_limit") or 0, j.get("expire") or 0)
        finally:
            await c.aclose()

    async def renew(self, name, ref, days, gb):
        c = await self._client()
        try:
            j = check_resp(await c.get(f"/api/user/{name}")).json()
            body = {"expire": new_expire(j.get("expire") or 0, days), "data_limit": gb * GB, "status": "active"}
            check_resp(await c.put(f"/api/user/{name}", json=body))
            check_resp(await c.post(f"/api/user/{name}/reset"))
        finally:
            await c.aclose()

    async def delete(self, name, ref):
        c = await self._client()
        try:
            check_resp(await c.delete(f"/api/user/{name}"))
        finally:
            await c.aclose()
