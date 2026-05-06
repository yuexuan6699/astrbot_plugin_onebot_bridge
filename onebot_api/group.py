from typing import Any, Dict
from .base import OneBotAPIHandler


class GroupAPI(OneBotAPIHandler):
    async def handle_request(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if action == "get_group_list":
            return await self.get_group_list(params)
        elif action == "get_group_member_info":
            return await self.get_group_member_info(params)
        elif action == "get_group_member_list":
            return await self.get_group_member_list(params)
        else:
            return self._error_response(1400, f"未实现的群组API: {action}")
    
    async def get_group_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        call_params = {}
        if params.get("no_cache") is not None:
            call_params["no_cache"] = params["no_cache"]
        
        result = await self.call_api("get_group_list", call_params)
        return result
    
    async def get_group_member_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        group_id = params.get("group_id")
        user_id = params.get("user_id")
        
        if group_id is None:
            return self._error_response(1400, "缺少group_id参数")
        if user_id is None:
            return self._error_response(1400, "缺少user_id参数")
        
        call_params = {
            "group_id": group_id,
            "user_id": user_id
        }
        
        if params.get("no_cache") is not None:
            call_params["no_cache"] = params["no_cache"]
        
        result = await self.call_api("get_group_member_info", call_params)
        return result
    
    async def get_group_member_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        group_id = params.get("group_id")
        
        if group_id is None:
            return self._error_response(1400, "缺少group_id参数")
        
        call_params = {
            "group_id": group_id
        }
        
        if params.get("no_cache") is not None:
            call_params["no_cache"] = params["no_cache"]
        
        result = await self.call_api("get_group_member_list", call_params)
        return result
