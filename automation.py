import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException
import zipfile
import xml.etree.ElementTree as ET

# === CONFIG ===
EXCEL_FILE = "Fall25_Bills_Budget.xlsx"
DOWNLOAD_DIR = "downloads"
USERNAME = "awu335"  # leave blank to prompt
PASSWORD = "Georgia_palace5"  # leave blank to prompt
BILL_URL = "https://gatech.campuslabs.com/engage/actionCenter/organization/mrg/budgeting/requests#/edit/326798"

# Prompt for credentials if blank
if not USERNAME:
    USERNAME = input("Enter your username: ")
if not PASSWORD:
    import getpass
    PASSWORD = getpass.getpass("Enter your password: ")
if not BILL_URL:
    BILL_URL = input("Enter the URL of the specific bill to edit: ")


# Save button Handler

def click_save_button(driver, retries=5, wait_between=1.0):
    xpath = "//a[contains(@class,'button-success') and contains(text(),'Save')]"
    actions = ActionChains(driver)

    for attempt in range(retries):
        try:
            # Wait until button is present and enabled
            save_button = WebDriverWait(driver, 10).until(
                lambda d: d.find_element(By.XPATH, xpath)
            )
            ng_disabled = save_button.get_attribute("ng-disabled")
            if ng_disabled and ng_disabled.lower() in ("true", "1"):
                print(f"    Save button disabled, waiting...")
                time.sleep(wait_between)
                continue

            # Scroll and move to button
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", save_button)
            actions.move_to_element(save_button).perform()
            save_button.click()
            print("    Clicked Save button")
            
            # Give some time for form to process
            time.sleep(2)
            

            return True

        except (StaleElementReferenceException, ElementClickInterceptedException, TimeoutException):
            print(f"    Attempt {attempt+1}: Save button click failed, retrying...")
            time.sleep(wait_between)

    print("    ERROR: Could not click Save button after retries")
    return False



def read_first_sheet_raw(path):
    wb = open_workbook_auto(path)
    sheet = wb.sheet_names()[0]
    rows = list(wb[sheet].to_records())

    # Find the max number of columns
    max_len = max(len(r) for r in rows)

    # Pad each row with None so all rows have the same length
    normalized = [list(r) + [None]*(max_len - len(r)) for r in rows]

    # First row = header
    header = normalized[0]
    data = normalized[1:]

    return pd.DataFrame(data, columns=header)
# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# === Step 2: Start Selenium Browser ===
options = webdriver.ChromeOptions()
options.add_argument("--incognito")
options.add_experimental_option("detach", True)  # keep Chrome open

driver = webdriver.Chrome(options=options)
driver.get("https://gatech.campuslabs.com/engage/")

# Handle Sign In via shadow DOM
discovery_bar = WebDriverWait(driver, 20).until(
    EC.presence_of_element_located((By.ID, "discovery-bar"))
)
parent_root = discovery_bar.find_element(By.ID, "parent-root")
shadow_root = driver.execute_script("return arguments[0].shadowRoot", parent_root)
sign_in_button = shadow_root.find_element(By.CSS_SELECTOR, "a[href*='/engage/account/login']")
sign_in_button.click()

# === Step 3: Automatic Login (Duo MFA still require interaction) ===
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

# === Step 4: Navigate to Specific Bill ===
driver.get(BILL_URL)

budget_tab = WebDriverWait(driver, 20).until(
    EC.element_to_be_clickable((By.XPATH, "//a[contains(@analytics-event, 'Tab Budget')]"))
)
budget_tab.click()
time.sleep(5)

# === Step 5: Iterate over budget sections and items ===
for section_name, items in sections:
    try:
        print(f"\nProcessing section: {section_name}")

        # Wait for section link to exist and be clickable
        section_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((
                By.XPATH,
                f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]"
            ))
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", section_link)
        time.sleep(1)  # give UI time to settle

        for idx, item in items.iterrows():
            print(f"  Processing item: {item['Item Name']}")

            # Locate Add Item button inside the section
            add_item_button = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    f"//h4[@class='groupTitle bdg-margin-vert']/a[contains(text(), '{section_name}')]/../../..//a[contains(@class,'add')]"
                ))
            )
            driver.execute_script("arguments[0].scrollIntoView(true);", add_item_button)
            time.sleep(0.5)  # let scroll finish
            driver.execute_script("arguments[0].click();", add_item_button)
            print("    Clicked 'Add Line Item' button")

            # Wait for Name field (ensures modal has loaded)
            name_field = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.ID, "Name"))
            )
            name_field.clear()
            name_field.send_keys(str(item["Item Name"]))

            driver.find_element(By.ID, "Description").send_keys(str(item["Description"]))

            # Quantity field
            quantity_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "Quantity"))
            )
            quantity_field.clear()
            quantity = int(item["Quantity"]) if not pd.isna(item["Quantity"]) else 0
            quantity_field.send_keys(str(quantity))

            # Price field
            price_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "Price"))
            )
            price_field.clear()
            price_field.send_keys(str(item["Cost"]))

            print("    Filled in item fields")

            # Upload file from downloads using item name
            filename = f"{item['Item Name']}.png"
            local_path = os.path.join(DOWNLOAD_DIR, filename)
            if not os.path.exists(local_path):
                print(f"    WARNING: File not found: {local_path}")
            else:
                file_input = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.ID, "fileUploadInput"))
                )
                driver.execute_script("arguments[0].style.display='block';", file_input)
                file_input.send_keys(os.path.abspath(local_path))
                print(f"    Uploaded file: {filename}")

            # Click Save
            success = click_save_button(driver)
            if not success:
                print(f"ERROR clicking Save for item '{item['Item Name']}'")

        print(f"Finished section: {section_name}")

    except Exception as e:
        print(f"ERROR in section '{section_name}': {e}")

print("All budget sections processed.")
