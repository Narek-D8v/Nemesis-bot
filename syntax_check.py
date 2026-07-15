import py_compile
import sys

files = [
    "utils/chat_utils.py",
    "db.py",
    "handlers/admin.py",
    "handlers/callbacks.py",
    "handlers/messages.py",
]

all_ok = True
for f in files:
    try:
        py_compile.compile(f, doraise=True)
        print(f"OK: {f}")
    except py_compile.PyCompileError as e:
        print(f"FAIL: {f}: {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
