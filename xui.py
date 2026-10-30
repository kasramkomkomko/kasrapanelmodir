import json
import secrets
import time
import uuid
from urllib.parse import urlparse

import httpx

from .base import GB, Adapter, Created, PanelError, Usage, check_resp, new_expire


class XUI(Adapter):
    """3x-ui / X-UI (سنایی و ثنایی)"""
    ptype = "3xui"

    async def _client(self) -> httpx.AsyncClient:
        c = httpx.AsyncClient(base_url=self.url, timeout=20, verify=False)
        try:
            r = await c.post("/login", data={"username": self.username, "password": self.password})
            if not r.json().get("success"):
                raise PanelError("ورود ناموفق")
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

    async def _inbound(self, c):
        iid = self.extra.get("inbound_id")
        if iid:
            return check_resp(await c.get(f"/panel/api/inbounds/get/{iid}")).json()["obj"]
        lst = check_resp(await c.get("/panel/api/inbounds/list")).json().get("obj") or []
        lst = [i for i in lst if i.get("enable")]
        if not lst:
            raise PanelError("هیچ اینباند فعالی در پنل نیست")
        return lst[0]

    async def _sub_base(self, c) -> str:
        if self.extra.get("sub_base"):
            b = self.extra["sub_base"]
            return b if b.endswith("/") else b + "/"
        try:
            o = (await c.post("/panel/setting/all")).json().get("obj") or {}
            if o.get("subURI"):
                b = o["subURI"]
            else:
                host = o.get("subDomain") or urlparse(self.url).hostname
                scheme = "https" if o.get("subCertFile") else "http"
                b = f"{scheme}://{host}:{o.get('subPort')}{o.get('subPath') or '/sub/'}"
            return b if b.endswith("/") else b + "/"
        except Exception:
            return ""

    async def create_user(self, name, days, gb):
        c = await self._client()
        try:
            ib = await self._inbound(c)
            proto = ib.get("protocol", "vless")
            cid = secrets.token_urlsafe(12) if proto in ("trojan", "shadowsocks") else str(uuid.uuid4())
            sub_id = secrets.token_hex(8)
            cl = {
                "email": name, "limitIp": 0, "totalGB": gb * GB,
                "expiryTime": (int(time.time()) + days * 86400) * 1000 if days > 0 else 0,
                "enable": True, "subId": sub_id, "tgId": "", "comment": "", "reset": 0,
            }
            if proto in ("trojan", "shadowsocks"):
                cl["password"] = cid
            else:
                cl["id"] = cid
                cl["flow"] = ""
            form = {"id": ib["id"], "settings": json.dumps({"clients": [cl]})}
            j = check_resp(await c.post("/panel/api/inbounds/addClient", data=form)).json()
            if not j.get("success"):
                raise PanelError(str(j.get("msg", "خطا در ساخت کاربر")))
            base = await self._sub_base(c)
            return Created(name, base + sub_id if base else "", {"cid": cid, "inbound_id": ib["id"], "sub_id": sub_id})
        finally:
            await c.aclose()

    async def usage(self, name, ref):
        c = await self._client()
        try:
            o = check_resp(await c.get(f"/panel/api/inbounds/getClientTraffics/{name}")).json().get("obj") or {}
            return Usage((o.get("up") or 0) + (o.get("down") or 0), o.get("total") or 0, int((o.get("expiryTime") or 0) / 1000))
        finally:
            await c.aclose()

    async def renew(self, name, ref, days, gb):
        c = await self._client()
        try:
            iid = ref["inbound_id"]
            ib = check_resp(await c.get(f"/panel/api/inbounds/get/{iid}")).json()["obj"]
            clients = json.loads(ib["settings"]).get("clients", [])
            cl = next((x for x in clients if x.get("email") == name), None)
            if not cl:
                raise PanelError("کاربر در اینباند پیدا نشد")
            cur = int((cl.get("expiryTime") or 0) / 1000)
            cl["totalGB"] = gb * GB
            cl["expiryTime"] = new_expire(cur, days) * 1000 if days > 0 else 0
            cl["enable"] = True
            form = {"id": iid, "settings": json.dumps({"clients": [cl]})}
            j = check_resp(await c.post(f"/panel/api/inbounds/updateClient/{ref['cid']}", data=form)).json()
            if not j.get("success"):
                raise PanelError(str(j.get("msg", "خطا در تمدید")))
            await c.post(f"/panel/api/inbounds/{iid}/resetClientTraffic/{name}")
        finally:
            await c.aclose()

    async def delete(self, name, ref):
        c = await self._client()
        try:
            check_resp(await c.post(f"/panel/api/inbounds/{ref['inbound_id']}/delClient/{ref['cid']}"))
        finally:
            await c.aclose()
