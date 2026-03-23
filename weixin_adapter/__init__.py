"""Weixin iLink Adapter - 模块化微信客户端，不依赖nanobot框架。

Usage:
    from weixin_adapter import WeixinClient, WeixinConfig

    config = WeixinConfig(
        bot_token="your_bot_token",
        base_url="https://ilinkai.weixin.qq.com",
        account_id="your_account_id"
    )

    def on_message(msg):
        print(f"收到消息: {msg}")

    def on_error(err):
        print(f"错误: {err}")

    client = WeixinClient(config, on_message=on_message, on_error=on_error)

    # 启动客户端
    await client.start()

    # 发送消息
    await client.send_text("user_id", "Hello", "context_token")

    # 停止客户端
    await client.stop()
"""

from weixin_adapter.client import WeixinClient, WeixinConfig
from weixin_adapter.login import WeixinLogin, fetch_bot_qrcode, poll_qrcode_status
from weixin_adapter import constants
from weixin_adapter import utils

__version__ = "1.0.0"

__all__ = [
    "WeixinClient",
    "WeixinConfig",
    "WeixinLogin",
    "fetch_bot_qrcode",
    "poll_qrcode_status",
    "constants",
    "utils",
]
