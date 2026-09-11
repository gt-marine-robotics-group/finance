import os
import tomllib
import importlib

def test_package_structure_and_packaging_declaration():
    """Verify that mrg_finance is properly packaged in pyproject.toml."""
    root_dir = os.path.dirname(os.path.dirname(__file__))
    pyproject_path = os.path.join(root_dir, "pyproject.toml")
    
    with open(pyproject_path, "rb") as f:
        config = tomllib.load(f)
        
    declared_packages = set(config["tool"]["setuptools"]["packages"])
    assert "mrg_finance" in declared_packages
    assert "web-app" in declared_packages
    
    # Verify script entry point points to mrg_finance.cli:main
    scripts = config["project"]["scripts"]
    assert scripts.get("mrg-finance") == "mrg_finance.cli:main"
    
    # Verify root has no stray loose python modules
    root_py_files = [
        f for f in os.listdir(root_dir)
        if f.endswith(".py") and not f.startswith("test") and f != "conftest.py"
    ]
    assert not root_py_files, f"Loose python files found in root: {root_py_files}"

def test_all_mrg_finance_modules_importable():
    """Verify that all modules in mrg_finance package can be imported without errors."""
    import mrg_finance
    expected_modules = [
        "cli",
        "automation",
        "automation_purchase",
        "automation_screenshots",
        "engage_bill_lookup",
        "order_excel_builder",
        "price_scraper",
        "review_server",
        "share_a_cart",
        "spreadsheet_utils",
    ]
    for mod in expected_modules:
        m = importlib.import_module(f"mrg_finance.{mod}")
        assert m is not None
