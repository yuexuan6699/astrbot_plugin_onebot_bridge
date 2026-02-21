# OneBot桥接插件

主副Bot桥接插件，支持将消息转发到副Bot并支持OneBot v11协议。

## 应用项目
- **[AstrBot](https://docs.astrbot.app/)**

## 功能特性

- 支持多种网络连接方式
  - WebSocket客户端连接到副Bot
  - WebSocket服务器接收副Bot连接
  - HTTP服务器接收副Bot请求
  - HTTP SSE服务器支持SSE推送
  - HTTP客户端主动连接副Bot
- 支持群消息和私聊消息转发
- 支持多种触发方式
  - 命令前缀触发（去除前缀转发剩余内容）
  - 转发前缀触发（完整转发消息）
  - 关键字触发（完整转发消息）
- 完整支持OneBot v11协议消息格式
- 支持多种消息类型转换
- 支持心跳检测和自动重连机制
- 支持多客户端配置
- 支持OneBot API调用

## 安装

查 AstrBot 文档：[https://docs.astrobot.cn/](https://docs.astrobot.cn/)

## 配置说明

### 网络配置

插件支持5种网络连接方式，可在配置中添加多个：

#### WebSocket客户端

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 客户端名称 | ws_client |
| enable | 是否启用 | true |
| debug | 调试模式 | false |
| uri | WebSocket服务端URI地址 | ws://localhost:3001/OneBotv11 |
| token | 访问令牌 | (空) |
| report_self_message | 是否上报机器人自己发送的消息 | false |
| enable_force_push_event | 是否强制推送所有事件 | true |
| message_post_format | 消息格式(array/string) | array |
| heart_interval | 心跳间隔(毫秒) | 30000 |
| ping_interval | Ping间隔(秒) | 10 |
| ping_timeout | Ping超时(秒) | 20 |
| connect_timeout | 连接超时(秒) | 10 |
| close_timeout | 关闭超时(秒) | 5 |
| max_reconnect_attempts | 最大重连次数(0为无限) | 0 |

#### WebSocket服务器

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 服务器名称 | ws_server |
| enable | 是否启用 | true |
| debug | 调试模式 | false |
| host | 监听地址 | 127.0.0.1 |
| port | 监听端口 | 3001 |
| path | WebSocket路径 | /OneBotv11 |
| token | 访问令牌 | (空) |
| report_self_message | 是否上报自身消息 | false |
| enable_force_push_event | 是否强制推送事件 | true |
| message_post_format | 消息格式(array/string) | array |
| heart_interval | 心跳间隔(毫秒) | 30000 |

#### HTTP服务器

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 服务器名称 | http_server |
| enable | 是否启用 | true |
| debug | 调试模式 | false |
| host | 监听地址 | 127.0.0.1 |
| port | 监听端口 | 3000 |
| enable_cors | 是否启用CORS跨域 | true |
| enable_websocket | 是否启用WebSocket | false |
| message_post_format | 消息格式(array/string) | array |
| token | 访问令牌 | (空) |

#### HTTP SSE服务器

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 服务器名称 | sse_server |
| enable | 是否启用 | true |
| debug | 调试模式 | false |
| host | 监听地址 | 127.0.0.1 |
| port | 监听端口 | 3002 |
| enable_cors | 是否启用CORS跨域 | true |
| message_post_format | 消息格式(array/string) | array |
| token | 访问令牌 | (空) |

#### HTTP客户端

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| name | 客户端名称 | http_client |
| enable | 是否启用 | true |
| debug | 调试模式 | false |
| base_url | HTTP服务端基础URL | http://localhost:3000 |
| token | 访问令牌 | (空) |
| report_self_message | 是否上报自身消息 | false |
| enable_force_push_event | 是否强制推送事件 | true |
| message_post_format | 消息格式(array/string) | array |
| timeout | 请求超时时间(秒) | 30 |

### 功能开关配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| enable_group_forward | 启用群消息转发 | true |
| enable_private_forward | 启用私聊消息转发 | false |
| command_prefix | 命令前缀(去除前缀转发) | (空) |
| forward_fprefix | 转发前缀(完整转发) | ["#", "*", "%"] |
| forward_keyword | 触发转发的关键字 | [] |
| help_list | 帮助命令返回的列表内容 | [] |

### 调试配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| debug | 调试模式 | false |

## 使用方法

### 触发方式说明

插件支持三种触发转发的方式：

1. **命令前缀触发**：配置 `command_prefix` 后，消息以该前缀开头时会去除前缀并转发剩余内容
   ```
   /yz 你好  ->  转发 "你好"
   ```

2. **转发前缀触发**：配置 `forward_fprefix` 后，消息以指定前缀开头时完整转发
   ```
   #你好  ->  转发 "#你好"
   ```

3. **关键字触发**：配置 `forward_keyword` 后，消息包含关键字时完整转发

### 帮助命令

```
bot_help
帮助
help
```

## 消息类型支持

插件支持以下消息类型的转换和转发：

- 文本
- 图片
- @ (at)
- 表情
- 语音
- 视频
- 回复
- 文件
- JSON (json)
- XML (xml)
- 位置
- 联系人
- 骰子
- 猜拳
- 戳一戳
- 音乐
- 合并转发

## OneBot API支持

插件支持以下OneBot v11 API调用：

### 消息API
- `get_msg` - 获取消息
- `delete_msg` - 撤回消息
- `get_forward_msg` - 获取合并转发消息
- `send_group_forward_msg` - 发送群合并转发消息
- `send_private_forward_msg` - 发送私聊合并转发消息

### 群组API
- `get_group_list` - 获取群列表
- `get_group_member_info` - 获取群成员信息
- `get_group_member_list` - 获取群成员列表

### 好友API
- `get_friend_list` - 获取好友列表

## 注意事项

1. 确保副Bot的网络服务已正确配置并运行
2. 如需转发私聊消息，请在配置中启用 `enable_private_forward`
3. 调试模式下会输出更多日志信息，便于排查问题
4. 可以同时配置多个网络连接方式，实现多Bot互联

## 许可证

跟随 AstrBot 项目的许可证。

## 作者

苏月晅
