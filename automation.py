import os
import sys
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
import time
import re
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

# --- Fresh sync from SharePoint ---
import sys
if "--fresh" in sys.argv or "-f" in sys.argv:
    print("Downloading fresh xlsx from SharePoint...")
    import subprocess
    result = subprocess.run(
        ["rclone", "copy", "--checksum",
         "onedrive:OPS-1 Operations/FY27 Finances/FY27_Bills_Budget.xlsx",
         os.path.dirname(CSV_FILE)],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode == 0:
        print("✅ Fresh copy downloaded")
    else:
        print(f"⚠️ rclone failed: {result.stderr.strip()}")
        print("Continuing with local copy...")
    # Also sync screenshots
    result2 = subprocess.run(
        ["rclone", "copy", "--checksum",
         "onedrive:OPS-1 Operations/FY27 Finances/screenshots",
         SCREENSHOT_DIR],
        capture_output=True, text=True, timeout=60
    )
    if result2.returncode == 0:
        print("✅ Screenshots synced")
    sys.argv.remove("--fresh") if "--fresh" in sys.argv else sys.argv.remove("-f")

# Prompt if empty
if not USERNAME:
    USERNAME = input("Enter your username: ")
if not PASSWORD:
    PASSWORD = getpass.getpass("Enter GT password (for CampusLabs + Duo MFA): ")
if not BILL_NO:
    if CSV_FILE.endswith(".xlsx"):
        _df_temp = pd.read_excel(CSV_FILE, sheet_name=SHEET_NAME)
    else:
        _df_temp = pd.read_csv(CSV_FILE)
    _df_temp = _df_temp.astype(object).fillna("")
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

    # Interactive Screenshot Audit & On-Demand Capture
    safe_bill = "".join(c if c.isalnum() or c in " -_" else "_" for c in BILL_NO)
    bill_items_df = _df_temp[_df_temp["Bill Title"].astype(str).str.strip().str.lower() == BILL_NO.lower()]
    
    missing_items = []
    existing_items = []
    
    for _, row in bill_items_df.iterrows():
        item_name = str(row.get("Item Name", "")).strip()
        url = str(row.get("Link", "")).strip()
        if item_name:
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in item_name)
            shot_path = os.path.join(SCREENSHOT_DIR, safe_bill, f"{safe_name}.png")
            if os.path.exists(shot_path):
                existing_items.append((item_name, url, shot_path))
            else:
                missing_items.append((item_name, url, shot_path))

    print(f"\n📸 Screenshot Audit for '{BILL_NO}':")
    print(f"   ✅ Existing ground-truth screenshots: {len(existing_items)}")
    print(f"   ⚠️ Missing screenshots: {len(missing_items)}")

    items_to_capture = []
    if missing_items:
        print("\nItems missing screenshots:")
        for m_name, m_url, _ in missing_items:
            print(f"   - {m_name} ({'Link available' if m_url else 'No link'})")
        
        take_missing = input("\nCapture missing screenshots now via headless Chrome? (Y/n): ").strip().lower()
        if take_missing in ("", "y", "yes"):
            items_to_capture = missing_items
    else:
        retake = input("\nAll screenshots exist! Re-capture screenshots anyway? (y/N): ").strip().lower()
        if retake in ("y", "yes"):
            items_to_capture = existing_items

    if items_to_capture:
        print(f"\n🚀 Launching headless Chrome to capture {len(items_to_capture)} screenshot(s)...")
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        
        c_opts = Options()
        c_opts.add_argument("--headless=new")
        c_opts.add_argument("--window-size=1920,1080")
        c_opts.add_argument("--no-sandbox")
        c_opts.add_argument("--disable-dev-shm-usage")
        
        try:
            c_driver = webdriver.Chrome(service=Service(), options=c_opts)
            c_driver.set_page_load_timeout(20)
            
            bill_shot_dir = os.path.join(SCREENSHOT_DIR, safe_bill)
            os.makedirs(bill_shot_dir, exist_ok=True)
            
            for m_name, m_url, shot_path in items_to_capture:
                if not m_url or not m_url.startswith("http"):
                    print(f"   ⚠️ Skipping '{m_name}': no valid URL link")
                    continue
                print(f"   📸 Capturing '{m_name}'...", end=" ", flush=True)
                try:
                    c_driver.get(m_url)
                    time.sleep(4)
                    c_driver.save_screenshot(shot_path)
                    print(f"✅ Saved ({os.path.basename(shot_path)})")
                except Exception as err:
                    print(f"❌ Failed: {err}")
            
            c_driver.quit()
            from automation_screenshots import sync_screenshots_to_sharepoint
            sync_screenshots_to_sharepoint()
        except Exception as chrome_err:
            print(f"⚠️ Could not start Chrome for screenshots: {chrome_err}")

    # Launch Side-by-Side Review GUI (auto-starts review_server on port 8321)
    try:
        from automation_screenshots import generate_review_html, find_screenshots_for_item, parse_price, REVIEW_HTML
        review_data = []
        for _, row in bill_items_df.iterrows():
            item_name = str(row.get("Item Name", "")).strip()
            url = str(row.get("Link", "")).strip()
            csv_cost = str(row.get("Cost", "")).strip()
            old_shot, new_shot = find_screenshots_for_item(BILL_NO, item_name)
            parsed = parse_price(csv_cost)
            status = "needs_review" if old_shot and new_shot else ("ok" if new_shot else "failed")
            review_data.append({
                "item_name": item_name, "url": url, "csv_cost": csv_cost,
                "scraped_price": f"${parsed:.2f}" if parsed else "", "parsed_price": parsed,
                "confidence": "high", "screenshot": os.path.basename(new_shot) if new_shot else None,
                "old_screenshot": old_shot, "new_screenshot": new_shot, "status": status,
            })
        generate_review_html(review_data, BILL_NO, REVIEW_HTML)
        from review_server import launch_review_server_and_browser
        launch_review_server_and_browser(REVIEW_HTML)
        input("\n   Press Enter after reviewing & saving prices on the review page → ")
    except Exception as ex:
        print(f"  ⚠️ Review GUI notice: {ex}")
    print("   Verify screenshots and prices on side-by-side review cards before proceeding.")

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
    """Find screenshot file for an item using exact and space-normalized flexible matching."""
    if not item_name:
        return None

    import re
    safe_name = re.sub(r'[<>:"/\\|?*]', '_', item_name)
    dirs_to_check = []
    if bill_title:
        dirs_to_check.append(os.path.join(SCREENSHOT_DIR, bill_title))
    dirs_to_check.append(SCREENSHOT_DIR)

    if os.path.isdir(SCREENSHOT_DIR):
        for sub in os.listdir(SCREENSHOT_DIR):
            sp = os.path.join(SCREENSHOT_DIR, sub)
            if os.path.isdir(sp) and sp not in dirs_to_check:
                dirs_to_check.append(sp)

    for d in dirs_to_check:
        for ext in [".png", ".jpg", ".jpeg", ".pdf"]:
            exact = os.path.join(d, f"{safe_name}{ext}")
            if os.path.exists(exact):
                return exact
            exact_orig = os.path.join(d, f"{item_name}{ext}")
            if os.path.exists(exact_orig):
                return exact_orig

            # Flexible whitespace/case match
            norm_target = re.sub(r'\s+', ' ', f"{safe_name}{ext}").lower()
            try:
                for f in os.listdir(d):
                    if re.sub(r'\s+', ' ', f).lower() == norm_target:
                        return os.path.join(d, f)
            except Exception:
                pass
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
df = df.astype(object).fillna("")
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
WebDriverWait(driver, 20).until(
    lambda d: d.execute_script("return !!document.getElementById('discovery-bar')")
)

sign_in_button = None
try:
    discovery_bar = driver.find_element(By.ID, "discovery-bar")
    parent_root = discovery_bar.find_element(By.ID, "parent-root")
    shadow_root = driver.execute_script("return arguments[0].shadowRoot", parent_root)
    sign_in_candidates = shadow_root.find_elements(By.CSS_SELECTOR, "a[href*='/engage/account/login'], a[href*='account/login'], button, [role='button']")
    for candidate in sign_in_candidates:
        href = (candidate.get_attribute("href") or "").lower()
        text = (candidate.text or "").lower()
        if "account/login" in href or "sign in" in text or "log in" in text:
            sign_in_button = candidate
            break
except Exception:
    sign_in_button = None

if sign_in_button is None:
    try:
        sign_in_button = driver.find_element(By.CSS_SELECTOR, "a[href*='/engage/account/login']")
    except Exception:
        sign_in_button = driver.find_element(By.XPATH, "//a[contains(@href, '/engage/account/login') or contains(normalize-space(.), 'Sign In') or contains(normalize-space(.), 'Log In')][1]")

if sign_in_button is None:
    raise RuntimeError("Could not locate the Engage sign-in link")

try:
    sign_in_button.click()
except Exception:
    driver.execute_script("arguments[0].click();", sign_in_button)

username_input = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "username"))
)
username_input.send_keys(USERNAME)
password_input = driver.find_element(By.ID, "password")
password_input.send_keys(PASSWORD)
login_button = driver.find_element(By.NAME, "submitbutton")
login_button.click()
print("\nComplete Duo MFA if prompted...")
try:
    WebDriverWait(driver, 180).until(EC.url_contains("gatech.campuslabs.com/engage"))
except TimeoutException:
    print("  ⏳ Duo MFA wait timed out automatically.")
    input("  Press Enter after completing Duo MFA in your browser window → ")
print("✅ Logged in\n")

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
