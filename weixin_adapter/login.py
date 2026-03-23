"""Weixin Login - QR码登录相关功能。

提供二维码获取、状态轮询和交互式登录功能。
"""

import asyncio
import io
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from weixin_adapter import constants
from weixin_adapter.utils import ensure_trailing_slash


async def fetch_bot_qrcode(
    api_base_url: str,
    bot_type: str = "3",
    *,
    sk_route_tag: Optional[str] = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """GET ilink/bot/get_bot_qrcode — returns JSON with qrcode, qrcode_img_content.

    Args:
        api_base_url: API基础URL，如 https://ilinkai.weixin.qq.com
        bot_type: 机器人类型，默认 "3"
        sk_route_tag: 可选的路由标签
        timeout: 请求超时时间(秒)

    Returns:
        包含 qrcode 和 qrcode_img_content 的响应字典
    """
    base = ensure_trailing_slash(api_base_url)
    url = f"{base}ilink/bot/get_bot_qrcode?bot_type={bot_type}"
    headers: dict[str, str] = {}
    if sk_route_tag:
        headers["SKRouteTag"] = sk_route_tag
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.get(url, headers=headers)
        r.raise_for_status()
        return r.json()


async def poll_qrcode_status(
    api_base_url: str,
    qrcode: str,
    *,
    sk_route_tag: Optional[str] = None,
    long_poll_timeout_ms: int = constants.QR_STATUS_LONG_POLL_MS,
) -> dict[str, Any]:
    """GET ilink/bot/get_qrcode_status — long-poll; may return status wait/scaned/confirmed/expired.

    Args:
        api_base_url: API基础URL
        qrcode: 二维码标识
        sk_route_tag: 可选的路由标签
        long_poll_timeout_ms: 长轮询超时时间(毫秒)

    Returns:
        包含 status 的响应字典，status 可能为 wait/scaned/confirmed/expired
    """
    base = ensure_trailing_slash(api_base_url)
    url = f"{base}ilink/bot/get_qrcode_status?qrcode={qrcode}"
    headers = {"iLink-App-ClientVersion": "1"}
    if sk_route_tag:
        headers["SKRouteTag"] = sk_route_tag

    timeout_sec = long_poll_timeout_ms / 1000.0 + 5.0
    async with httpx.AsyncClient(timeout=timeout_sec) as client:
        try:
            r = await client.get(url, headers=headers, timeout=long_poll_timeout_ms / 1000.0)
            r.raise_for_status()
            return r.json()
        except httpx.TimeoutException:
            return {"status": "wait"}


def qr_payload_for_terminal(qr_response: dict[str, Any]) -> str:
    """String to embed in a scannable terminal QR."""
    img = qr_response.get("qrcode_img_content")
    if isinstance(img, str) and img.strip():
        return img.strip()
    raw = qr_response.get("qrcode")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return ""


def print_weixin_qr_terminal(payload: str) -> None:
    """Render a QR code as ASCII to the console (requires ``qrcode`` package)."""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except ImportError:
        msg = "[Install qrcode: pip install qrcode]"
        print(msg, payload, sep="\n", file=sys.stderr)
        return

    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M, box_size=1, border=1)
    qr.add_data(payload)
    qr.make(fit=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        qr.print_ascii(invert=True)
    text = buf.getvalue()
    print(text)


class LoginResult:
    """微信登录结果"""

    def __init__(
        self,
        bot_token: str,
        base_url: str,
        account_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.bot_token = bot_token
        self.base_url = base_url
        self.account_id = account_id
        self.user_id = user_id


class WeixinLogin:
    """微信QR码登录处理器

    提供交互式微信登录功能，支持二维码获取、状态轮询和登录完成回调。
    """

    def __init__(
        self,
        api_base_url: str = "https://ilinkai.weixin.qq.com",
        bot_type: str = "3",
        sk_route_tag: Optional[str] = None,
        on_message: Optional[Callable[[str], None]] = None,
    ):
        """初始化登录处理器

        Args:
            api_base_url: API基础URL
            bot_type: 机器人类型
            sk_route_tag: 可选的路由标签
            on_message: 消息回调函数
        """
        self.api_base_url = api_base_url
        self.bot_type = bot_type
        self.sk_route_tag = sk_route_tag
        self.on_message = on_message or (lambda msg: print(msg))

    @staticmethod
    def _qr_payload_for_terminal_static(qr_response: dict[str, Any]) -> str:
        """获取二维码payload的静态方法版本"""
        return qr_payload_for_terminal(qr_response)

    def _log(self, message: str) -> None:
        """输出日志消息"""
        self.on_message(message)

    async def login(
        self,
        login_timeout_s: float = constants.DEFAULT_QR_LOGIN_TIMEOUT_S,
    ) -> LoginResult:
        """执行交互式登录

        Args:
            login_timeout_s: 登录超时时间(秒)

        Returns:
            LoginResult 包含登录成功后获取的凭证信息

        Raises:
            RuntimeError: 登录失败时抛出
            TimeoutError: 登录超时时抛出
        """
        self._log("[Weixin] 正在获取登录二维码...")

        qr_data = await fetch_bot_qrcode(
            self.api_base_url,
            self.bot_type,
            sk_route_tag=self.sk_route_tag,
        )

        qrcode_ticket = str(qr_data.get("qrcode") or "").strip()
        display_payload = qr_payload_for_terminal(qr_data)

        if not qrcode_ticket:
            raise RuntimeError("get_bot_qrcode: 响应缺少 qrcode")
        if not display_payload:
            display_payload = qrcode_ticket

        self._log("\n请使用微信扫描下方二维码完成 ClawBot 绑定：\n")
        print_weixin_qr_terminal(display_payload)

        if display_payload.startswith("http"):
            self._log(f"\n若二维码显示异常，可在浏览器打开:\n{display_payload}\n")

        deadline = time.time() + max(login_timeout_s, 1.0)
        scanned_printed = False
        qr_refresh_count = 1

        while time.time() < deadline:
            try:
                status = await poll_qrcode_status(
                    self.api_base_url,
                    qrcode_ticket,
                    sk_route_tag=self.sk_route_tag,
                )
                st = str(status.get("status") or "")

                if st == "confirmed":
                    token = status.get("bot_token")
                    if not token or not str(token).strip():
                        raise RuntimeError("登录已确认但服务器未返回 bot_token")

                    bot_id = status.get("ilink_bot_id")
                    baseurl = str(status.get("baseurl") or "").strip().rstrip("/")
                    uid = status.get("ilink_user_id")

                    self._log(f"\n登录成功! bot_token 已获取。\n")
                    if uid:
                        self._log(f"用户ID: {uid}")

                    return LoginResult(
                        bot_token=str(token).strip(),
                        base_url=baseurl or self.api_base_url,
                        account_id=str(bot_id).strip() if bot_id else None,
                        user_id=str(uid).strip() if uid else None,
                    )

                if st == "expired":
                    qr_refresh_count += 1
                    if qr_refresh_count > constants.MAX_QR_REFRESH_COUNT:
                        raise RuntimeError("二维码多次过期，请重新运行再试")

                    self._log(f"\n二维码已过期，正在刷新 ({qr_refresh_count}/{constants.MAX_QR_REFRESH_COUNT})...\n")
                    qr_data = await fetch_bot_qrcode(
                        self.api_base_url,
                        self.bot_type,
                        sk_route_tag=self.sk_route_tag,
                    )
                    qrcode_ticket = str(qr_data.get("qrcode") or "").strip()
                    display_payload = qr_payload_for_terminal(qr_data) or qrcode_ticket
                    print_weixin_qr_terminal(display_payload)
                    scanned_printed = False

                elif st == "scaned" and not scanned_printed:
                    self._log("\n已扫码，请在微信上确认登录...\n")
                    scanned_printed = True

            except httpx.HTTPStatusError as e:
                raise RuntimeError(f"微信登录 HTTP 错误: {e.response.status_code}") from e

            await asyncio.sleep(1.0)

        raise TimeoutError("微信登录超时，请重试")
