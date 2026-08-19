import re
import time
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ENGAGE_BILL_BASE_URL = (
    "https://gatech.campuslabs.com/engage/actionCenter/organization/MRG/"
    "budgeting/requests#/edit/{bill_no}"
)


def build_bill_url(bill_no: str) -> str:
    bill_no = str(bill_no or "").strip()
    if not bill_no:
        raise ValueError("bill_no is required")
    return ENGAGE_BILL_BASE_URL.format(bill_no=bill_no)


def _normalize_text(value) -> str:
    if value is None:
        return ""
    value = str(value)
    value = value.replace("&nbsp;", " ")
    value = re.sub(r"<.*?>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


def find_line_number_in_bill_html(html: str, item_name: str) -> Optional[int]:
    """Return the 1-based line number for an item name on an Engage bill page."""
    if not html or not item_name:
        return None

    matches = re.findall(
        r"<a[^>]*ng-click=['\"]editLineItem\(lineItem\)['\"][^>]*>(.*?)</a>",
        html,
        flags=re.I | re.S,
    )
    if not matches:
        return None

    normalized_target = _normalize_text(item_name)
    
    # Pass 1: Exact match
    for idx, match in enumerate(matches, start=1):
        text = _normalize_text(match)
        if text == normalized_target:
            return idx

    # Pass 2: Clean alphanumeric match
    target_clean = re.sub(r"[^a-z0-9]", "", normalized_target)
    for idx, match in enumerate(matches, start=1):
        text_clean = re.sub(r"[^a-z0-9]", "", _normalize_text(match))
        if target_clean and text_clean == target_clean:
            return idx

    # Pass 3: Token / Substring with closest length
    best_idx = None
    best_len_diff = float("inf")
    for idx, match in enumerate(matches, start=1):
        text = _normalize_text(match)
        if not text:
            continue
        if normalized_target in text or text in normalized_target:
            len_diff = abs(len(text) - len(normalized_target))
            if len_diff < best_len_diff:
                best_len_diff = len_diff
                best_idx = idx

    return best_idx


def find_best_item_match(target_name: str, candidate_dict: dict[str, dict]) -> Optional[dict]:
    """
    Match target item name against scraped Engage line item dictionary.
    Prioritizes:
    1. Exact normalized match (e.g. 'antenna' == 'antenna', 'toggle switch' == 'toggle switch')
    2. Exact alphanumeric normalized match (ignoring punctuation/extra whitespace)
    3. Longest common token set match (preferring closest string length)
    4. Substring containment with closest length penalty (never match a short token to a composite name if exact exists)
    """
    if not target_name or not candidate_dict:
        return None

    target_norm = _normalize_text(target_name)
    target_clean = re.sub(r"[^a-z0-9]", "", target_norm)

    # Pass 1: Exact string match
    if target_norm in candidate_dict:
        return candidate_dict[target_norm]

    # Pass 2: Clean alphanumeric match
    for key, info in candidate_dict.items():
        key_clean = re.sub(r"[^a-z0-9]", "", key)
        if target_clean and key_clean and target_clean == key_clean:
            return info

    # Pass 3: Whole word / token matching
    target_tokens = set(target_norm.split())
    best_candidate = None
    best_score = 0.0
    best_len_diff = float("inf")

    for key, info in candidate_dict.items():
        key_tokens = set(key.split())
        if target_tokens and (target_tokens == key_tokens or target_tokens.issubset(key_tokens) or key_tokens.issubset(target_tokens)):
            len_diff = abs(len(key) - len(target_norm))
            intersection = len(target_tokens & key_tokens)
            union = len(target_tokens | key_tokens)
            score = intersection / union if union else 0
            if score > best_score or (score == best_score and len_diff < best_len_diff):
                best_score = score
                best_len_diff = len_diff
                best_candidate = info

    if best_candidate and best_score >= 0.5:
        return best_candidate

    # Pass 4: Substring containment with length penalty
    for key, info in candidate_dict.items():
        if target_norm in key or key in target_norm:
            len_diff = abs(len(key) - len(target_norm))
            if len_diff < best_len_diff:
                best_len_diff = len_diff
                best_candidate = info

    return best_candidate


def lookup_bill_item_line_numbers(driver, bill_no: str, item_names: list[str]) -> dict[str, int]:
    """Visit the Engage bill page, find the actual line numbers, and return a name->line map."""
    data = lookup_bill_item_locations(driver, bill_no, item_names)
    return {name: info["line_number"] for name, info in data.items() if isinstance(info, dict) and "line_number" in info}


def lookup_bill_item_locations(driver, bill_no: str, item_names: list[str]) -> dict[str, dict]:
    """Visit the Engage bill page and return item -> {section, line_number}.

    Reverse-engineered from automation.py DOM navigation and extraction logic.
    """
    if not bill_no or not item_names:
        return {}

    bill_url = build_bill_url(bill_no)
    print(f"\n  🔍 Resolving live section and line numbers from Engage for Bill #{bill_no}...")
    print(f"     🌐 Navigating to {bill_url}")
    driver.get(bill_url)

    # 1) Click the "Tab Budget" tab exactly as in automation.py (line 485-489)
    try:
        budget_tab = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@analytics-event, 'Tab Budget')]"))
        )
        budget_tab.click()
        print("     👆 Clicked 'Tab Budget' tab")
        time.sleep(5)
    except Exception as e:
        print(f"     ℹ️ Budget tab click notice: {e}")
        time.sleep(3)

    by_name = {}
    section_count = 0

    # 2) Extract sections and line items using section containers (from automation.py line 542-546 & 260-266)
    try:
        section_anchors = driver.find_elements(
            By.XPATH, "//h4[contains(@class, 'groupTitle')]/a | //h4[contains(@class, 'groupTitle')]"
        )
        seen_secs = set()
        unique_anchors = []
        for sa in section_anchors:
            txt = sa.text.strip()
            if txt and txt not in seen_secs:
                seen_secs.add(txt)
                unique_anchors.append(sa)

        section_count = len(unique_anchors)
        overall_line_counter = 1

        for anchor in unique_anchors:
            sec_name = anchor.text.strip()
            try:
                # Traverse up 3 parent levels to section container as in automation.py
                container = anchor.find_element(By.XPATH, "./../../..")

                sec_items = []

                # Strategy A: Find element nodes inside container (links, rows, list items)
                line_item_elements = container.find_elements(
                    By.XPATH,
                    ".//a[contains(@ng-click, 'lineItem') or contains(@ng-click, 'LineItem')] | "
                    ".//a[contains(@class, 'line') or contains(@class, 'item')] | "
                    ".//tr[contains(@class, 'ng-scope') or contains(@ng-repeat, 'line')] | "
                    ".//li[contains(@ng-repeat, 'line')] | "
                    ".//div[contains(@class, 'line-item') or contains(@class, 'budget-item')] | "
                    ".//a | .//td[1]"
                )

                for li in line_item_elements:
                    txt = li.text.strip()
                    norm = _normalize_text(txt)
                    if norm and norm != _normalize_text(sec_name) and len(norm) >= 3:
                        if not any(skip in norm for skip in ["add line item", "delete section", "section total", "edit section"]):
                            if norm not in [item[1] for item in sec_items]:
                                sec_items.append((txt, norm))

                # Strategy B: Fallback to parsing container text lines if DOM node lookup returned nothing
                if not sec_items:
                    raw_text = container.text or ""
                    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
                    for ln in lines:
                        norm = _normalize_text(ln)
                        if norm and norm != _normalize_text(sec_name) and len(norm) >= 3:
                            if not any(skip in norm for skip in ["add line item", "delete section", "section total", "edit section"]):
                                if not re.match(r'^\$?\d+[\d.,]*$', norm):
                                    if norm not in [item[1] for item in sec_items]:
                                        sec_items.append((ln, norm))

                for sec_line_idx, (orig_txt, norm_txt) in enumerate(sec_items, start=1):
                    if norm_txt not in by_name:
                        by_name[norm_txt] = {
                            "section": sec_name,
                            "line_number": overall_line_counter,
                            "section_line_number": sec_line_idx,
                        }
                        overall_line_counter += 1
            except Exception:
                pass
    except Exception:
        pass

    # 3) Fallback if section container traversal didn't find items: find line items globally
    if not by_name:
        try:
            line_items = driver.find_elements(
                By.XPATH, "//a[@ng-click='editLineItem(lineItem)']"
            )
            for idx, li in enumerate(line_items, start=1):
                li_text = li.text.strip()
                norm_text = _normalize_text(li_text)
                if norm_text:
                    by_name[norm_text] = {
                        "section": "Unknown Section",
                        "line_number": idx,
                        "section_line_number": idx,
                    }
        except Exception:
            pass

    print(f"     ✅ Found {len(by_name)} total line items across {section_count} section(s) on Engage.")

    # 4) Match target item names against extracted Engage line items using multi-tiered matcher
    result = {}
    for item_name in item_names:
        if not item_name:
            continue
        match_info = find_best_item_match(item_name, by_name)
        if match_info:
            result[item_name] = match_info

    print(f"     🎯 Matched {len(result)} of {len(item_names)} requested item(s) to live Engage locations.")
    return result
