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
DOWNLOAD_DIR = "downloads"
USERNAME = "awu335"
PASSWORD = "Georgia_palace5"
BILL_URL = "https://gatech.campuslabs.com/engage/actionCenter/organization/mrg/budgeting/requests#/edit/344616"
BILL_NO = "Marine Robotics Group Fall 2025 Bill No. 7"

# Prompt if empty
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
    try:
        if isinstance(val, str):
            val = val.replace("$", "").replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return default

def click_save_button(driver, retries=5, wait_between=1.0):
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
            actions.move_to_element(save_button).perform()
            save_button.click()
            time.sleep(2)
            return True
        except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException):
            time.sleep(wait_between)
    return False

def clear_existing_line_items(driver, section_name):
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

# === Read CSV ===
df = pd.read_csv(CSV_FILE)
df.fillna("", inplace=True)
df.columns = df.columns.str.strip()

if "Cost" in df.columns:
    df["Cost"] = (
        df["Cost"]
        .astype(str)
        .str.replace(r"[^0-9.\-]", "", regex=True)
        .replace("", "0")
        .astype(float)
    )

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

# === Process Sections ===
for section_name, items in sections:
    print(f"\nProcessing section: {section_name}")
    clear_existing_line_items(driver, section_name)

    # === Process Sections ===
for section_name, items in sections:
    print(f"\nProcessing section: {section_name}")
    clear_existing_line_items(driver, section_name)

    # === Process Sections ===
for section_name, items in sections:
    print(f"\nProcessing section: {section_name}")
    clear_existing_line_items(driver, section_name)

    for _, item in items.iterrows():
        retries = 5
        for attempt in range(retries):
            try:
                # Re-fetch section and Add button each time
                section_anchor = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((
                        By.XPATH,
                        f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
                    ))
                )
                section_container = section_anchor.find_element(By.XPATH, "./../../..")
                add_item_button = section_container.find_element(By.XPATH, ".//a[contains(@class,'add')]")

                # Scroll and click via JS
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", add_item_button)
                driver.execute_script("arguments[0].click();", add_item_button)

                # Wait for form fields to appear
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "Name"))
                )

                print(f"  ✅ Clicked 'Add Line Item' for {item['Item Name']}")
                break
            except (StaleElementReferenceException, ElementClickInterceptedException):
                print(f"  ⚠️ Retry clicking Add Line Item ({attempt+1}/{retries})...")
                time.sleep(0.5)
        else:
            print(f"  ❌ Failed to click Add Line Item for {item['Item Name']}")
            continue

        # Fill form safely after waiting for fields
        name_field = driver.find_element(By.ID, "Name")
        name_field.clear()
        name_field.send_keys(str(item["Item Name"]))

        driver.find_element(By.ID, "Description").send_keys(str(item.get("Description", "")))
        quantity_field = driver.find_element(By.ID, "Quantity")
        quantity_field.clear()
        quantity_field.send_keys(str(safe_int(item.get("Quantity", 1))))
        price_field = driver.find_element(By.ID, "Price")
        price_field.clear()
        price_field.send_keys(str(safe_float(item.get("Cost", 0.0))))

        # Upload file if exists
        local_path = None
        for ext in [".png", ".jpg"]:
            candidate = os.path.join(DOWNLOAD_DIR, f"{item['Item Name']}{ext}")
            if os.path.exists(candidate):
                local_path = candidate
                break
        if local_path:
            file_input = driver.find_element(By.ID, "fileUploadInput")
            driver.execute_script("arguments[0].style.display='block';", file_input)
            file_input.send_keys(os.path.abspath(local_path))
            print(f"    Uploaded file: {os.path.basename(local_path)}")
        else:
            print(f"    ⚠️ No file for {item['Item Name']}")

        click_save_button(driver)

    print(f"✅ Finished section: {section_name}")

print(f"🎉 All items for Bill {BILL_NO} processed successfully.")
