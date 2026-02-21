from typing import Any, Dict, Optional
from astrbot.api import logger


class OneBotAPIHandler:
    def __init__(self, platform=None):
        self.platform = platform
        self._client = None
    
    def set_platform(self, platform):
        self.platform = platform
        self._client = None
    
    def _get_client(self):
        if self._client is not None:
            return self._client
        
        if self.platform is None:
            logger.debug("[OneBot API] 平台实例为空")
            return None
        
        try:
            if hasattr(self.platform, 'bot'):
                self._client = self.platform.bot
                logger.debug(f"[OneBot API] 从 platform.bot 获取客户端: {type(self._client)}")
            elif hasattr(self.platform, 'get_client'):
                self._client = self.platform.get_client()
                logger.debug(f"[OneBot API] 从 platform.get_client() 获取客户端: {type(self._client)}")
            elif hasattr(self.platform, 'client'):
                self._client = self.platform.client
                logger.debug(f"[OneBot API] 从 platform.client 获取客户端: {type(self._client)}")
            elif hasattr(self.platform, 'api'):
                self._client = self.platform
                logger.debug(f"[OneBot API] 使用 platform 本身作为客户端: {type(self._client)}")
            else:
                self._client = self.platform
                logger.debug(f"[OneBot API] 使用 platform 作为客户端(兜底): {type(self._client)}")
        except Exception as e:
            logger.error(f"[OneBot API] 获取客户端失败: {e}")
            return None
        
        return self._client
    
    async def call_api(self, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        client = self._get_client()
        
        if client is None:
            logger.warning(f"[OneBot API] 无法获取平台客户端，action: {action}")
            return self._error_response(1401, "无法获取平台客户端")
        
        try:
            if hasattr(client, 'api') and hasattr(client.api, 'call_action'):
                logger.debug(f"[OneBot API] 调用 client.api.call_action: {action}")
                result = await client.api.call_action(action, **(params or {}))
                return self._success_response(result)
            elif hasattr(client, 'call_action'):
                logger.debug(f"[OneBot API] 调用 client.call_action: {action}")
                result = await client.call_action(action, **(params or {}))
                return self._success_response(result)
            elif hasattr(client, 'call_api'):
                logger.debug(f"[OneBot API] 调用 client.call_api: {action}")
                result = await client.call_api(action, params)
                return self._success_response(result)
            else:
                logger.warning(f"[OneBot API] 客户端不支持API调用: {type(client)}, 可用属性: {dir(client)}")
                return self._error_response(1401, "客户端不支持API调用")
        except Exception as e:
            logger.error(f"[OneBot API] 调用API失败 {action}: {e}")
            return self._error_response(1400, str(e))
    
    def _success_response(self, data: Any = None) -> Dict[str, Any]:
        return {
            "status": "ok",
            "retcode": 0,
            "data": data if data is not None else {},
            "message": "",
            "wording": "",
            "stream": "normal-action"
        }
    
    def _error_response(self, retcode: int, message: str) -> Dict[str, Any]:
        return {
            "status": "failed",
            "retcode": retcode,
            "data": None,
            "message": message,
            "wording": message,
            "stream": "normal-action"
        }
    
    async def handle_request(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._error_response(1400, f"未实现的API: {action}")
