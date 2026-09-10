import os
import tomllib

def test_all_root_py_modules_declared_in_pyproject():
    """Verify that all root python files are listed in pyproject.toml's py-modules."""
    root_dir = os.path.dirname(os.path.dirname(__file__))
    pyproject_path = os.path.join(root_dir, "pyproject.toml")
    
    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)
        
    declared_modules = set(config["tool"]["setuptools"]["py-modules"])
    
    # Scan root directory for python source files (excluding tests/scratch/setup/etc)
    root_py_files = [
        f[:-3] for f in os.listdir(root_dir)
        if f.endswith(".py") and not f.startswith("test") and f != "conftest.py"
    ]
    
    missing = [mod for mod in root_py_files if mod not in declared_modules]
    assert not missing, f"The following modules are missing from pyproject.toml py-modules: {missing}"
