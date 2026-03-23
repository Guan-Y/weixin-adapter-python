"""Weixin Adapter CLI & Test Suite

测试模块化微信适配器的各个组件，并提供命令行工具。
Usage:
    # 运行单元测试
    python test_weixin_adapter.py test

    # 获取二维码
    python test_weixin_adapter.py qrcode

    # 交互式登录
    python test_weixin_adapter.py login

    # 启动消息客户端
    python test_weixin_adapter.py client --token YOUR_TOKEN --base-url https://ilinkai.weixin.qq.com
"""

import asyncio
import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

try:
    import typer
    from typing_extensions import Annotated
    HAS_TYPER = True
except ImportError:
    HAS_TYPER = False
    typer = None
    Annotated = None


async def run_tests():
    """运行单元测试"""
    from typing import Any, Dict
    from unittest.mock import AsyncMock, MagicMock, patch

    from weixin_adapter import (
        WeixinClient,
        WeixinConfig,
        WeixinLogin,
        fetch_bot_qrcode,
        poll_qrcode_status,
        constants,
        utils,
    )

    print("\n" + "=" * 60)
    print("微信适配器测试套件")
    print("=" * 60)

    def test_constants():
        print("\n" + "-" * 40)
        print("测试: constants 模块")
        print("-" * 40)

        assert constants.MESSAGE_TYPE_USER == 1
        assert constants.MESSAGE_TYPE_BOT == 2
        assert constants.MESSAGE_ITEM_TEXT == 1
        assert constants.MESSAGE_ITEM_IMAGE == 2
        assert constants.MESSAGE_ITEM_VOICE == 3
        assert constants.MESSAGE_ITEM_FILE == 4
        assert constants.MESSAGE_ITEM_VIDEO == 5
        assert constants.MESSAGE_STATE_FINISH == 2
        assert constants.SESSION_EXPIRED_ERRCODE == -14
        assert constants.DEFAULT_LONG_POLL_TIMEOUT_MS == 35_000
        assert constants.DEFAULT_API_TIMEOUT_MS == 15_000
        assert constants.TEXT_CHUNK_LIMIT == 4000

        print("✓ 所有常量测试通过")

    def test_utils():
        print("\n" + "-" * 40)
        print("测试: utils 模块")
        print("-" * 40)

        uin = utils.random_wechat_uin()
        assert isinstance(uin, str)
        assert len(uin) > 0
        print(f"✓ random_wechat_uin: {uin}")

        url = utils.ensure_trailing_slash("https://example.com")
        assert url == "https://example.com/"
        print("✓ ensure_trailing_slash 测试通过")

        plain = utils.markdown_to_plain_text("**粗体** 和 *斜体*")
        assert "粗体" in plain and "斜体" in plain
        print(f"✓ markdown_to_plain_text: {plain}")

        item = {"type": 2}
        assert utils.is_media_item(item) == True
        item = {"type": 1}
        assert utils.is_media_item(item) == False
        print("✓ is_media_item 测试通过")

        item_list = [
            {"type": 1, "text_item": {"text": "Hello"}},
            {"type": 2, "image_item": {"url": "http://example.com/image.jpg"}},
        ]
        body = utils.body_from_item_list(item_list)
        assert body == "Hello"
        print(f"✓ body_from_item_list: {body}")

        print("✓ utils 模块所有测试通过")

    def test_login():
        print("\n" + "-" * 40)
        print("测试: login 模块")
        print("-" * 40)

        qr_response = {
            "qrcode": "test_qrcode_12345",
            "qrcode_img_content": "data:image/png;base64,iVBORw0KGgoAAAANS...",
        }
        payload = WeixinLogin._qr_payload_for_terminal_static(qr_response)
        assert payload == "data:image/png;base64,iVBORw0KGgoAAAANS..."
        print("✓ qr_payload_for_terminal")

        login = WeixinLogin(
            api_base_url="https://ilinkai.weixin.qq.com",
            bot_type="3",
        )
        assert login.api_base_url == "https://ilinkai.weixin.qq.com"
        print("✓ WeixinLogin 初始化")

        print("✓ login 模块测试通过")

    def test_client_config():
        print("\n" + "-" * 40)
        print("测试: WeixinConfig")
        print("-" * 40)

        config = WeixinConfig(
            bot_token="test_token_12345",
            base_url="https://ilinkai.weixin.qq.com",
            account_id="test_account_123",
        )
        assert config.bot_token == "test_token_12345"
        assert config.base_url == "https://ilinkai.weixin.qq.com"
        print("✓ WeixinConfig 初始化")

    def test_callbacks():
        print("\n" + "-" * 40)
        print("测试: on_message/on_error 回调")
        print("-" * 40)

        received_messages = []
        received_errors = []

        def on_message(msg):
            received_messages.append(msg)

        def on_error(err):
            received_errors.append(err)

        config = WeixinConfig(bot_token="test", base_url="https://test.com")
        client = WeixinClient(config, on_message=on_message, on_error=on_error)

        assert client._on_message == on_message
        assert client._on_error == on_error

        test_msg = {"type": 1, "content": "test"}
        client._on_message(test_msg)
        assert len(received_messages) == 1
        assert received_messages[0] == test_msg

        print("✓ on_message 回调测试通过")

        client._on_error(ValueError("test error"))
        assert len(received_errors) == 1
        print("✓ on_error 回调测试通过")

    async def test_client():
        print("\n" + "-" * 40)
        print("测试: WeixinClient")
        print("-" * 40)

        config = WeixinConfig(
            bot_token="test_token",
            base_url="https://ilinkai.weixin.qq.com",
        )
        client = WeixinClient(config)
        assert client._running == False
        print("✓ WeixinClient 初始化")

        client._context_tokens["chat_123"] = "token_abc"
        token = client.get_context_token("chat_123")
        assert token == "token_abc"
        print("✓ get_context_token")

        try:
            await client.send_text_message("user_123", "Hello", "token")
        except RuntimeError as e:
            assert "HTTP client not started" in str(e)
            print("✓ 未启动时发送消息正确抛出异常")

    async def test_module_import():
        print("\n" + "-" * 40)
        print("测试: 模块导入")
        print("-" * 40)

        from weixin_adapter import WeixinClient, WeixinConfig
        from weixin_adapter.login import WeixinLogin
        from weixin_adapter.constants import MESSAGE_TYPE_USER
        from weixin_adapter.utils import markdown_to_plain_text

        print("✓ 所有模块导入成功")

    test_constants()
    test_utils()
    test_login()
    test_client_config()
    test_callbacks()
    await test_client()
    await test_module_import()

    print("\n" + "=" * 60)
    print("✓ 所有单元测试通过!")
    print("=" * 60)


async def cmd_qrcode(
    api_base_url: str = "https://ilinkai.weixin.qq.com",
    bot_type: str = "3",
    sk_route_tag: str = None,
):
    """获取微信登录二维码"""
    from weixin_adapter.login import fetch_bot_qrcode, qr_payload_for_terminal, print_weixin_qr_terminal

    print(f"\n获取二维码...")
    print(f"API URL: {api_base_url}")
    print(f"Bot Type: {bot_type}")

    try:
        qr_data = await fetch_bot_qrcode(
            api_base_url,
            bot_type,
            sk_route_tag=sk_route_tag,
        )

        qrcode = qr_data.get("qrcode")
        qrcode_img = qr_data.get("qrcode_img_content")

        print(f"\n✓ 获取成功!")
        print(f"QR Code: {qrcode[:50]}..." if qrcode and len(str(qrcode)) > 50 else f"QR Code: {qrcode}")

        if qrcode_img:
            print("QR Image Content: (base64 data)")
            print_weixin_qr_terminal(qr_payload_for_terminal(qr_data))
        elif qrcode:
            print("\n请使用微信扫描以下二维码:")
            print_weixin_qr_terminal(str(qrcode))

        return qr_data

    except Exception as e:
        print(f"\n✗ 获取二维码失败: {e}")
        raise typer.Exit(1)


async def cmd_login(
    api_base_url: str = "https://ilinkai.weixin.qq.com",
    bot_type: str = "3",
    sk_route_tag: str = None,
    timeout: float = 480.0,
):
    """交互式微信登录"""
    from weixin_adapter.login import WeixinLogin

    print(f"\n开始微信登录...")
    print(f"API URL: {api_base_url}")
    print(f"Timeout: {timeout}s")

    messages = []

    def log_message(msg: str):
        messages.append(msg)
        print(msg)

    login = WeixinLogin(
        api_base_url=api_base_url,
        bot_type=bot_type,
        sk_route_tag=sk_route_tag,
        on_message=log_message,
    )

    try:
        result = await login.login(login_timeout_s=timeout)

        print("\n" + "=" * 60)
        print("✓ 登录成功!")
        print("=" * 60)
        print(f"Bot Token: {result.bot_token[:20]}..." if len(result.bot_token) > 20 else f"Bot Token: {result.bot_token}")
        print(f"Base URL:  {result.base_url}")
        if result.account_id:
            print(f"Account ID: {result.account_id}")
        if result.user_id:
            print(f"User ID:    {result.user_id}")

        save_token = input("\n是否保存Token到文件? (y/n): ").strip().lower()
        if save_token == 'y':
            config_path = Path.home() / ".weixin_adapter" / "config.json"
            config_path.parent.mkdir(parents=True, exist_ok=True)

            import json
            config_data = {
                "bot_token": result.bot_token,
                "base_url": result.base_url,
                "account_id": result.account_id or "",
                "user_id": result.user_id or "",
            }
            config_path.write_text(json.dumps(config_data, indent=2, ensure_ascii=False))
            print(f"✓ 已保存到: {config_path}")

        return result

    except Exception as e:
        print(f"\n✗ 登录失败: {e}")
        raise typer.Exit(1)


async def cmd_client(
    token: str = None,
    base_url: str = "https://ilinkai.weixin.qq.com",
    account_id: str = "",
    sk_route_tag: str = None,
    duration: int = 60,
):
    """启动微信客户端进行测试"""
    from weixin_adapter import WeixinClient, WeixinConfig

    if not token:
        config_path = Path.home() / ".weixin_adapter" / "config.json"
        if config_path.exists():
            import json
            config_data = json.loads(config_path.read_text())
            token = config_data.get("bot_token")
            base_url = config_data.get("base_url", base_url)
            account_id = config_data.get("account_id", account_id)
            print(f"✓ 已从配置文件加载Token")
        else:
            print("✗ 请提供 --token 参数")
            raise typer.Exit(1)

    print(f"\n启动微信客户端...")
    print(f"Base URL: {base_url}")
    print(f"Duration: {duration}s")

    config = WeixinConfig(
        bot_token=token,
        base_url=base_url,
        account_id=account_id,
        sk_route_tag=sk_route_tag,
    )

    def on_message(msg):
        import json
        print(f"\n[收到消息] {json.dumps(msg, ensure_ascii=False)[:200]}...")

    def on_error(err):
        print(f"\n[错误] {err}")

    client = WeixinClient(config, on_message=on_message, on_error=on_error)

    try:
        await client.start()
        print(f"✓ 客户端已启动，监听 {duration} 秒...")

        for i in range(duration):
            await asyncio.sleep(1)
            if i % 10 == 0:
                print(f"  运行中... {i}/{duration}s")

    except Exception as e:
        print(f"\n✗ 客户端错误: {e}")
    finally:
        await client.stop()
        print("✓ 客户端已停止")


def create_cli():
    """创建CLI应用"""
    if not HAS_TYPER:
        print("Error: typer is required. Install with: pip install typer")
        sys.exit(1)

    app = typer.Typer(
        name="weixin-adapter",
        help="微信iLink适配器测试工具",
        add_completion=False,
    )

    @app.command()
    def test():
        """运行单元测试"""
        asyncio.run(run_tests())

    @app.command()
    def qrcode(
        api_url: Annotated[str, typer.Option("--api-url", "-u")] = "https://ilinkai.weixin.qq.com",
        bot_type: Annotated[str, typer.Option("--bot-type", "-t")] = "3",
        sk_tag: Annotated[str, typer.Option("--sk-tag", "-s")] = None,
    ):
        """获取微信登录二维码"""
        asyncio.run(cmd_qrcode(api_url, bot_type, sk_tag))

    @app.command()
    def login(
        api_url: Annotated[str, typer.Option("--api-url", "-u")] = "https://ilinkai.weixin.qq.com",
        bot_type: Annotated[str, typer.Option("--bot-type", "-t")] = "3",
        sk_tag: Annotated[str, typer.Option("--sk-tag", "-s")] = None,
        timeout: Annotated[float, typer.Option("--timeout", "-o")] = 480.0,
    ):
        """交互式微信登录"""
        asyncio.run(cmd_login(api_url, bot_type, sk_tag, timeout))

    @app.command()
    def client(
        token: Annotated[str, typer.Option("--token", "-k")] = None,
        api_url: Annotated[str, typer.Option("--api-url", "-u")] = "https://ilinkai.weixin.qq.com",
        account_id: Annotated[str, typer.Option("--account-id", "-a")] = "",
        sk_tag: Annotated[str, typer.Option("--sk-tag", "-s")] = None,
        duration: Annotated[int, typer.Option("--duration", "-d")] = 60,
    ):
        """启动微信客户端"""
        asyncio.run(cmd_client(token, api_url, account_id, sk_tag, duration))

    return app


def main():
    if len(sys.argv) == 1:
        print(__doc__)
        print("\n可用命令:")
        print("  test      - 运行单元测试")
        print("  qrcode    - 获取二维码")
        print("  login     - 交互式登录")
        print("  client    - 启动客户端")
        print("\n示例:")
        print("  python test_weixin_adapter.py test")
        print("  python test_weixin_adapter.py qrcode")
        print("  python test_weixin_adapter.py login")
        print("  python test_weixin_adapter.py client --token YOUR_TOKEN")
        sys.exit(0)

    if not HAS_TYPER:
        cmd = sys.argv[1]
        if cmd == "test":
            asyncio.run(run_tests())
        else:
            print(f"Error: '{cmd}' command requires typer. Install with: pip install typer")
            sys.exit(1)
    else:
        app = create_cli()
        app()


if __name__ == "__main__":
    main()
