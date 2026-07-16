import py_compile
import sys

files = [
    "utils/chat_utils.py",
    "db.py",
    "handlers/admin/__init__.py",
    "handlers/admin/common.py",
    "handlers/admin/ranks.py",
    "handlers/admin/warns.py",
    "handlers/admin/punish.py",
    "handlers/admin/misc.py",
    "handlers/callbacks/__init__.py",
    "handlers/callbacks/settings.py",
    "handlers/callbacks/admin.py",
    "handlers/callbacks/common.py",
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
