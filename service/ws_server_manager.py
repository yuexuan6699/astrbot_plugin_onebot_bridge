import asyncio
import json
import time
from typing import Dict, Any, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass
import websockets
import websockets.exceptions
from aiohttp import web

from astrbot.api import logger

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection as WebSocketServerProtocol
else:
    WebSocketServerProtocol = Any


@dataclass
class WSServerConfig:
    enable: bool = True
    name: str = "ws_server"
    host: str = "127.0.0.1"
    port: int = 3001
    path: str = "/OneBotv11"
    token: str = ""
    debug: bool = False
    report_self_message: bool = False
    enable_force_push_event: bool = True
    message_post_format: str = "array"
    heart_interval: int = 30000

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "WSServerConfig":
        return cls(
            enable=config_dict.get("enable", True),
            name=config_dict.get("name", "ws_server"),
            host=config_dict.get("host", "127.0.0.1"),
            port=config_dict.get("port", 3001),
            path=config_dict.get("path", "/OneBotv11"),
            token=config_dict.get("token", ""),
            debug=config_dict.get("debug", False),
            report_self_message=config_dict.get("report_self_message", False),
            enable_force_push_event=config_dict.get("enable_force_push_event", True),
            message_post_format=config_dict.get("message_post_format", "array"),
            heart_interval=config_dict.get("heart_interval", 30000),
        )


class WSServerManager:
    def __init__(self, config: Dict[str, Any], bot_id: str, send_message_callback):
        self.config = config
        self.bot_id = bot_id
        self.send_message_callback = send_message_callback
        
        self.ws_servers: Dict[str, WSServerConfig] = {}
        self.ws_clients: Dict[str, Set[WebSocketServerProtocol]] = {}
        self.servers: Dict[str, Any] = {}
        
        self._load_ws_servers_config()
        
        self.message_api = None
        self.group_api = None
        self.friend_api = None
    
    def set_api_handlers(self, message_api, group_api, friend_api):
        self.message_api = message_api
        self.group_api = group_api
        self.friend_api = friend_api
        
    def _load_ws_servers_config(self):
        websocket_clients = self.config.get("websocket_clients", [])
        
        if websocket_clients:
            for i, server_config in enumerate(websocket_clients):
                if isinstance(server_config, dict):
                    template_key = server_config.get("__template_key")
                    if template_key != "WebSocket服务器":
                        continue
                    name = server_config.get("name", f"ws_server_{i}")
                    self.ws_servers[name] = WSServerConfig.from_dict(server_config)
                    self.ws_clients[name] = set()
                    logger.info(f"[Bot通信] 已加载WebSocket服务器配置: {name} -> {self.ws_servers[name].host}:{self.ws_servers[name].port}")
    
    async def start_all(self):
        tasks = [self.start_server(name) for name, server in self.ws_servers.items() if server.enable]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        total_count = len([s for s in self.ws_servers.values() if s.enable])
        logger.debug(f"[Bot通信] 已启动所有WebSocket服务器，成功 {success_count}/{total_count}")
        
        return success_count
    
    async def start_server(self, server_name: str) -> bool:
        server = self.ws_servers.get(server_name)
        if not server:
            logger.error(f"[Bot通信] WebSocket服务器 {server_name} 不存在")
            return False
        
        if not server.enable:
            logger.debug(f"[Bot通信] WebSocket服务器 {server_name} 已禁用，跳过启动")
            return False
        
        try:
            async def handler(websocket: WebSocketServerProtocol):
                await self._handle_connection(server_name, websocket)
            
            ws_server = await websockets.serve(
                handler,
                server.host,
                server.port,
                subprotocols=["onebot.v11"]
            )
            
            self.servers[server_name] = ws_server
            
            logger.info(f"[Bot通信] WebSocket服务器 {server_name} 已启动: ws://{server.host}:{server.port}{server.path}")
            return True
            
        except Exception as e:
            logger.error(f"[Bot通信] 启动WebSocket服务器 {server_name} 失败: {e}")
            return False
    
    async def _handle_connection(self, server_name: str, websocket: WebSocketServerProtocol):
        server = self.ws_servers.get(server_name)
        if not server:
            return
        
        if server.token:
            auth_header = websocket.request_headers.get('Authorization', '') if hasattr(websocket, 'request_headers') else ''
            if auth_header.startswith('Bearer '):
                provided_token = auth_header[7:]
            else:
                provided_token = websocket.request_headers.get('access_token', '') if hasattr(websocket, 'request_headers') else ''
            
            if provided_token != server.token:
                logger.warning(f"[Bot通信] WebSocket服务器 {server_name} 拒绝未授权连接")
                await websocket.close(code=1008, reason="Unauthorized")
                return
        
        self.ws_clients[server_name].add(websocket)
        client_addr = websocket.remote_address if hasattr(websocket, 'remote_address') else 'unknown'
        logger.info(f"[Bot通信] WebSocket服务器 {server_name} 新连接: {client_addr}")
        
        try:
            await self._send_lifecycle_event(websocket, "connect")
            
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if server.debug:
                        logger.debug(f"[Bot通信] WebSocket服务器 {server_name} 收到消息: {data}")
                    
                    await self._handle_message(server_name, websocket, data)
                except json.JSONDecodeError:
                    logger.error(f"[Bot通信] 无效的JSON消息: {message}")
                except Exception as e:
                    logger.error(f"[Bot通信] 处理消息失败: {e}")
        
        except websockets.exceptions.ConnectionClosedOK:
            logger.debug(f"[Bot通信] WebSocket服务器 {server_name} 连接正常关闭: {client_addr}")
        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(f"[Bot通信] WebSocket服务器 {server_name} 连接异常关闭: {client_addr}: {e}")
        except Exception as e:
            logger.error(f"[Bot通信] WebSocket服务器 {server_name} 连接异常: {client_addr}: {e}")
        finally:
            self.ws_clients[server_name].discard(websocket)
            logger.info(f"[Bot通信] WebSocket服务器 {server_name} 连接断开: {client_addr}")
    
    async def _send_lifecycle_event(self, websocket: WebSocketServerProtocol, sub_type: str):
        event = {
            "post_type": "meta_event",
            "meta_event_type": "lifecycle",
            "sub_type": sub_type,
            "self_id": self.bot_id,
            "time": int(time.time())
        }
        await websocket.send(json.dumps(event))
    
    async def _handle_message(self, server_name: str, websocket: WebSocketServerProtocol, data: Dict[str, Any]):
        action = data.get("action")
        params = data.get("params", {})
        echo = data.get("echo")
        
        response: Dict[str, Any] = {
            "status": "ok",
            "data": {},
            "echo": echo
        }
        
        try:
            if action in ["send_msg", "send_group_msg", "send_private_msg"]:
                content = params.get("message")
                if content is None:
                    response["status"] = "failed"
                    response["data"] = {"error": "缺少message参数"}
                elif "group_id" in params:
                    group_id = str(params["group_id"])
                    if self.send_message_callback:
                        msg_id = await self.send_message_callback("GroupMessage", group_id, content)
                        response["data"] = {"message_id": msg_id or "0"}
                elif "user_id" in params:
                    user_id = str(params["user_id"])
                    if self.send_message_callback:
                        msg_id = await self.send_message_callback("FriendMessage", user_id, content)
                        response["data"] = {"message_id": msg_id or "0"}
                else:
                    response["status"] = "failed"
                    response["data"] = {"error": "缺少group_id或user_id参数"}
            
            elif action == "get_self_info" or action == "get_login_info":
                response["data"] = {
                    "user_id": self.bot_id,
                    "nickname": "AstrBot"
                }
            
            elif action == "get_version_info":
                response["data"] = {
                    "app_name": "AstrBot",
                    "app_version": "1.0.0",
                    "protocol_version": "v11"
                }
            
            elif action in ["get_msg", "delete_msg", "get_forward_msg", "send_group_forward_msg", "send_private_forward_msg"]:
                if self.message_api:
                    response = await self.message_api.handle_request(action, params)
                    response["echo"] = echo
                else:
                    response["status"] = "failed"
                    response["data"] = {"error": "API处理器未初始化"}
            
            elif action in ["get_group_list", "get_group_member_info", "get_group_member_list"]:
                if self.group_api:
                    response = await self.group_api.handle_request(action, params)
                    response["echo"] = echo
                else:
                    response["status"] = "failed"
                    response["data"] = {"error": "API处理器未初始化"}
            
            elif action == "get_friend_list":
                if self.friend_api:
                    response = await self.friend_api.handle_request(action, params)
                    response["echo"] = echo
                else:
                    response["status"] = "failed"
                    response["data"] = {"error": "API处理器未初始化"}
            
            else:
                response["status"] = "failed"
                response["data"] = {"error": f"不支持的动作: {action}"}
        
        except Exception as e:
            logger.error(f"[Bot通信] 处理OneBot动作失败: {e}")
            response["status"] = "failed"
            response["data"] = {"error": str(e)}
        
        if "retcode" not in response:
            response["retcode"] = 0 if response["status"] == "ok" else 1
        
        await websocket.send(json.dumps(response))
    
    async def send_message(self, message: Any) -> int:
        success_count = 0
        
        for server_name, clients in self.ws_clients.items():
            server = self.ws_servers.get(server_name)
            for client in list(clients):
                try:
                    if isinstance(message, dict):
                        data = json.dumps(message, ensure_ascii=False)
                    else:
                        data = str(message)
                    
                    await client.send(data)
                    success_count += 1
                    
                    if server and server.debug:
                        logger.debug(f"[Bot通信] WebSocket服务器 {server_name} 消息发送成功")
                except Exception as e:
                    logger.error(f"[Bot通信] WebSocket服务器发送消息失败: {e}")
                    clients.discard(client)
        
        return success_count
    
    async def close(self):
        logger.debug("[Bot通信] 开始关闭WebSocket服务器管理器...")
        
        for server_name, clients in self.ws_clients.items():
            for client in clients:
                try:
                    await client.close(code=1000, reason="Server shutting down")
                except Exception:
                    pass
        
        for name, server in self.servers.items():
            try:
                server.close()
                await server.wait_closed()
                logger.debug(f"[Bot通信] 已关闭WebSocket服务器: {name}")
            except Exception as e:
                logger.error(f"[Bot通信] 关闭WebSocket服务器 {name} 失败: {e}")
        
        self.servers = {}
        self.ws_clients = {}
        
        logger.debug("[Bot通信] WebSocket服务器管理器已关闭")
