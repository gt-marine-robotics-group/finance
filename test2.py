import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException, StaleElementReferenceException
import time

def click_save_button(driver, retries=5, wait_between=1.0):
    xpath = "//a[contains(@class,'button-success') and contains(text(),'Save')]"
    
    for attempt in range(retries):
        try:
            save_button = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )

            # Check if button is disabled
            is_disabled = save_button.get_attribute("ng-disabled")
            if is_disabled and ("true" in is_disabled or "1" in is_disabled):
                print(f"    Save button disabled, waiting...")
                time.sleep(wait_between)
                continue

            # Scroll into view + JS click
            driver.execute_script("arguments[0].scrollIntoView(true);", save_button)
            driver.execute_script("arguments[0].click();", save_button)
            print("    Clicked Save button")
            
            # Wait for modal or form to disappear (adjust selector if needed)
            WebDriverWait(driver, 10).until_not(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            return True
        except (ElementClickInterceptedException, StaleElementReferenceException) as e:
            print(f"    Attempt {attempt+1}: Save button click failed, retrying...")
            time.sleep(wait_between)
    print("    ERROR: Could not click Save button after retries")
    return False

# === CONFIG ===
EXCEL_FILE = "Fall25_Bills_Budget.xlsx"
DOWNLOAD_DIR = "downloads"
USERNAME = "awu335"
PASSWORD = "Georgia_palace5"  # store securely in practice


# === Step 1: Read Excel ===
df = pd.read_excel(EXCEL_FILE)
sections = df.groupby("Budget Section")

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# === Step 2: Start Selenium Browser ===
options = webdriver.ChromeOptions()
options.add_argument("--incognito")
options.add_experimental_option("detach", True)  # <-- keeps Chrome open

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

# === Step 3: Automatic Login (Duo MFA may still require interaction) ===
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
driver.get("https://gatech.campuslabs.com/engage/actionCenter/organization/mrg/budgeting/requests#/edit/326798")

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
