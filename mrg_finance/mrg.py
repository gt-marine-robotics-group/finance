"""
Entrypoint shim for legacy callers referencing mrg.py directly.
"""
from .cli import main, get_python_executable

if __name__ == "__main__":
    main()
