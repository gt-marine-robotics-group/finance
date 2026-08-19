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


def _normalize_stem(word: str) -> str:
    """Normalize plural endings and common suffixes for robust token comparison."""
    w = word.lower().strip()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 3 and not w.endswith("ses"):
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 2:
        return w[:-1]
    return w


def find_best_item_match(target_name: str, candidate_dict: dict[str, dict]) -> Optional[dict]:
    """
    Match target item name against scraped Engage line item dictionary.
    Prioritizes:
    1. Exact normalized match (e.g. 'antenna' == 'antenna')
    2. Exact alphanumeric normalized match (ignoring punctuation/extra whitespace)
    3. Stemmed token set match (handles plurals: 'toggle switch' == 'toggle switches')
    4. Fuzzy SequenceMatcher ratio >= 0.65 (handles typos: 'rapsberry pi 4' == 'raspberry pi 4')
    5. Substring containment with closest length penalty
    """
    if not target_name or not candidate_dict:
        return None

    import difflib

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

    # Pass 3: Stemmed whole word / token matching
    target_stems = set(_normalize_stem(w) for w in target_norm.split() if len(w) > 1)
    best_candidate = None
    best_score = 0.0
    best_len_diff = float("inf")

    for key, info in candidate_dict.items():
        key_stems = set(_normalize_stem(w) for w in key.split() if len(w) > 1)
        if target_stems and (target_stems == key_stems or target_stems.issubset(key_stems) or key_stems.issubset(target_stems)):
            len_diff = abs(len(key) - len(target_norm))
            intersection = len(target_stems & key_stems)
            union = len(target_stems | key_stems)
            score = intersection / union if union else 0
            if score > best_score or (score == best_score and len_diff < best_len_diff):
                best_score = score
                best_len_diff = len_diff
                best_candidate = info

    if best_candidate and best_score >= 0.4:
        return best_candidate

    # Pass 4: Fuzzy sequence matching (handles typos, character swaps, word reorderings)
    best_ratio = 0.0
    for key, info in candidate_dict.items():
        ratio = difflib.SequenceMatcher(None, target_norm, key).ratio()
        stem_target = " ".join(sorted(target_stems))
        stem_key = " ".join(sorted(_normalize_stem(w) for w in key.split() if len(w) > 1))
        stem_ratio = difflib.SequenceMatcher(None, stem_target, stem_key).ratio() if stem_target and stem_key else 0.0
        max_r = max(ratio, stem_ratio)
        if max_r > best_ratio:
            best_ratio = max_r
            best_candidate = info

    if best_candidate and best_ratio >= 0.65:
        return best_candidate

    # Pass 5: Substring containment with length penalty
    best_len_diff = float("inf")
    best_candidate = None
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

                # Strategy 1: Parse container text lines with explicit line numbers
                raw_text = container.text or ""
                lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

                def _clean_item_name(raw_val: str) -> str:
                    c = raw_val.split("\t")[0].strip()
                    c = re.sub(r"\s+B\d{2}\s*-.*$", "", c, flags=re.I)
                    c = re.sub(r"\s+\d+\s*x\s*\$?\d+.*$", "", c, flags=re.I)
                    c = re.sub(r"\s+\$?\d+[\d.,]*$", "", c)
                    return c.strip()

                # Single-line format (tab or space separated)
                for ln in lines:
                    m = re.match(r"^\s*(\d+)\.\s*([^\n\r]+)", ln)
                    if m:
                        explicit_num = int(m.group(1))
                        cleaned_name = _clean_item_name(m.group(2))
                        norm = _normalize_text(cleaned_name)
                        if norm and norm != _normalize_text(sec_name) and len(norm) >= 2:
                            if not any(skip in norm for skip in ["add line item", "delete section", "section total", "edit section"]):
                                sec_items.append((cleaned_name, norm, explicit_num))

                # Multiline format (line number on line i, item name on line i+1)
                if not sec_items:
                    i = 0
                    while i < len(lines):
                        ln = lines[i]
                        m_single = re.match(r"^(\d+)\.?$", ln)
                        if m_single and i + 1 < len(lines):
                            explicit_num = int(m_single.group(1))
                            name_candidate = _clean_item_name(lines[i + 1])
                            norm = _normalize_text(name_candidate)
                            if norm and len(norm) >= 2 and norm != _normalize_text(sec_name):
                                if not any(skip in norm for skip in ["add line item", "delete section", "section total", "edit section"]):
                                    if not re.match(r"^\d+\.?$", name_candidate) and not re.match(r"^B\d{2}\s*-", name_candidate):
                                        sec_items.append((name_candidate, norm, explicit_num))
                                        i += 1
                        i += 1

                # Strategy 2: Check table rows (tr) inside container
                if not sec_items:
                    rows = container.find_elements(By.TAG_NAME, "tr")
                    for r in rows:
                        cells = r.find_elements(By.TAG_NAME, "td")
                        if len(cells) >= 2:
                            c0_text = cells[0].text.strip()
                            c1_text = _clean_item_name(cells[1].text.strip())
                            m = re.match(r"^(\d+)\.?", c0_text)
                            if m and c1_text:
                                explicit_num = int(m.group(1))
                                norm = _normalize_text(c1_text)
                                if norm and len(norm) >= 2 and norm != _normalize_text(sec_name):
                                    sec_items.append((c1_text, norm, explicit_num))

                # Strategy 3: Find element nodes inside container
                if not sec_items:
                    line_item_elements = container.find_elements(
                        By.XPATH,
                        ".//a[contains(@ng-click, 'lineItem') or contains(@ng-click, 'LineItem')] | "
                        ".//tr[contains(@class, 'ng-scope') or contains(@ng-repeat, 'line')] | "
                        ".//div[contains(@class, 'line-item') or contains(@class, 'budget-item')]"
                    )
                    for li in line_item_elements:
                        txt = li.text.strip()
                        m = re.match(r"^(\d+)\.\s*(.*)", txt)
                        explicit_num = int(m.group(1)) if m else None
                        raw_txt = m.group(2).strip() if m else txt
                        cleaned_txt = _clean_item_name(raw_txt)
                        norm = _normalize_text(cleaned_txt)
                        if norm and norm != _normalize_text(sec_name) and len(norm) >= 2:
                            if not any(skip in norm for skip in ["add line item", "delete section", "section total", "edit section"]):
                                sec_items.append((cleaned_txt, norm, explicit_num))

                for sec_line_idx, item_tuple in enumerate(sec_items, start=1):
                    orig_txt = item_tuple[0]
                    norm_txt = item_tuple[1]
                    explicit_num = item_tuple[2] if len(item_tuple) > 2 and item_tuple[2] is not None else sec_line_idx

                    if norm_txt not in by_name:
                        by_name[norm_txt] = {
                            "section": sec_name,
                            "line_number": explicit_num,
                            "section_line_number": explicit_num,
                        }
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
