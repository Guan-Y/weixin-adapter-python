# Weixin iLink Adapter

Python版微信(iLink)机器人适配器，可作为独立组件集成到其他项目中。

## 功能特性

- **消息接收**: 长轮询获取微信消息
- **消息发送**: 发送文本消息给用户
- **QR登录**: 支持交互式二维码扫码登录获取 Token
- **无依赖**: 不依赖特定claw

## 安装

```bash
uv pip install httpx
```

可选依赖（用于test命令行交互和显示二维码）:

```bash
uv pip install typer
uv pip install qrcode
```

## 快速开始

### 1. 获取登录二维码

```python
from weixin_adapter import WeixinLogin

login = WeixinLogin()
result = await login.login()
print(f"Token: {result.bot_token}")
```

### 2. 使用 Token 创建客户端

```python
from weixin_adapter import WeixinClient, WeixinConfig

config = WeixinConfig(
    bot_token="your_bot_token",
    base_url="https://ilinkai.weixin.qq.com"
)

def on_message(msg):
    print(f"收到消息: {msg}")

def on_error(err):
    print(f"错误: {err}")

client = WeixinClient(config, on_message=on_message, on_error=on_error)
await client.start()
```

### 3. 发送消息

```python
# 根据收到的消息回复
await client.send_text(to_user_id="user_id", text="Hello", context_token="token_from_msg")
```

### 4. 停止客户端

```python
await client.stop()
```

## API 参考

### WeixinConfig

客户端配置类。

```python
from weixin_adapter import WeixinConfig

config = WeixinConfig(
    bot_token="机器人Token",
    base_url="API基础URL",
    account_id="账户ID",           # 可选
    sk_route_tag="路由标签",        # 可选
    channel_version="1.0.2",       # 可选
)
```

| 参数                      | 类型  | 说明                  |
| ----------------------- | --- | ------------------- |
| bot\_token              | str | 机器人 Token，从 QR 登录获取 |
| base\_url               | str | API 基础 URL          |
| account\_id             | str | 账户 ID（可选）           |
| sk\_route\_tag          | str | 路由标签（可选）            |
| channel\_version        | str | 渠道版本号，默认 1.0.2      |
| get\_updates\_buf\_path | str | 消息同步缓冲区文件路径（可选）     |
| long\_poll\_timeout\_ms | int | 长轮询超时时间，默认 35000ms  |

### WeixinClient

微信客户端主类。

```python
client = WeixinClient(
    config=WeixinConfig(...),
    on_message=lambda msg: print(msg),  # 收到消息回调
    on_error=lambda err: print(err),    # 错误回调
)
```

#### 方法

| 方法                                                   | 说明                   |
| ---------------------------------------------------- | -------------------- |
| `start()`                                            | 启动客户端，开始接收消息         |
| `stop()`                                             | 停止客户端                |
| `send_text(to_user_id, text, context_token)`         | 发送文本消息               |
| `send_text_message(to_user_id, text, context_token)` | 发送文本消息（完整版）          |
| `get_context_token(chat_id)`                         | 获取会话的 context\_token |
| `is_running`                                         | 属性，返回客户端是否运行中        |

#### 消息回调格式

`on_message` 回调接收的原始消息字典包含以下字段：

```python
{
    "message_type": 1,           # 消息类型: 1=用户消息
    "from_user_id": "user_xxx",  # 发送者ID
    "to_user_id": "bot_xxx",     # 接收者ID
    "context_token": "xxx",       # 用于回复的Token
    "group_id": "group_xxx",     # 群ID（如果是群消息）
    "item_list": [               # 消息内容列表
        {"type": 1, "text_item": {"text": "消息内容"}},
        {"type": 2, "image_item": {...}},
    ]
}
```

### WeixinLogin

QR 码登录处理器。

```python
login = WeixinLogin(
    api_base_url="https://ilinkai.weixin.qq.com",
    bot_type="3",
    sk_route_tag=None,
    on_message=lambda msg: print(msg),  # 消息回调
)
result = await login.login()
```

#### LoginResult

登录结果包含以下字段：

```python
result.bot_token   # 机器人 Token
result.base_url    # API 基础 URL
result.account_id  # 账户 ID
result.user_id     # 用户 ID
```

### 工具函数

#### fetch\_bot\_qrcode

获取登录二维码。

```python
from weixin_adapter import fetch_bot_qrcode

qr_data = await fetch_bot_qrcode(
    api_base_url="https://ilinkai.weixin.qq.com",
    bot_type="3",
    sk_route_tag=None,
)
# 返回: {"qrcode": "...", "qrcode_img_content": "..."}
```

#### poll\_qrcode\_status

轮询二维码状态。

```python
from weixin_adapter import poll_qrcode_status

status = await poll_qrcode_status(
    api_base_url="https://ilinkai.weixin.qq.com",
    qrcode="二维码标识",
)
# 返回: {"status": "wait"/"scaned"/"confirmed"/"expired", ...}
```

### 常量

```python
from weixin_adapter import constants

constants.MESSAGE_TYPE_USER       # 1 - 用户消息
constants.MESSAGE_TYPE_BOT        # 2 - 机器人消息
constants.MESSAGE_ITEM_TEXT        # 1 - 文本
constants.MESSAGE_ITEM_IMAGE       # 2 - 图片
constants.MESSAGE_ITEM_VOICE      # 3 - 语音
constants.MESSAGE_ITEM_FILE        # 4 - 文件
constants.MESSAGE_ITEM_VIDEO      # 5 - 视频
constants.MESSAGE_STATE_FINISH    # 2 - 消息完成状态
```

### 工具函数

```python
from weixin_adapter import utils

utils.markdown_to_plain_text(markdown_text)  # Markdown 转纯文本
utils.ensure_trailing_slash(url)              # 确保 URL 以斜杠结尾
utils.random_wechat_uin()                      # 生成随机微信 UIN
utils.body_from_item_list(item_list)          # 从消息列表提取文本
utils.is_media_item(item)                     # 判断是否为媒体类型
```

## 命令行工具

项目提供了测试脚本 `test_weixin_adapter.py`，支持以下命令：

```bash
# 运行单元测试
python test_weixin_adapter.py test

# 获取登录二维码
python test_weixin_adapter.py qrcode

# 交互式登录
python test_weixin_adapter.py login

# 启动客户端测试
python test_weixin_adapter.py client --token YOUR_TOKEN -d 30
```

## 完整示例

```python
import asyncio
from weixin_adapter import WeixinClient, WeixinConfig

async def main():
    config = WeixinConfig(
        bot_token="your_token",
        base_url="https://ilinkai.weixin.qq.com"
    )

    async def on_message(msg):
        # 解析消息
        from_user = msg.get("from_user_id")
        context_token = msg.get("context_token")

        # 获取文本内容
        from weixin_adapter.utils import body_from_item_list
        text = body_from_item_list(msg.get("item_list", []))

        print(f"收到用户 {from_user} 的消息: {text}")

        # 回复消息
        await client.send_text(from_user, f"收到: {text}", context_token)

    def on_error(err):
        print(f"错误: {err}")

    client = WeixinClient(config, on_message=on_message, on_error=on_error)

    try:
        await client.start()
        print("客户端已启动，按 Ctrl+C 停止...")

        # 保持运行
        while True:
            await asyncio.sleep(10)
    except KeyboardInterrupt:
        pass
    finally:
        await client.stop()
        print("客户端已停止")

if __name__ == "__main__":
    asyncio.run(main())
```

## 文件结构

```
weixin_adapter/
├── __init__.py      # 主入口，导出公共 API
├── client.py        # WeixinClient 核心类
├── login.py         # QR 登录相关功能
├── constants.py     # 协议常量定义
└── utils.py         # 工具函数
```

## 依赖

- Python 3.8+
- httpx

可选:

- qrcode (用于显示二维码)
- typer (用于 CLI 工具)

