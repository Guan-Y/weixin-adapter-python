"""Weixin Client - 微信iLink机器人客户端核心模块。

提供消息接收、发送和事件回调功能。
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx

from weixin_adapter import constants
from weixin_adapter.utils import (
    ensure_trailing_slash,
    markdown_to_plain_text,
    body_from_item_list,
    random_wechat_uin,
)


logger = logging.getLogger(__name__)


@dataclass
class WeixinConfig:
    """微信客户端配置

    Attributes:
        bot_token: 机器人Token，从QR登录获取
        base_url: API基础URL，如 https://ilinkai.weixin.qq.com
        account_id: 机器人账户ID
        sk_route_tag: 可选的路由标签
        channel_version: 渠道版本号
        get_updates_buf_path: 可选的消息同步缓冲区文件路径
        long_poll_timeout_ms: 长轮询超时时间(毫秒)
    """
    bot_token: str
    base_url: str
    account_id: str = ""
    sk_route_tag: Optional[str] = None
    channel_version: str = "1.0.2"
    get_updates_buf_path: Optional[str] = None
    long_poll_timeout_ms: int = constants.DEFAULT_LONG_POLL_TIMEOUT_MS


class WeixinClient:
    """微信iLink机器人客户端

    提供消息轮询、发送和事件回调功能。
    """

    def __init__(
        self,
        config: WeixinConfig,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """初始化微信客户端

        Args:
            config: 客户端配置
            on_message: 收到消息时的回调，参数为原始消息字典
            on_error: 发生错误时的回调
        """
        self.config = config
        self._on_message = on_message
        self._on_error = on_error

        self._client: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self._running = False

        self._context_tokens: Dict[str, str] = {}
        self._pause_until_mono: Optional[float] = None
        self._consecutive_failures = 0

    def _sync_buf_file(self) -> Path:
        """获取同步缓冲区文件路径"""
        raw = (self.config.get_updates_buf_path or "").strip()
        if raw:
            return Path(raw).expanduser()

        if self.config.account_id:
            p = Path.home() / ".weixin_adapter" / "weixin" / f"{self.config.account_id}_get_updates.buf"
            p.parent.mkdir(parents=True, exist_ok=True)
            return p
        return Path.home() / ".weixin_adapter" / "weixin" / "get_updates.buf"

    def _load_get_updates_buf(self) -> str:
        """加载同步缓冲区"""
        path = self._sync_buf_file()
        try:
            if path.exists():
                return path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("Weixin: could not read sync buf {}: {}", path, e)
        return ""

    def _save_get_updates_buf(self, buf: str) -> None:
        """保存同步缓冲区"""
        if not buf:
            return
        path = self._sync_buf_file()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(buf, encoding="utf-8")
        except OSError as e:
            logger.warning("Weixin: could not write sync buf {}: {}", path, e)

    def _base_info(self) -> Dict[str, Any]:
        """获取基础信息"""
        return {"channel_version": self.config.channel_version or "1.0.2"}

    def _build_headers(self, body: bytes, *, with_token: bool) -> Dict[str, str]:
        """构建请求头"""
        headers: Dict[str, str] = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body)),
            "X-WECHAT-UIN": random_wechat_uin(),
        }
        tok = (self.config.bot_token or "").strip()
        if with_token and tok:
            headers["Authorization"] = f"Bearer {tok}"
        tag = (self.config.sk_route_tag or "").strip()
        if tag:
            headers["SKRouteTag"] = tag
        return headers

    def _session_paused(self) -> bool:
        """检查会话是否已暂停"""
        if self._pause_until_mono is None:
            return False
        if time.monotonic() >= self._pause_until_mono:
            self._pause_until_mono = None
            return False
        return True

    def _pause_session(self) -> None:
        """暂停会话"""
        self._pause_until_mono = time.monotonic() + constants.SESSION_PAUSE_MS / 1000.0
        logger.error(
            "Weixin: session expired (errcode %s), pausing API calls for %d min",
            constants.SESSION_EXPIRED_ERRCODE,
            constants.SESSION_PAUSE_MS // 60_000,
        )

    async def _post_ilink(
        self,
        endpoint: str,
        payload: Dict[str, Any],
        timeout: float,
    ) -> Dict[str, Any]:
        """发送POST请求到iLink API"""
        if self._client is None:
            raise RuntimeError("Weixin HTTP client not started")
        if self._session_paused():
            raise RuntimeError("Weixin session paused after expiry; wait or re-login")

        base = ensure_trailing_slash(self.config.base_url.strip())
        url = f"{base}{endpoint.lstrip('/')}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._build_headers(body, with_token=True)

        r = await self._client.post(url, content=body, headers=headers, timeout=timeout)
        text = r.text

        if not r.is_success:
            logger.error("Weixin POST %s -> %s %s", endpoint, r.status_code, text[:500])
            r.raise_for_status()

        try:
            return json.loads(text) if text else {}
        except json.JSONDecodeError:
            logger.error("Weixin POST %s: invalid JSON %s", endpoint, text[:300])
            return {}

    async def get_updates_once(
        self,
        get_updates_buf: str,
        timeout_ms: int,
    ) -> Dict[str, Any]:
        """POST ilink/bot/getupdates. On client timeout returns empty msgs."""
        if self._client is None:
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}

        base = ensure_trailing_slash(self.config.base_url.strip())
        url = f"{base}ilink/bot/getupdates"
        payload = {"get_updates_buf": get_updates_buf or "", "base_info": self._base_info()}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = self._build_headers(body, with_token=True)

        timeout_sec = max(timeout_ms / 1000.0, 1.0) + 5.0
        try:
            r = await self._client.post(url, content=body, headers=headers, timeout=timeout_sec)
            text = r.text
            if not r.is_success:
                logger.error("Weixin getUpdates HTTP %s %s", r.status_code, text[:500])
                r.raise_for_status()
            return json.loads(text) if text else {}
        except httpx.TimeoutException:
            logger.debug("Weixin getUpdates client timeout after %dms", timeout_ms)
            return {"ret": 0, "msgs": [], "get_updates_buf": get_updates_buf}
        except Exception as e:
            logger.error("Weixin getUpdates error: %s", e)
            raise

    async def send_text_message(
        self,
        to_user_id: str,
        text: str,
        context_token: str,
    ) -> None:
        """POST ilink/bot/sendmessage — 发送文本消息

        Args:
            to_user_id: 接收者用户ID
            text: 消息文本
            context_token: 上下文Token，用于关联会话
        """
        if not context_token:
            raise ValueError("context_token is required for Weixin sendmessage")

        plain = markdown_to_plain_text(text)
        if not plain.strip():
            return

        chunks: List[str] = []
        if len(plain) <= constants.TEXT_CHUNK_LIMIT:
            chunks = [plain]
        else:
            for i in range(0, len(plain), constants.TEXT_CHUNK_LIMIT):
                chunks.append(plain[i : i + constants.TEXT_CHUNK_LIMIT])

        for part in chunks:
            client_id = f"weixin-adapter-{uuid.uuid4().hex[:16]}"
            item_list: List[Dict[str, Any]] = []
            if part:
                item_list.append({"type": constants.MESSAGE_ITEM_TEXT, "text_item": {"text": part}})

            msg_body: Dict[str, Any] = {
                "msg": {
                    "from_user_id": "",
                    "to_user_id": to_user_id,
                    "client_id": client_id,
                    "message_type": constants.MESSAGE_TYPE_BOT,
                    "message_state": constants.MESSAGE_STATE_FINISH,
                    "context_token": context_token,
                }
            }
            if item_list:
                msg_body["msg"]["item_list"] = item_list

            payload = {**msg_body, "base_info": self._base_info()}
            await self._post_ilink(
                "ilink/bot/sendmessage",
                payload,
                timeout=constants.DEFAULT_API_TIMEOUT_MS / 1000.0,
            )

    def _resolve_chat_ids(self, msg: Dict[str, Any]) -> tuple:
        """解析聊天ID和发送者ID"""
        from_uid = str(msg.get("from_user_id") or "")
        gid = msg.get("group_id")
        if gid is not None and str(gid).strip():
            return str(gid).strip(), from_uid
        return from_uid, from_uid

    def _inbound_content_and_media_note(self, msg: Dict[str, Any]) -> tuple:
        """提取消息内容和媒体通知"""
        items = msg.get("item_list") or []
        if not isinstance(items, list):
            items = []
        body = body_from_item_list(items)
        media: List[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            t = it.get("type")
            if t == constants.MESSAGE_ITEM_IMAGE:
                media.append("[weixin:image received]")
            elif t == constants.MESSAGE_ITEM_VOICE and not body:
                media.append("[weixin:voice without ASR text]")
            elif t in (constants.MESSAGE_ITEM_FILE, constants.MESSAGE_ITEM_VIDEO):
                media.append("[weixin:file/video]")
        return body, media

    async def _handle_inbound_raw(self, raw: Dict[str, Any]) -> None:
        """处理接收到的原始消息"""
        if raw.get("message_type") != constants.MESSAGE_TYPE_USER:
            return

        chat_id, sender_id = self._resolve_chat_ids(raw)
        ctx = raw.get("context_token")
        if ctx:
            self._context_tokens[chat_id] = str(ctx)

        if self._on_message:
            self._on_message(raw)

    async def _poll_loop(self) -> None:
        """消息轮询循环"""
        get_buf = self._load_get_updates_buf()
        next_timeout = self.config.long_poll_timeout_ms or constants.DEFAULT_LONG_POLL_TIMEOUT_MS

        logger.info(
            "Weixin monitor started base_url=%s buf_len=%d",
            self.config.base_url,
            len(get_buf),
        )

        while not self._stop_evt.is_set():
            if self._session_paused():
                await asyncio.sleep(1.0)
                continue

            try:
                resp = await self.get_updates_once(get_buf, next_timeout)

                if resp.get("longpolling_timeout_ms"):
                    v = int(resp["longpolling_timeout_ms"])
                    if v > 0:
                        next_timeout = v

                ret = resp.get("ret", 0)
                errcode = resp.get("errcode", 0)
                is_err = (ret not in (0, None)) or (errcode not in (0, None))

                if is_err:
                    if errcode == constants.SESSION_EXPIRED_ERRCODE or ret == constants.SESSION_EXPIRED_ERRCODE:
                        self._pause_session()
                        self._consecutive_failures = 0
                        continue

                    self._consecutive_failures += 1
                    logger.error(
                        "Weixin getUpdates err ret=%s errcode=%s errmsg=%s",
                        ret,
                        errcode,
                        resp.get("errmsg"),
                    )

                    if self._consecutive_failures >= constants.MAX_CONSECUTIVE_FAILURES:
                        self._consecutive_failures = 0
                        await asyncio.sleep(constants.BACKOFF_DELAY_MS / 1000.0)
                    else:
                        await asyncio.sleep(constants.RETRY_DELAY_MS / 1000.0)
                    continue

                self._consecutive_failures = 0
                new_buf = resp.get("get_updates_buf")
                if new_buf:
                    self._save_get_updates_buf(str(new_buf))
                    get_buf = str(new_buf)

                for m in resp.get("msgs") or []:
                    if isinstance(m, dict):
                        await self._handle_inbound_raw(m)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._stop_evt.is_set():
                    break
                self._consecutive_failures += 1
                logger.exception("Weixin poll error: %s", e)

                if self._consecutive_failures >= constants.MAX_CONSECUTIVE_FAILURES:
                    self._consecutive_failures = 0
                    await asyncio.sleep(constants.BACKOFF_DELAY_MS / 1000.0)
                else:
                    await asyncio.sleep(constants.RETRY_DELAY_MS / 1000.0)

        logger.info("Weixin monitor stopped")

    async def start(self) -> None:
        """启动客户端，开始接收消息"""
        if not (self.config.bot_token or "").strip():
            raise ValueError("bot_token is required")
        if not (self.config.base_url or "").strip():
            raise ValueError("base_url is required")

        self._running = True
        self._stop_evt.clear()
        self._client = httpx.AsyncClient()
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("WeixinClient started")

    async def stop(self) -> None:
        """停止客户端"""
        self._running = False
        self._stop_evt.set()

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._client:
            await self._client.aclose()
            self._client = None

        logger.info("WeixinClient stopped")

    async def send_text(
        self,
        to_user_id: str,
        text: str,
        context_token: Optional[str] = None,
    ) -> None:
        """发送文本消息的便捷方法

        Args:
            to_user_id: 接收者用户ID
            text: 消息文本
            context_token: 上下文Token，如果未提供则使用已保存的Token
        """
        token = context_token or self._context_tokens.get(to_user_id)
        if not token:
            logger.error(
                "Weixin send: no context_token for user_id=%s — cannot attach reply to conversation",
                to_user_id,
            )
            return
        await self.send_text_message(to_user_id, text, token)

    def get_context_token(self, chat_id: str) -> Optional[str]:
        """获取指定会话的context_token"""
        return self._context_tokens.get(chat_id)

    @property
    def is_running(self) -> bool:
        """检查客户端是否正在运行"""
        return self._running
