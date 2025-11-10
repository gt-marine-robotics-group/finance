import os
import time
import pandas as pd
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
CSV_FILE = "Fall25_Bills_Budget.csv"
DOWNLOAD_DIR = "downloads"  # where screenshots are already saved
USERNAME = ""  # leave blank to prompt
PASSWORD = ""  # leave blank to prompt
BILL_URL = ""
BILL_NO = ""  # prompt dynamically

# === Prompt for credentials and bill info ===
if not USERNAME:
    USERNAME = input("Enter your username: ")
if not PASSWORD:
    PASSWORD = getpass.getpass("Enter your password: ")
if not BILL_URL:
    BILL_URL = input("Enter the URL of the specific bill to edit: ")
if not BILL_NO:
    BILL_NO = input("Enter the Bill Title: ").strip()

# === Utility functions ===
def safe_int(val, default=0):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default
    
def safe_float(val, default=0.0):
    """Convert value to float safely, stripping symbols and commas."""
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return default
    
def click_save_button(driver, retries=5, wait_between=1.0):
    """Try clicking the Save button up to `retries` times."""
    xpath = "//a[contains(@class,'button-success') and contains(text(),'Save')]"
    actions = ActionChains(driver)

    for attempt in range(retries):
        try:
            save_button = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.XPATH, xpath)
            )
            ng_disabled = save_button.get_attribute("ng-disabled")
            if ng_disabled and ng_disabled.lower() in ("true", "1"):
                print(f"    Save button disabled, waiting...")
                time.sleep(wait_between)
                continue

            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_button)
            actions.move_to_element(save_button).perform()
            save_button.click()
            print("    Clicked Save button")
            time.sleep(2)
            return True
        except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException):
            print(f"    Attempt {attempt+1}: Save button click failed, retrying...")
            time.sleep(wait_between)

    print("    ERROR: Could not click Save button after retries")
    return False

def clear_existing_line_items(driver, section_name):
    """Clear all existing line items from a section by opening each and pressing Delete."""
    print(f"  Clearing existing line items in section: {section_name}")
    try:
        section_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
            ))
        )
        section_container = section_link.find_element(By.XPATH, "./../../..")

        # Count once for display
        initial_items = section_container.find_elements(
            By.XPATH,
            ".//a[@ng-click='editLineItem(lineItem)']"
        )
        print(f"    Found {len(initial_items)} line items to delete.")

        deleted_count = 0
        while True:
            try:
                # Refetch each iteration (DOM changes after delete)
                line_items = section_container.find_elements(
                    By.XPATH,
                    ".//a[@ng-click='editLineItem(lineItem)']"
                )
                if not line_items:
                    break

                # Click the first available item
                item_link = line_items[-1]  # delete from bottom for stability
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", item_link)
                time.sleep(0.5)
                item_link.click()
                deleted_count += 1
                print(f"    Opened line item {deleted_count}")

                delete_button = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//a[@ng-click='deleteLineItem()']"
                    ))
                )
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", delete_button)
                time.sleep(0.3)
                delete_button.click()
                print(f"      ✅ Deleted line item {deleted_count}")

                # Wait for DOM update before re-querying
                time.sleep(1.5)

            except Exception as e:
                print(f"      ⚠️ Error deleting line item {deleted_count}: {e}")
                # Try refetching after a small delay
                time.sleep(1)
                continue

        print(f"    ✅ Finished clearing section '{section_name}'")

    except Exception as e:
        print(f"  ⚠️ ERROR in section '{section_name}': {e}")


# === Step 1: Read CSV ===
df = pd.read_csv(CSV_FILE)
df.fillna("", inplace=True)
df.columns = df.columns.str.strip()


# Normalize Cost column
if "Cost" in df.columns:
    df["Cost"] = (
        df["Cost"]
        .astype(str)
        .str.replace(r"[^0-9.\-]", "", regex=True)  # remove $, commas, etc.
        .replace("", "0")
        .astype(float)
    )


required_cols = {"Item Name", "Link", "Cost", "Bill Title"}
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"Missing columns in CSV: {missing}")


# Filter for chosen bill
mask = df["Bill Title"].astype(str).str.strip().str.lower() == BILL_NO.lower()
df_filtered = df[mask].copy()

if df_filtered.empty:
    print(f"⚠️ No entries found for  '{BILL_NO}' — exiting.")
    exit(0)

## Fill down Budget Section (only within filtered rows)
if "Budget Section" in df_filtered.columns:
    df_filtered["Budget Section"] = df_filtered["Budget Section"].replace("", pd.NA).ffill()

# Group items by section (only for the selected bill)
sections = []
if "Budget Section" in df_filtered.columns:
    grouped = df_filtered.groupby("Budget Section", sort=False)
    for section_name, items in grouped:
        sections.append((section_name, items))
else:
    print("⚠️ Cannot define sections because 'Budget Section' is missing in filtered data")


# === Step 2: Start Selenium and log in ===
options = webdriver.ChromeOptions()
options.add_argument("--incognito")
options.add_experimental_option("detach", True)

driver = webdriver.Chrome(options=options)
driver.get("https://gatech.campuslabs.com/engage/")

# Handle login
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

print("Please complete Duo MFA if prompted...")
WebDriverWait(driver, 60).until(EC.url_contains("gatech.campuslabs.com/engage"))

# === Step 3: Navigate to Bill ===
driver.get(BILL_URL)
budget_tab = WebDriverWait(driver, 20).until(
    EC.element_to_be_clickable((By.XPATH, "//a[contains(@analytics-event, 'Tab Budget')]"))
)
budget_tab.click()
time.sleep(5)

# === Step 4: Process each section and upload existing screenshots ===
for section_name, items in sections:
    try:
        print(f"\nProcessing section: {section_name}")

        section_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
            ))
        )
        clear_existing_line_items(driver, section_name)
        driver.execute_script("arguments[0].scrollIntoView(true);", section_link)
        time.sleep(1)

        for _, item in items.iterrows():
            print(f"  Processing item: {item['Item Name']}")

            # Click "Add Line Item"
            add_item_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]/../../..//a[contains(@class,'add')]"
                ))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", add_item_button)
            time.sleep(0.5)
            driver.execute_script("arguments[0].click();", add_item_button)
            print("    Clicked 'Add Line Item'")

            # Fill fields
            name_field = WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "Name")))
            name_field.clear()
            name_field.send_keys(str(item["Item Name"]))

            driver.find_element(By.ID, "Description").send_keys(str(item["Description"]))

            quantity_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "Quantity")))
            quantity_field.clear()
            quantity_field.send_keys(str(safe_int(item["Quantity"])))

            price_field = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "Price")))
            price_field.clear()
            price_field.send_keys(str(safe_float(item["Cost"])))

            # Upload screenshot (if exists)
            local_path = None
            for ext in [".png", ".jpg"]:
                candidate = os.path.join(DOWNLOAD_DIR, f"{item['Item Name']}{ext}")
                if os.path.exists(candidate):
                    local_path = candidate
                    break

            if local_path:
                file_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "fileUploadInput"))
                )
                driver.execute_script("arguments[0].style.display='block';", file_input)
                file_input.send_keys(os.path.abspath(local_path))
                print(f"    Uploaded file: {os.path.basename(local_path)}")
            else:
                print(f"    ⚠️ No file found for '{item['Item Name']}'")

            success = click_save_button(driver)
            if not success:
                print(f"    ERROR saving item '{item['Item Name']}'")

        print(f"✅ Finished section: {section_name}")

    except Exception as e:
        print(f"⚠️ ERROR in section '{section_name}': {e}")

print(f"🎉 All items for Bill {BILL_NO} processed successfully.")
