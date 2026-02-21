import asyncio
import json
from typing import Dict, Any, Optional, Set
from dataclasses import dataclass
from aiohttp import web

from astrbot.api import logger


@dataclass
class SSEServerConfig:
    enable: bool = True
    name: str = "sse_server"
    host: str = "127.0.0.1"
    port: int = 3001
    token: str = ""
    debug: bool = False
    enable_cors: bool = True
    message_post_format: str = "array"

    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> "SSEServerConfig":
        return cls(
            enable=config_dict.get("enable", True),
            name=config_dict.get("name", "sse_server"),
            host=config_dict.get("host", "127.0.0.1"),
            port=config_dict.get("port", 3001),
            token=config_dict.get("token", ""),
            debug=config_dict.get("debug", False),
            enable_cors=config_dict.get("enable_cors", True),
            message_post_format=config_dict.get("message_post_format", "array"),
        )


class SSEServerManager:
    def __init__(self, config: Dict[str, Any], bot_id: str, send_message_callback):
        self.config = config
        self.bot_id = bot_id
        self.send_message_callback = send_message_callback
        
        self.sse_servers: Dict[str, SSEServerConfig] = {}
        self.runners: Dict[str, web.AppRunner] = {}
        self.sites: Dict[str, web.TCPSite] = {}
        self.sse_clients: Dict[str, Set[web.StreamResponse]] = {}
        
        self._load_sse_servers_config()
        
        self.message_api = None
        self.group_api = None
        self.friend_api = None
    
    def set_api_handlers(self, message_api, group_api, friend_api):
        self.message_api = message_api
        self.group_api = group_api
        self.friend_api = friend_api
        
    def _load_sse_servers_config(self):
        websocket_clients = self.config.get("websocket_clients", [])
        
        if websocket_clients:
            for i, server_config in enumerate(websocket_clients):
                if isinstance(server_config, dict):
                    template_key = server_config.get("__template_key")
                    if template_key != "HTTP SSE服务器":
                        continue
                    name = server_config.get("name", f"sse_server_{i}")
                    self.sse_servers[name] = SSEServerConfig.from_dict(server_config)
                    self.sse_clients[name] = set()
                    logger.info(f"[Bot通信] 已加载SSE服务器配置: {name} -> {self.sse_servers[name].host}:{self.sse_servers[name].port}")
    
    async def start_all(self):
        tasks = [self.start_server(name) for name, server in self.sse_servers.items() if server.enable]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        success_count = sum(1 for r in results if r is True)
        total_count = len([s for s in self.sse_servers.values() if s.enable])
        logger.debug(f"[Bot通信] 已启动所有SSE服务器，成功 {success_count}/{total_count}")
        
        return success_count
    
    async def start_server(self, server_name: str) -> bool:
        server = self.sse_servers.get(server_name)
        if not server:
            logger.error(f"[Bot通信] SSE服务器 {server_name} 不存在")
            return False
        
        if not server.enable:
            logger.debug(f"[Bot通信] SSE服务器 {server_name} 已禁用，跳过启动")
            return False
        
        try:
            app = web.Application()
            
            if server.enable_cors:
                app.middlewares.append(self._cors_middleware)
            
            if server.token:
                app.middlewares.append(self._create_auth_middleware(server.token))
            
            app.router.add_get('/sse', self._handle_sse_connection)
            app.router.add_get('/events', self._handle_sse_connection)
            app.router.add_post('/onebot/v11', self._handle_onebot_request)
            app.router.add_get('/health', self._handle_health_check)
            
            runner = web.AppRunner(app)
            await runner.setup()
            
            site = web.TCPSite(runner, server.host, server.port)
            await site.start()
            
            self.runners[server_name] = runner
            self.sites[server_name] = site
            
            logger.info(f"[Bot通信] SSE服务器 {server_name} 已启动: http://{server.host}:{server.port}")
            return True
            
        except Exception as e:
            logger.error(f"[Bot通信] 启动SSE服务器 {server_name} 失败: {e}")
            return False
    
    @web.middleware
    async def _cors_middleware(self, request: web.Request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)
        
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        return response
    
    def _create_auth_middleware(self, token: str):
        @web.middleware
        async def auth_middleware(request: web.Request, handler):
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                provided_token = auth_header[7:]
            else:
                provided_token = request.headers.get('access_token', '')
            
            if provided_token != token:
                return web.json_response({'status': 'failed', 'retcode': 1403, 'data': None}, status=403)
            
            return await handler(request)
        return auth_middleware
    
    async def _handle_health_check(self, request: web.Request) -> web.Response:
        return web.json_response({'status': 'ok', 'self_id': self.bot_id})
    
    async def _handle_sse_connection(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse()
        response.content_type = 'text/event-stream'
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['Access-Control-Allow-Origin'] = '*'
        
        await response.prepare(request)
        
        server_name = None
        for name, server in self.sse_servers.items():
            if server.port == request.url.port or (request.url.port is None and server.port == 80):
                server_name = name
                break
        
        if server_name and server_name in self.sse_clients:
            self.sse_clients[server_name].add(response)
            
            try:
                await response.write(b'data: {"status": "connected", "self_id": "' + str(self.bot_id).encode() + b'"}\n\n')
                
                while True:
                    await asyncio.sleep(30)
                    await response.write(b': heartbeat\n\n')
            except (ConnectionResetError, BrokenPipeError):
                pass
            finally:
                self.sse_clients[server_name].discard(response)
        
        return response
    
    async def _handle_onebot_request(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            action = data.get('action')
            params = data.get('params', {})
            echo = data.get('echo')
            
            response = await self._process_onebot_action(action, params, echo)
            return web.json_response(response)
            
        except json.JSONDecodeError:
            return web.json_response({'status': 'failed', 'retcode': 1400, 'data': None}, status=400)
        except Exception as e:
            logger.error(f"[Bot通信] 处理SSE HTTP请求失败: {e}")
            return web.json_response({'status': 'failed', 'retcode': 1500, 'data': {'error': str(e)}}, status=500)
    
    async def _process_onebot_action(self, action: str, params: Dict[str, Any], echo: Any) -> Dict[str, Any]:
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
        
        return response
    
    async def send_message(self, message: Any) -> int:
        success_count = 0
        
        for server_name, clients in self.sse_clients.items():
            for client in list(clients):
                try:
                    if isinstance(message, dict):
                        data = json.dumps(message, ensure_ascii=False)
                    else:
                        data = str(message)
                    
                    await client.write(f'data: {data}\n\n'.encode('utf-8'))
                    success_count += 1
                except Exception as e:
                    logger.error(f"[Bot通信] SSE发送消息失败: {e}")
                    clients.discard(client)
        
        return success_count
    
    async def close(self):
        logger.debug("[Bot通信] 开始关闭SSE服务器管理器...")
        
        for server_name, clients in self.sse_clients.items():
            for client in clients:
                try:
                    await client.write(b'data: {"status": "closing"}\n\n')
                except Exception:
                    pass
        
        for name, site in self.sites.items():
            try:
                await site.stop()
                logger.debug(f"[Bot通信] 已停止SSE服务器: {name}")
            except Exception as e:
                logger.error(f"[Bot通信] 停止SSE服务器 {name} 失败: {e}")
        
        for name, runner in self.runners.items():
            try:
                await runner.cleanup()
            except Exception as e:
                logger.error(f"[Bot通信] 清理SSE服务器 {name} 失败: {e}")
        
        self.runners = {}
        self.sites = {}
        self.sse_clients = {}
        
        logger.debug("[Bot通信] SSE服务器管理器已关闭")
