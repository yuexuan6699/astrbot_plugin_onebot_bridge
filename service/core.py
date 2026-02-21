import asyncio
import time
from typing import Dict, Any, Optional, List

from astrbot.api.event import AstrMessageEvent
from astrbot.api import logger

from .websocket_manager import WebSocketManager
from .http_server_manager import HTTPServerManager
from .sse_server_manager import SSEServerManager
from .http_client_manager import HTTPClientManager
from .ws_server_manager import WSServerManager


class BotCommunicationCore:
    def __init__(self, config: Dict[str, Any], bot_id: str, send_message_callback, platform=None):
        self.config = config
        self.bot_id = bot_id
        self.send_message_callback = send_message_callback
        self.platform = platform
        
        self.ws_manager = WebSocketManager(config, bot_id, send_message_callback)
        self.http_server_manager = HTTPServerManager(config, bot_id, send_message_callback)
        self.sse_server_manager = SSEServerManager(config, bot_id, send_message_callback)
        self.http_client_manager = HTTPClientManager(config, bot_id, send_message_callback)
        self.ws_server_manager = WSServerManager(config, bot_id, send_message_callback)
        
        self.debug = config.get("debug", False)
        
        self._init_api_handlers()
    
    def _init_api_handlers(self):
        from ..onebot_api import MessageAPI, GroupAPI, FriendAPI
        
        message_api = MessageAPI(self.platform)
        group_api = GroupAPI(self.platform)
        friend_api = FriendAPI(self.platform)
        
        self.ws_manager.set_api_handlers(message_api, group_api, friend_api)
        self.http_server_manager.set_api_handlers(message_api, group_api, friend_api)
        self.sse_server_manager.set_api_handlers(message_api, group_api, friend_api)
        self.ws_server_manager.set_api_handlers(message_api, group_api, friend_api)
        
        self.message_api = message_api
        self.group_api = group_api
        self.friend_api = friend_api
    
    def set_platform(self, platform):
        self.platform = platform
        if self.message_api:
            self.message_api.set_platform(platform)
        if self.group_api:
            self.group_api.set_platform(platform)
        if self.friend_api:
            self.friend_api.set_platform(platform)
    
    async def initialize(self):
        if self.ws_manager.websocket_clients:
            await self.ws_manager.connect_all()
        if self.http_server_manager.http_servers:
            await self.http_server_manager.start_all()
        if self.sse_server_manager.sse_servers:
            await self.sse_server_manager.start_all()
        if self.http_client_manager.http_clients:
            await self.http_client_manager.connect_all()
        if self.ws_server_manager.ws_servers:
            await self.ws_server_manager.start_all()
        logger.debug("[Bot通信] 所有通信管理器已初始化")
    
    async def convert_and_forward(self, event: AstrMessageEvent, text: str):
        if not text or not text.strip():
            logger.debug(f"[Bot通信] 忽略空白消息转发: {text}")
            return
            
        try:
            message_type = "group" if event.get_group_id() else "private"
            
            forward_message = {
                "post_type": "message",
                "message_type": message_type,
                "user_id": int(event.get_sender_id()),
                "self_id": self.bot_id,
                "message": [
                    {
                        "type": "text",
                        "data": {
                            "text": text
                        }
                    }
                ],
                "raw_message": text,
                "sub_type": "normal",
                "message_id": event.message_obj.message_id,
                "time": int(time.time()),
            }
            
            if message_type == "group":
                forward_message["group_id"] = int(event.get_group_id())
            
            sender_info = self._get_sender_info(event)
            forward_message["sender"] = sender_info
            
            await self._broadcast_message(forward_message)
            
        except Exception as e:
            logger.error(f"[Bot通信] 转发消息失败: {e}")
    
    async def forward_event(self, event: AstrMessageEvent, message_str: str = None):
        try:
            forward_message = self._build_forward_message(event, message_str)
            if forward_message:
                await self._broadcast_message(forward_message)
        except Exception as e:
            logger.error(f"[Bot通信] 转发事件失败: {e}")
    
    async def _broadcast_message(self, message: Dict[str, Any]):
        tasks = [
            self.ws_manager.send_message(message),
            self.http_server_manager.send_message(message),
            self.sse_server_manager.send_message(message),
            self.http_client_manager.send_message(message),
            self.ws_server_manager.send_message(message),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        total_success = sum(r for r in results if isinstance(r, int) and r > 0)
        if self.debug:
            logger.debug(f"[Bot通信] 消息已广播到 {total_success} 个目标")
    
    def _build_forward_message(self, event: AstrMessageEvent, message_str: str = None) -> Optional[Dict[str, Any]]:
        try:
            message_type = "group" if event.get_group_id() else "private"
            
            message_chain = event.get_messages()
            onebot_message = self._convert_message_chain(message_chain)
            
            forward_message = {
                "post_type": "message",
                "message_type": message_type,
                "user_id": int(event.get_sender_id()),
                "self_id": self.bot_id,
                "message": onebot_message,
                "raw_message": message_str or event.message_str,
                "sub_type": "normal",
                "message_id": event.message_obj.message_id,
                "time": int(time.time()),
            }
            
            if message_type == "group":
                forward_message["group_id"] = int(event.get_group_id())
            
            sender_info = self._get_sender_info(event)
            forward_message["sender"] = sender_info
            
            return forward_message
            
        except Exception as e:
            logger.error(f"[Bot通信] 构建转发消息失败: {e}")
            return None
    
    def _convert_message_chain(self, message_chain: List[Any]) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        
        try:
            for component in message_chain:
                component_type = type(component).__name__
                
                if component_type == "Plain":
                    messages.append({
                        "type": "text",
                        "data": {"text": component.text}
                    })
                elif component_type == "Image":
                    url = component.url if hasattr(component, "url") else component.file
                    messages.append({
                        "type": "image",
                        "data": {"url": url, "file": url}
                    })
                elif component_type == "At":
                    messages.append({
                        "type": "at",
                        "data": {"qq": str(component.qq)}
                    })
                elif component_type == "Face":
                    messages.append({
                        "type": "face",
                        "data": {"id": component.id}
                    })
                elif component_type == "Record":
                    url = component.url if hasattr(component, "url") else component.file
                    messages.append({
                        "type": "record",
                        "data": {"url": url, "file": url}
                    })
                elif component_type == "Video":
                    url = component.url if hasattr(component, "url") else component.file
                    messages.append({
                        "type": "video",
                        "data": {"url": url, "file": url}
                    })
                elif component_type == "Reply":
                    messages.append({
                        "type": "reply",
                        "data": {"id": component.id}
                    })
                elif component_type == "File":
                    messages.append({
                        "type": "file",
                        "data": {
                            "name": component.name if hasattr(component, "name") else "",
                            "url": component.url if hasattr(component, "url") else ""
                        }
                    })
                elif component_type == "Poke":
                    messages.append({
                        "type": "poke",
                        "data": {
                            "type": getattr(component, "poke_type", ""),
                            "id": str(getattr(component, "poke_id", ""))
                        }
                    })
                elif component_type == "Dice":
                    messages.append({
                        "type": "dice",
                        "data": {"result": getattr(component, "result", 1)}
                    })
                elif component_type == "Rps":
                    messages.append({
                        "type": "rps",
                        "data": {"result": getattr(component, "result", 0)}
                    })
                elif component_type == "Location":
                    messages.append({
                        "type": "location",
                        "data": {
                            "lat": getattr(component, "lat", 0),
                            "lon": getattr(component, "lon", 0),
                            "title": getattr(component, "title", ""),
                            "content": getattr(component, "content", "")
                        }
                    })
                elif component_type == "Json":
                    messages.append({
                        "type": "json",
                        "data": {"data": getattr(component, "data", "")}
                    })
                elif component_type == "Xml":
                    messages.append({
                        "type": "xml",
                        "data": {"data": getattr(component, "data", "")}
                    })
                elif component_type == "Forward":
                    messages.append({
                        "type": "forward",
                        "data": {"id": getattr(component, "id", "")}
                    })
                elif component_type == "Node":
                    messages.append({
                        "type": "node",
                        "data": {
                            "user_id": getattr(component, "user_id", 0),
                            "nickname": getattr(component, "nickname", ""),
                            "content": getattr(component, "content", "")
                        }
                    })
                elif component_type == "Music":
                    messages.append({
                        "type": "music",
                        "data": {
                            "type": getattr(component, "music_type", "custom"),
                            "url": getattr(component, "url", ""),
                            "audio": getattr(component, "audio", ""),
                            "title": getattr(component, "title", ""),
                            "image": getattr(component, "image", "")
                        }
                    })
                elif component_type == "Contact":
                    messages.append({
                        "type": "contact",
                        "data": {
                            "type": getattr(component, "contact_type", "qq"),
                            "id": str(getattr(component, "contact_id", ""))
                        }
                    })
                else:
                    if hasattr(component, "text"):
                        messages.append({
                            "type": "text",
                            "data": {"text": str(component.text)}
                        })
                    elif hasattr(component, "__str__"):
                        messages.append({
                            "type": "text",
                            "data": {"text": str(component)}
                        })
        except Exception as e:
            logger.error(f"[Bot通信] 转换消息链失败: {e}")
        
        if not messages:
            messages.append({
                "type": "text",
                "data": {"text": ""}
            })
        
        return messages
    
    def _get_sender_info(self, event: AstrMessageEvent) -> Dict[str, Any]:
        sender_info = {
            "user_id": int(event.get_sender_id()),
            "nickname": event.get_sender_name() or "未知用户",
            "card": "",
            "sex": "unknown",
            "age": 0,
            "area": "",
            "level": 0,
            "role": "member",
            "title": ""
        }
        
        try:
            message_obj = event.message_obj
            if hasattr(message_obj, "sender"):
                sender = message_obj.sender
                if hasattr(sender, "nickname"):
                    sender_info["nickname"] = sender.nickname
                if hasattr(sender, "card"):
                    sender_info["card"] = sender.card or ""
                if hasattr(sender, "role"):
                    sender_info["role"] = sender.role or "member"
        except Exception:
            pass
        
        return sender_info
    
    async def close(self):
        try:
            await self.ws_manager.close()
            await self.http_server_manager.close()
            await self.sse_server_manager.close()
            await self.http_client_manager.close()
            await self.ws_server_manager.close()
            logger.debug("[Bot通信] Bot通信核心服务已关闭")
        except Exception as e:
            logger.error(f"[Bot通信] 关闭Bot通信核心服务失败: {e}")
