import pandas as pd
import os
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import math

# === Configuration ===
CSV_PATH = "./Fall25_Bills_Budget.csv"            # path to your saved CSV
SAVE_FOLDER = "./screenshots"        # folder to save screenshots
DELAY = 3                            # seconds to wait after page load

# === Set up Selenium ===
chrome_options = Options()
chrome_options.add_argument("--headless=new")  # run headless
chrome_options.add_argument("--window-size=1920,1080")

service = Service()  # assumes chromedriver is in PATH
driver = webdriver.Chrome(service=service, options=chrome_options)

# === Prepare save directory ===
os.makedirs(SAVE_FOLDER, exist_ok=True)

# === Load CSV ===
df = pd.read_csv(CSV_PATH)

# === Visit each valid URL ===
for _, row in df.iterrows():
    item = str(row.get("Item Name", "")).strip()
    url = row.get("Link", "")

    # Skip if url is empty or NaN
    if not isinstance(url, str) or url.strip() == "" or str(url).lower() == "nan":
        print(f"Skipping empty URL for item: {item}")
        continue

    print(f"Opening {item} → {url}")

    try:
        driver.get(url)
        time.sleep(DELAY)

        # Save using exact Item name (spaces preserved)
        filename = os.path.join(SAVE_FOLDER, f"{item}.png")
        driver.save_screenshot(filename)
        print(f"✅ Saved screenshot: {filename}")
    except Exception as e:
        print(f"⚠️ Error loading {url} for {item}: {e}")

driver.quit()
print("🎉 All valid screenshots saved.")
