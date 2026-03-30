from typing import Any, Dict
from urllib.parse import quote

import requests

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _headers() -> Dict[str, str]:
    return {
        "host": "q.qq.com",
        "accept": "application/json",
        "content-type": "application/json",
        "user-agent": CHROME_UA,
    }


def _get_json(resp: requests.Response) -> Dict[str, Any]:
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected JSON payload (expected object).")
    return data


class QQQRCodeLoginService:
    @staticmethod
    def request_login_code() -> Dict[str, str]:
        """
        Returns:
          {
            "code": str,
            "qrImageUrl": str
          }
        """
        url = "https://q.qq.com/ide/devtoolAuth/GetLoginCode"
        r = requests.get(url, headers=_headers(), timeout=30)
        payload = _get_json(r)

        code = str(payload.get("data", {}).get("code", ""))
        api_code = payload.get("code", None)
        if api_code is None or int(api_code) != 0:
            raise RuntimeError("GetLoginCode failed (unexpected response code).")
        if not code:
            raise RuntimeError("GetLoginCode failed (missing data.code).")

        qr_url = f"https://h5.qzone.qq.com/qqq/code/{code}?_proxy=1&from=ide"
        qr_image_url = (
            "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data="
            + quote(qr_url, safe="")
        )

        return {"code": code, "qrImageUrl": qr_image_url}

    @staticmethod
    def query_status(code: str) -> Dict[str, str]:
        """
        Returns:
          - state=wait|used|ok|error
          - if ok: uin
          - if error: msg
        """
        url = "https://q.qq.com/ide/devtoolAuth/syncScanSateGetTicket"
        params = {"code": code}
        r = requests.get(url, headers=_headers(), params=params, timeout=30)

        if r.status_code != 200:
            return {"state": "error", "msg": "status query network error"}

        payload = _get_json(r)
        res_code = int(payload.get("code", 0))
        data = payload.get("data", {}) if isinstance(payload.get("data", {}), dict) else {}

        if res_code == 0:
            if int(data.get("ok", 0)) != 1:
                return {"state": "wait"}
            return {
                "state": "ok",
                "uin": str(data.get("uin", "") or ""),
            }

        if res_code == -10003:
            return {"state": "used"}

        return {"state": "error", "msg": f"code={res_code}"}

