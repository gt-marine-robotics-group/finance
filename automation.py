import os
import time
import pandas as pd
from dotenv import load_dotenv
load_dotenv()
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
import getpass

# === CONFIG ===
DEFAULT_XLSX = os.path.expanduser(
    "~/Library/CloudStorage/OneDrive-GeorgiaInstituteofTechnology/"
    "Documents - Marine Robotics Group/OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx"
)
CSV_FILE = os.environ.get("FINANCE_XLSX_PATH", DEFAULT_XLSX)
SHEET_NAME = "Bills"
SCREENSHOT_DIR = "screenshots"
USERNAME = os.environ.get("ENGAGE_USERNAME", "")
PASSWORD = ""
BILL_URL = ""  # Auto-generated from Bill No. in spreadsheet
BILL_NO = ""   # Will prompt — shows available options

# Prompt if empty
if not USERNAME:
    USERNAME = input("Enter your username: ")
if not PASSWORD:
    PASSWORD = getpass.getpass("Enter your password: ")
if not BILL_NO:
    # Show available bill titles from spreadsheet
    if CSV_FILE.endswith(".xlsx"):
        _df_temp = pd.read_excel(CSV_FILE, sheet_name=SHEET_NAME)
    else:
        _df_temp = pd.read_csv(CSV_FILE)
    _df_temp.fillna("", inplace=True)
    _df_temp.columns = _df_temp.columns.str.strip()
    _titles = _df_temp["Bill Title"].astype(str).str.strip().unique()
    _skip = ("nan", "request", "liquid", "misc")
    _titles = [t for t in _titles if t and not any(t.lower().startswith(s) for s in _skip)]
    print("\nAvailable Bill Titles:")
    for i, t in enumerate(_titles, 1):
        # Find bill number for this title
        _mask = _df_temp["Bill Title"].astype(str).str.strip().str.lower() == t.lower()
        _bill_nos = _df_temp[_mask]["Bill No."].astype(str).str.replace(".0", "", regex=False).str.strip().unique()
        _bill_no_str = _bill_nos[0] if len(_bill_nos) > 0 and _bill_nos[0] not in ("", "nan") else "?"
        count = _mask.sum()
        print(f"  {i}. {t} (Bill #{_bill_no_str}, {count} items)")
    BILL_NO = input("\nEnter Bill Title (or number): ").strip()
    if BILL_NO.isdigit() and 1 <= int(BILL_NO) <= len(_titles):
        BILL_NO = _titles[int(BILL_NO) - 1]

    # Auto-generate BILL_URL from Bill No. in spreadsheet
    _mask = _df_temp["Bill Title"].astype(str).str.strip().str.lower() == BILL_NO.lower()
    _bill_nos = _df_temp[_mask]["Bill No."].astype(str).str.replace(".0", "", regex=False).str.strip().unique()
    _bill_num = _bill_nos[0] if len(_bill_nos) > 0 and _bill_nos[0] not in ("", "nan") else ""
    if _bill_num:
        BILL_URL = f"https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/budgeting/requests#/edit/{_bill_num}"
        print(f"\n  → Bill URL: {BILL_URL}")
    else:
        BILL_URL = input("Could not find Bill No. Enter URL manually: ").strip()

    del _df_temp, _titles

# === Utility functions ===
def safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default

def safe_float(val, default=0.0):
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return default


def click_save_button(driver, retries=5, wait_between=1.5):
    """Click Save and verify it actually saved by waiting for the form to close."""
    xpath = "//a[contains(@class,'button-success') and contains(text(),'Save')]"
    actions = ActionChains(driver)

    for attempt in range(retries):
        try:
            save_button = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.XPATH, xpath)
            )
            ng_disabled = save_button.get_attribute("ng-disabled")
            if ng_disabled and ng_disabled.lower() in ("true", "1"):
                time.sleep(wait_between)
                continue
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_button)
            time.sleep(0.3)
            actions.move_to_element(save_button).perform()
            save_button.click()

            # Wait for the form/modal to disappear (indicates save completed)
            try:
                WebDriverWait(driver, 15).until(
                    EC.invisibility_of_element_located((By.ID, "Name"))
                )
            except TimeoutException:
                # Form didn't close — try clicking again
                print("    ⚠️ Save form did not close, retrying...")
                time.sleep(wait_between)
                continue

            time.sleep(1.5)
            return True
        except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException):
            time.sleep(wait_between)
    return False


def verify_item_exists(driver, section_name, item_name):
    """Check if an item with the given name already exists in the section."""
    try:
        section_anchor = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
            ))
        )
        section_container = section_anchor.find_element(By.XPATH, "./../../..")
        line_items = section_container.find_elements(
            By.XPATH, ".//a[@ng-click='editLineItem(lineItem)']"
        )
        for li in line_items:
            # Normalize whitespace for comparison
            import re as _re
            normalized_name = _re.sub(r'\s+', ' ', item_name.lower().strip())
            normalized_li = _re.sub(r'\s+', ' ', li.text.lower().strip())
            if normalized_name in normalized_li:
                return True
    except Exception:
        pass
    return False


def count_section_items(driver, section_name):
    """Count the number of line items currently in a section."""
    try:
        section_anchor = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
            ))
        )
        section_container = section_anchor.find_element(By.XPATH, "./../../..")
        line_items = section_container.find_elements(
            By.XPATH, ".//a[@ng-click='editLineItem(lineItem)']"
        )
        return len(line_items)
    except Exception:
        return -1


def _find_screenshot(item_name, bill_title=""):
    """Find screenshot file for an item. Checks bill_title subdir first, then flat, then all subdirs."""
    for ext in [".png", ".jpg", ".jpeg", ".pdf"]:
        # Check bill_title subdirectory first (new structure)
        if bill_title:
            candidate = os.path.join(SCREENSHOT_DIR, bill_title, f"{item_name}{ext}")
            if os.path.exists(candidate):
                return candidate

        # Check flat structure (legacy)
        candidate = os.path.join(SCREENSHOT_DIR, f"{item_name}{ext}")
        if os.path.exists(candidate):
            return candidate

    # Search all subdirectories
    if os.path.isdir(SCREENSHOT_DIR):
        for subdir in os.listdir(SCREENSHOT_DIR):
            subdir_path = os.path.join(SCREENSHOT_DIR, subdir)
            if os.path.isdir(subdir_path):
                for ext in [".png", ".jpg", ".jpeg", ".pdf"]:
                    candidate = os.path.join(subdir_path, f"{item_name}{ext}")
                    if os.path.exists(candidate):
                        return candidate
    return None


def clear_existing_line_items(driver, section_name):
    """Remove all existing line items from a section."""
    while True:
        try:
            section_link = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
                ))
            )
            section_container = section_link.find_element(By.XPATH, "./../../..")
            line_items = section_container.find_elements(
                By.XPATH, ".//a[@ng-click='editLineItem(lineItem)']"
            )
            if not line_items:
                return
            item = line_items[-1]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", item)
            time.sleep(0.3)
            item.click()
            delete_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@ng-click='deleteLineItem()']"))
            )
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", delete_button)
            delete_button.click()
            time.sleep(1.0)
        except StaleElementReferenceException:
            time.sleep(0.5)
            continue
        except Exception:
            time.sleep(0.5)
            continue


# === Read spreadsheet ===
if CSV_FILE.endswith(".xlsx"):
    df = pd.read_excel(CSV_FILE, sheet_name=SHEET_NAME)
else:
    df = pd.read_csv(CSV_FILE)
df.fillna("", inplace=True)
df.columns = df.columns.str.strip()

if "Cost" in df.columns:
    df["Cost"] = (
        df["Cost"]
        .astype(str)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .replace({"": None, ".": None, "..": None})
    )
    df["Cost"] = pd.to_numeric(df["Cost"], errors="coerce").fillna(0.0)

required_cols = {"Item Name", "Link", "Cost", "Bill Title"}
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"Missing columns in CSV: {missing}")

mask = df["Bill Title"].astype(str).str.strip().str.lower() == BILL_NO.lower()
df_filtered = df[mask].copy()

if df_filtered.empty:
    print(f"No entries for '{BILL_NO}'")
    exit(0)

if "Budget Section" in df_filtered.columns:
    df_filtered["Budget Section"] = df_filtered["Budget Section"].replace("", pd.NA).ffill()
    grouped = df_filtered.groupby("Budget Section", sort=False)
    sections = [(name, items) for name, items in grouped]
else:
    sections = []

# === PRE-FLIGHT CHECK ===
print(f"\n{'='*60}")
print(f"📋 PRE-FLIGHT: {len(df_filtered)} items for '{BILL_NO}'")
print(f"{'='*60}")
for section_name, items in sections:
    print(f"\n  📁 {section_name} ({len(items)} items):")
    for _, row in items.iterrows():
        name = str(row.get("Item Name", "")).strip()
        cost = safe_float(row.get("Cost", 0))
        qty = safe_int(row.get("Quantity", 1))
        has_file = "📎" if _find_screenshot(name, BILL_NO) else "⚠️"
        print(f"    {has_file} {name:<40} ${cost:.2f} x{qty}")

total_cost = sum(safe_float(row.get("Cost", 0)) * safe_int(row.get("Quantity", 1)) for _, row in df_filtered.iterrows())
print(f"\n  💰 Total: ${total_cost:.2f}")
print(f"  📎 = file found, ⚠️ = no file in {SCREENSHOT_DIR}/")

confirm = input(f"\nProceed? [Y/n]: ").strip().lower()
if confirm == "n":
    print("Cancelled.")
    exit(0)

# === Selenium Setup ===
options = webdriver.ChromeOptions()
options.add_argument("--incognito")
options.add_experimental_option("detach", True)
driver = webdriver.Chrome(options=options)
driver.get("https://gatech.campuslabs.com/engage/")

# Login
discovery_bar = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "discovery-bar"))
)
parent_root = discovery_bar.find_element(By.ID, "parent-root")
shadow_root = driver.execute_script("return arguments[0].shadowRoot", parent_root)
sign_in_button = shadow_root.find_element(By.CSS_SELECTOR, "a[href*='/engage/account/login']")
sign_in_button.click()

username_input = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "username"))
)
username_input.send_keys(USERNAME)
password_input = driver.find_element(By.ID, "password")
password_input.send_keys(PASSWORD)
login_button = driver.find_element(By.NAME, "submitbutton")
login_button.click()
print("Complete Duo MFA if prompted...")
WebDriverWait(driver, 60).until(EC.url_contains("gatech.campuslabs.com/engage"))

driver.get(BILL_URL)
budget_tab = WebDriverWait(driver, 20).until(
    EC.element_to_be_clickable((By.XPATH, "//a[contains(@analytics-event, 'Tab Budget')]"))
)
budget_tab.click()
time.sleep(5)

# === Ask about existing items ===
print(f"\n⚠️  What to do with existing line items in each section?")
print(f"  1. Clear all existing items first (start fresh)")
print(f"  2. Keep existing items (only add new ones, skip duplicates)")
clear_choice = input("\nChoice [1/2]: ").strip()
CLEAR_EXISTING = clear_choice != "2"
if CLEAR_EXISTING:
    print("→ Will DELETE all existing items before adding.")
else:
    print("→ Will KEEP existing items and skip duplicates.")

# === Process Sections (SINGLE PASS with tracking & verification) ===
results = {"success": [], "failed": [], "skipped_duplicate": []}

for section_name, items in sections:
    print(f"\n{'='*60}")
    print(f"Processing section: {section_name} ({len(items)} items)")
    print(f"{'='*60}")

    if CLEAR_EXISTING:
        print(f"  🗑️  Clearing existing items...")
        clear_existing_line_items(driver, section_name)
        print(f"  ✅ Section cleared")

    items_list = list(items.iterrows())
    for item_idx, (_, item) in enumerate(items_list):
        item_name = " ".join(str(item["Item Name"]).split())  # normalize whitespace

        # --- DEDUPLICATION CHECK: skip if already in section ---
        if verify_item_exists(driver, section_name, item_name):
            print(f"  ⏭️  '{item_name}' already exists in section — skipping")
            results["skipped_duplicate"].append(item_name)
            continue

        count_before = count_section_items(driver, section_name)

        # --- ADD ITEM WITH RETRY ---
        max_retries = 3
        item_added = False

        for attempt in range(max_retries):
            try:
                # Re-check for duplicate before retry (prior attempt may have partially saved)
                if attempt > 0 and verify_item_exists(driver, section_name, item_name):
                    print(f"    ✅ '{item_name}' appeared after retry — already saved")
                    item_added = True
                    break

                # Re-fetch section and Add button each time
                section_anchor = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
                    ))
                )
                section_container = section_anchor.find_element(By.XPATH, "./../../..")
                add_item_button = section_container.find_element(By.XPATH, ".//a[contains(@class,'add')]")

                # Scroll and click
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", add_item_button)
                time.sleep(0.3)
                driver.execute_script("arguments[0].click();", add_item_button)

                # Wait for form fields to appear
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "Name"))
                )

                # Fill form
                name_field = driver.find_element(By.ID, "Name")
                name_field.clear()
                name_field.send_keys(item_name)

                desc_field = driver.find_element(By.ID, "Description")
                desc_field.clear()
                desc_field.send_keys(str(item.get("Description", "")))

                quantity_field = driver.find_element(By.ID, "Quantity")
                quantity_field.clear()
                quantity_field.send_keys(str(safe_int(item.get("Quantity", 1))))

                price_field = driver.find_element(By.ID, "Price")
                price_field.clear()
                price_field.send_keys(str(safe_float(item.get("Cost", 0.0))))

                # Upload file if exists
                local_path = _find_screenshot(item_name, BILL_NO)
                if local_path:
                    file_input = driver.find_element(By.ID, "fileUploadInput")
                    driver.execute_script("arguments[0].style.display='block';", file_input)
                    file_input.send_keys(os.path.abspath(local_path))
                    print(f"    📎 Uploaded: {os.path.basename(local_path)}")
                    time.sleep(1.5)  # wait for upload to register
                else:
                    print(f"    ⚠️ No file for '{item_name}'")

                # Save and verify
                save_ok = click_save_button(driver)
                if not save_ok:
                    print(f"    ⚠️ Save button failed on attempt {attempt+1}")
                    time.sleep(1)
                    continue

                # Verify the item actually appeared in the section
                time.sleep(1)
                count_after = count_section_items(driver, section_name)
                if count_after > count_before:
                    item_added = True
                    break
                elif verify_item_exists(driver, section_name, item_name):
                    item_added = True
                    break
                else:
                    print(f"    ⚠️ Item count didn't increase ({count_before} → {count_after}), retrying...")
                    time.sleep(1)

            except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException) as e:
                print(f"    ⚠️ Attempt {attempt+1}/{max_retries} failed: {type(e).__name__}")
                time.sleep(1.5)

        if item_added:
            print(f"  ✅ [{item_idx+1}/{len(items_list)}] Added: {item_name}")
            results["success"].append(item_name)
        else:
            print(f"  ❌ [{item_idx+1}/{len(items_list)}] FAILED: {item_name}")
            results["failed"].append(item_name)

    # Section-level verification
    final_count = count_section_items(driver, section_name)
    print(f"\n  📊 Section '{section_name}': {final_count} items in UI (expected {len(items_list)})")

# === Final Report ===
print(f"\n{'='*60}")
print(f"🎉 COMPLETED — Bill: {BILL_NO}")
print(f"{'='*60}")
print(f"  ✅ Successfully added: {len(results['success'])}")
print(f"  ⏭️  Skipped (duplicate): {len(results['skipped_duplicate'])}")
print(f"  ❌ Failed: {len(results['failed'])}")
if results["failed"]:
    print(f"\n  Failed items:")
    for name in results["failed"]:
        print(f"    - {name}")
print()
