import ast
import math
import operator
import random
import string


def fmt_time(s):
    s = int(s)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f"{d}д")
    if h:
        parts.append(f"{h}ч")
    if m:
        parts.append(f"{m}м")
    if s or not parts:
        parts.append(f"{s}с")
    return " ".join(parts)


def progress_bar(val, mx, width=10):
    filled = int(width * val / max(mx, 1))
    return "█" * filled + "░" * (width - filled)


def format_bytes(n):
    n = float(n)
    for unit in ('Б', 'КБ', 'МБ', 'ГБ'):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} ТБ"


class SafeEvalError(ValueError):
    pass


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.BitXor: operator.xor,
    ast.BitAnd: operator.and_,
    ast.BitOr: operator.or_,
    ast.LShift: operator.lshift,
    ast.RShift: operator.rshift,
}

_SAFE_FUNCS = {
    'abs': abs,
    'pow': pow,
    'round': round,
    'min': min,
    'max': max,
    'sqrt': math.sqrt,
    'sin': math.sin,
    'cos': math.cos,
    'tan': math.tan,
    'log': math.log,
    'log2': math.log2,
    'log10': math.log10,
    'floor': math.floor,
    'ceil': math.ceil,
    'factorial': math.factorial,
    'gcd': math.gcd,
    'hypot': math.hypot,
    'pi': math.pi,
    'e': math.e,
    'degrees': math.degrees,
    'radians': math.radians,
}


def _eval_ast(node):
    if isinstance(node, ast.Expression):
        return _eval_ast(node.body)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise SafeEvalError(f"Недопустимая константа: {type(node.value).__name__}")
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise SafeEvalError(f"Недопустимая операция: {op_type.__name__}")
        left = _eval_ast(node.left)
        right = _eval_ast(node.right)
        return _SAFE_OPS[op_type](left, right)
    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPS:
            raise SafeEvalError(f"Недопустимая унарная операция: {op_type.__name__}")
        return _SAFE_OPS[op_type](_eval_ast(node.operand))
    if isinstance(node, ast.Call):
        func_node = node.func
        if not isinstance(func_node, ast.Name):
            raise SafeEvalError("Разрешены только прямые вызовы функций")
        func_name = func_node.id
        if func_name not in _SAFE_FUNCS:
            raise SafeEvalError(f"Недопустимая функция: {func_name}")
        args = [_eval_ast(a) for a in node.args]
        return _SAFE_FUNCS[func_name](*args)
    if isinstance(node, ast.List):
        return [_eval_ast(el) for el in node.elts]
    if isinstance(node, ast.Tuple):
        return tuple(_eval_ast(el) for el in node.elts)
    raise SafeEvalError(f"Недопустимое выражение: {type(node).__name__}")


def safe_eval(expr: str):
    try:
        tree = ast.parse(expr.strip(), mode='eval')
        result = _eval_ast(tree)
        if isinstance(result, float):
            if math.isinf(result) or math.isnan(result):
                return "∞"
            return round(result, 10)
        return result
    except SafeEvalError:
        return None
    except Exception:
        return None


def caesar(text, shift, dec=False):
    if dec:
        shift = -shift
    out = []
    for c in text:
        if 'А' <= c <= 'я' or c in 'ёЁ':
            base = ord('А' if c.isupper() or c == 'Ё' else 'а')
            size = 33
            out.append(chr((ord(c) - base + shift) % size + base))
        elif c.isalpha():
            base = ord('A' if c.isupper() else 'a')
            out.append(chr((ord(c) - base + shift) % 26 + base))
        else:
            out.append(c)
    return ''.join(out)


_MORSE = {
    'A': '.-', 'B': '-...', 'C': '-.-.', 'D': '-..', 'E': '.', 'F': '..-.',
    'G': '--.', 'H': '....', 'I': '..', 'J': '.---', 'K': '-.-', 'L': '.-..',
    'M': '--', 'N': '-.', 'O': '---', 'P': '.--.', 'Q': '--.-', 'R': '.-.',
    'S': '...', 'T': '-', 'U': '..-', 'V': '...-', 'W': '.--', 'X': '-..-',
    'Y': '-.--', 'Z': '--..',
    '0': '-----', '1': '.----', '2': '..---', '3': '...--', '4': '....-',
    '5': '.....', '6': '-....', '7': '--...', '8': '---..', '9': '----.',
    ' ': '/'
}


def morse_enc(t):
    return ' '.join(_MORSE.get(c.upper(), '?') for c in t)


def gen_pwd(n=16, sym=True):
    pool = string.ascii_letters + string.digits + ("!@#$%^&*()-_=+[]{}|;:,.<>?" if sym else "")
    return ''.join(random.SystemRandom().choice(pool) for _ in range(n))


def vigenere(text, key, dec=False):
    key = key.upper()
    out, ki = [], 0
    for c in text:
        if c.isalpha():
            shift = ord(key[ki % len(key)]) - ord('A')
            if dec:
                shift = -shift
            base = ord('A' if c.isupper() else 'a')
            out.append(chr((ord(c) - base + shift) % 26 + base))
            ki += 1
        else:
            out.append(c)
    return ''.join(out)
