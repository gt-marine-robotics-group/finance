import os
import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

# === CONFIG ===
CSV_PATH = "./Fall25_Bills_Budget.csv"        # input CSV
OUTPUT_CSV = "./Fall25_Bills_Budget_Updated.csv"
SAVE_FOLDER = "./screenshots"
DELAY = 3                                     # seconds to wait after page load

# === PROMPT USER ===
bill_title = input("Enter Bill Title: ").strip()

# === PREPARE DIRECTORIES ===
if os.path.exists(SAVE_FOLDER):
    for f in os.listdir(SAVE_FOLDER):
        fp = os.path.join(SAVE_FOLDER, f)
        if os.path.isfile(fp):
            os.remove(fp)
else:
    os.makedirs(SAVE_FOLDER)

# === LOAD CSV ===
df = pd.read_csv(CSV_PATH, encoding="utf-8", on_bad_lines="skip")
df.fillna("", inplace=True)
df.columns = df.columns.str.strip()

# Ensure required columns exist
required_cols = {"Item Name", "Link", "Cost", "Bill Title"}
missing = required_cols - set(df.columns)
if missing:
    raise ValueError(f"Missing columns in CSV: {missing}")

# Filter for chosen bill
mask = df["Bill Title"].astype(str).str.strip().str.lower() == bill_title.lower()
df_filtered = df[mask].copy()

if df_filtered.empty:
    print(f"⚠️ No entries found for Bill '{bill_title}' — exiting.")
    exit(0)

# === Price extraction ===
def parse_price(s: str):
    """Return float for first valid price string (e.g. '129.99', '129,99 USD', '8.99')"""
    if not isinstance(s, str) or not s.strip():
        return None

    s = s.replace("\xa0", " ").strip()

    # Match numbers with optional decimals
    match = re.search(r'(\d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{1,2})?|\d+[.,]\d{1,2})', s)
    if not match:
        return None

    num_str = match.group(1)

    # Normalize European decimal
    if "," in num_str and "." not in num_str:
        num_str = num_str.replace(",", ".")
    else:
        num_str = re.sub(r"[,\s]", "", num_str)  # remove thousand separators

    try:
        return float(num_str)
    except ValueError:
        return None

# === SETUP SELENIUM ===
chrome_options = Options()
chrome_options.add_argument("--headless=new")
chrome_options.add_argument("--window-size=1920,1080")

service = Service()  # assumes chromedriver is in PATH
driver = webdriver.Chrome(service=service, options=chrome_options)

# === SCRAPE LOOP ===
for idx, row in df_filtered.iterrows():
    item_name = str(row.get("Item Name", "")).strip()
    url = str(row.get("Link", "")).strip()

    if not item_name or not isinstance(url, str) or url.lower() == "nan" or url == "":
        print(f"⚠️ Skipping empty or invalid row (item='{item_name}')")
        continue

    print(f"\nOpening {item_name} → {url}")
    scraped_text = ""
    found = False

    try:
        driver.get(url)
        time.sleep(DELAY)

        # === AMAZON-PRIORITY SELECTORS ===
        amazon_price_selectors = [
            # Modern Amazon price widget
            "#corePriceDisplay_desktop_feature_div .a-offscreen",
            "#apex_desktop .a-offscreen",

            # Standard price blocks
            "#priceblock_ourprice",
            "#priceblock_dealprice",
            "#sns-base-price",
            "#newBuyBoxPrice",

            # Generic Amazon price classes
            ".a-price .a-offscreen",
            ".a-price-whole",
            ".a-price-fraction",
        ]

        def first_nonempty_text(element):
            txt = (element.text or "").strip()
            if not txt:
                txt = (element.get_attribute("innerText") or "").strip()
            if not txt:
                txt = (element.get_attribute("content") or "").strip()
            return txt

        # ---------- TRY AMAZON SELECTORS FIRST ----------
        for sel in amazon_price_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
            except Exception:
                elems = []

            for el in elems:
                text = first_nonempty_text(el)
                if not text:
                    continue
                if re.search(r"\d", text):
                    scraped_text = text
                    found = True
                    break
            if found:
                break

        # ---------- SPECIAL CASE: AMAZON WHOLE + FRACTION ----------
        if not found:
            try:
                whole = driver.find_elements(By.CSS_SELECTOR, ".a-price-whole")
                frac = driver.find_elements(By.CSS_SELECTOR, ".a-price-fraction")
                if whole and frac:
                    w = whole[0].text.replace(",", "").strip()
                    f = frac[0].text.strip()
                    if w.isdigit() and f.isdigit():
                        scraped_text = f"{w}.{f}"
                        found = True
            except Exception:
                pass

        # ---------- GENERIC FALLBACK SELECTORS ----------
        if not found:
            generic_selectors = [
                '[class*="price"]',
                '[id*="price"]',
                '[class*="cost"]',
                '[id*="cost"]',
                '[class*="amount"]',
                '[data-price]',
                '[itemprop*="price"]',
                '[data-testid*="price"]',
            ]

            for sel in generic_selectors:
                try:
                    elems = driver.find_elements(By.CSS_SELECTOR, sel)
                except Exception:
                    elems = []

                for el in elems:
                    text = first_nonempty_text(el)
                    if not text:
                        continue
                    if re.search(r"\d", text):
                        scraped_text = text
                        found = True
                        break
                if found:
                    break

        # ---------- RAW HTML REGEX LAST RESORT ----------
        if not scraped_text:
            html = driver.page_source
            m = re.search(r'[\$€£]?\s*\d[\d,]*\.?\d{0,2}', html)
            if m:
                scraped_text = m.group(0)

        # --- Save screenshot ---
        safe_filename = f"{item_name}.png"
        driver.save_screenshot(os.path.join(SAVE_FOLDER, safe_filename))
        print(f"✅ Saved screenshot: {safe_filename}")

        # --- Parse & Update Cost ---
        parsed = parse_price(scraped_text)
        if parsed is not None and parsed > 0.0:
            df.at[idx, "Cost"] = f"${parsed:.2f}"
            print(f"💲 Found cost: {scraped_text} → ${parsed:.2f}")
        else:
            print(f"⚠️ Could not parse price from: '{scraped_text}'")

    except Exception as e:
        print(f"⚠️ Error loading {url}: {e}")

driver.quit()

# === SAVE UPDATED CSV ===
df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
print(f"\n🎉 Done. Updated CSV saved as: {OUTPUT_CSV}")
print(f"Screenshots saved in: {os.path.abspath(SAVE_FOLDER)}")
