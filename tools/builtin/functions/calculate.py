"""
calculate - 数学计算工具

可直接调用:
    calculate(expression) -> str
"""
import math

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "description": "执行数学表达式计算，支持加减乘除、幂运算等",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "数学表达式，如 1+2*3、2**10、sqrt(16)"}
                },
                "required": ["expression"]
            }
        },
        "display": {"name_cn": "数学计算", "description_cn": "安全执行数学表达式计算", "icon": "fa-calculator"}
    }
]

_SAFE_BUILTINS = {"abs": abs, "round": round, "int": int, "float": float, "min": min, "max": max, "sum": sum, "pow": pow}
_SAFE_MATH = {"sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "log": math.log, "log10": math.log10, "exp": math.exp, "floor": math.floor, "ceil": math.ceil, "pi": math.pi, "e": math.e, "degrees": math.degrees, "radians": math.radians}
_SAFE_NS = {**_SAFE_BUILTINS, **_SAFE_MATH}

def calculate(args):
    """执行数学计算 — 可直接调用
    
    @param args: dict - {"expression": "1+2*3"}
    @return str - 计算结果
    """
    if isinstance(args, str):
        return calculate({"expression": args})
    expr = args.get("expression", "") if isinstance(args, dict) else args
    if not expr:
        return "请提供表达式"
    try:
        return f"结果: {eval(expr, {'__builtins__': {}}, _SAFE_NS)}"
    except ZeroDivisionError:
        return "除数不能为 0"
    except Exception as e:
        return f"计算失败: {e}"