import py_compile
import sys
import os

all_ok = True
for root, dirs, files in os.walk("."):
    dirs[:] = [d for d in dirs if d != "__pycache__"]
    for f in files:
        if f.endswith(".py") and f != "syntax_check.py":
            path = os.path.join(root, f)
            try:
                py_compile.compile(path, doraise=True)
                print(f"OK: {path}")
            except py_compile.PyCompileError as e:
                print(f"FAIL: {path}: {e}")
                all_ok = False

sys.exit(0 if all_ok else 1)
