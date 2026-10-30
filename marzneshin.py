from datetime import datetime, timedelta, timezone

import httpx

from .base import GB, Adapter, Created, PanelError, Usage, check_resp


def _iso(days: int):
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def _parse(s) -> int:
    if not s:
        return 0
    try:
        return int(datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp())
    except Exception:
        return 0


class Marzneshin(Adapter):
    ptype = "marzneshin"

    async def _client(self) -> httpx.AsyncClient:
        c = httpx.AsyncClient(base_url=self.url, timeout=20, verify=False)
        try:
            r = await c.post("/api/admins/token", data={"username": self.username, "password": self.password})
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
            sv = check_resp(await c.get("/api/services")).json()
            ids = [s["id"] for s in (sv.get("items", sv) if isinstance(sv, dict) else sv)]
            body = {
                "username": name,
                "service_ids": ids,
                "expire_strategy": "fixed_date" if days > 0 else "never",
                "data_limit": gb * GB,
                "data_limit_reset_strategy": "no_reset",
            }
            if days > 0:
                body["expire_date"] = _iso(days)
            j = check_resp(await c.post("/api/users", json=body)).json()
            sub = j.get("subscription_url", "")
            if sub.startswith("/"):
                sub = self.url + sub
            return Created(name, sub, {})
        finally:
            await c.aclose()

    async def usage(self, name, ref):
        c = await self._client()
        try:
            j = check_resp(await c.get(f"/api/users/{name}")).json()
            return Usage(j.get("used_traffic") or 0, j.get("data_limit") or 0, _parse(j.get("expire_date")))
        finally:
            await c.aclose()

    async def renew(self, name, ref, days, gb):
        c = await self._client()
        try:
            cur = check_resp(await c.get(f"/api/users/{name}")).json()
            start = max(_parse(cur.get("expire_date")), int(datetime.now(timezone.utc).timestamp()))
            body = {
                "expire_strategy": "fixed_date" if days > 0 else "never",
                "data_limit": gb * GB,
                "service_ids": cur.get("service_ids", []),
            }
            if days > 0:
                body["expire_date"] = datetime.fromtimestamp(start + days * 86400, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
            check_resp(await c.put(f"/api/users/{name}", json=body))
            await c.post(f"/api/users/{name}/reset")
            await c.post(f"/api/users/{name}/enable")
        finally:
            await c.aclose()

    async def delete(self, name, ref):
        c = await self._client()
        try:
            check_resp(await c.delete(f"/api/users/{name}"))
        finally:
            await c.aclose()
