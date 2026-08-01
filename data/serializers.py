"""
鏁版嵁搴忓垪鍖栧櫒 - 妯″瀷涓庡瓧鍏?JSON 浜掕浆
"""
import json
from typing import Any, Dict, List, Type, Optional
from data.models.base import BaseModel


class ModelSerializer:
    """妯″瀷搴忓垪鍖栧櫒"""

    @staticmethod
    def serialize(model: BaseModel) -> Dict[str, Any]:
        """搴忓垪鍖栨ā鍨嬩负瀛楀吀"""
        return model.to_dict()

    @staticmethod
    def serialize_list(models: List[BaseModel]) -> List[Dict[str, Any]]:
        """搴忓垪鍖栨ā鍨嬪垪琛?""
        return [m.to_dict() for m in models]

    @staticmethod
    def to_json(model: BaseModel, indent: int = 2) -> str:
        """搴忓垪鍖栦负 JSON 瀛楃涓?""
        return json.dumps(model.to_dict(), ensure_ascii=False, indent=indent, default=str)

    @staticmethod
    def deserialize(model_class: Type[BaseModel], data: Dict[str, Any]) -> BaseModel:
        """鍙嶅簭鍒楀寲涓烘ā鍨嬪疄渚?""
        return model_class.from_dict(data)

    @staticmethod
    def deserialize_list(model_class: Type[BaseModel], data_list: List[Dict[str, Any]]) -> List[BaseModel]:
        """鍙嶅簭鍒楀寲鍒楄〃"""
        return [model_class.from_dict(d) for d in data_list]
