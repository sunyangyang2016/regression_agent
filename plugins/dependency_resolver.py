"""
依赖解析器 - 解析插件间依赖关系
"""
from typing import Dict, List, Set, Optional, Tuple


class DependencyResolver:
    """插件依赖解析器"""

    def resolve(self, dependencies: Dict[str, List[str]]) -> Tuple[bool, List[str]]:
        """解析依赖关系，返回拓扑排序结果"""
        # 检测循环依赖
        visited: Set[str] = set()
        in_stack: Set[str] = set()
        order: List[str] = []

        def dfs(node: str) -> bool:
            visited.add(node)
            in_stack.add(node)
            for dep in dependencies.get(node, []):
                if dep not in visited:
                    if dfs(dep):
                        return True
                elif dep in in_stack:
                    return True  # 发现循环
            in_stack.remove(node)
            order.append(node)
            return False

        for node in dependencies:
            if node not in visited:
                if dfs(node):
                    return False, ["检测到循环依赖"]

        return True, list(reversed(order))

    def check_satisfied(self, plugin_name: str, dependencies: List[str],
                        available: Dict[str, bool]) -> List[str]:
        """检查依赖是否满足"""
        missing = []
        for dep in dependencies:
            if dep not in available:
                missing.append(f"缺少依赖插件: {dep}")
            elif not available[dep]:
                missing.append(f"依赖插件未启用: {dep}")
        return missing