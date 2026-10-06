import re
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.common.exceptions import (
    ElementClickInterceptedException, ElementNotInteractableException,
    StaleElementReferenceException, TimeoutException,
)
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


def funding_kind_from_title(title):
    return "budget" if re.search(r"\bbudget\b", str(title), re.I) else "bill"


def _normalize_text(value) -> str:
    if value is None:
        return ""
    value = str(value)
    value = value.replace("&nbsp;", " ")
    value = re.sub(r"<.*?>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


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


def parse_budget_text(text: str) -> dict[str, dict]:
    """Read explicit section-relative numbers from Engage's visible Budget view.

    The section summary also contains numbers, so require numbered item rows
    and a section heading/row label. Never substitute Excel IDs or guessed indexes.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    section = None
    by_name = {}
    duplicates = set()
    section_pattern = r"[A-Z]\d{2}(?:\s*-\s*.+)?"
    for index, line in enumerate(lines):
        heading = re.fullmatch(r"Budget Section:\s*(.*)", line, re.I)
        if heading:
            title = heading[1] or (lines[index + 1] if index + 1 < len(lines) else "")
            if re.fullmatch(section_pattern, title):
                section = title
            else:
                section = None
        match = re.fullmatch(r"(\d+)\.\s*(.*)", line)
        if not match or int(match[1]) <= 0:
            continue
        name = match[2].strip()
        name_index = index
        if not name and index + 1 < len(lines):
            name_index += 1
            name = lines[name_index]
        row_section = None
        inline = re.search(r"\s+([A-Z]\d{2}\s*-\s*.*)$", name)
        if inline:
            row_section = re.split(r"\s+\d+\s*[x×]\s*\$|\s+\$", inline[1])[0].strip()
            if section and row_section[:3] == section[:3]:
                row_section = section
            name = name[:inline.start()].strip()
        elif name_index + 1 < len(lines) and re.fullmatch(section_pattern, lines[name_index + 1]):
            row_section = lines[name_index + 1]
        actual_section = row_section or section
        name = name.split("\t")[0].strip()
        if not name or not actual_section or re.fullmatch(section_pattern, name):
            continue
        norm = _normalize_text(name)
        info = {"section": actual_section, "line_number": int(match[1]),
                "section_line_number": int(match[1])}
        if norm in by_name and by_name[norm] != info:
            duplicates.add(norm)
        else:
            by_name[norm] = info
    # An identically named item in two sections needs human disambiguation.
    return {name: info for name, info in by_name.items() if name not in duplicates}


def open_budget_view(driver):
    """Expand the request Menu before selecting Budget, then wait for its data."""
    menu_clicked = False
    budget_clicked = False
    upper, lower = "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"
    label = f"translate(normalize-space(.), '{upper}', '{lower}')"

    def ready(d):
        nonlocal menu_clicked, budget_clicked
        body = d.find_element(By.TAG_NAME, "body").text or ""
        if parse_budget_text(body):
            return body
        if not budget_clicked:
            for tab in d.find_elements(By.XPATH,
                    f"//a[{label}='budget' or contains(@analytics-event, 'Tab Budget')] | "
                    f"//button[{label}='budget'] | //*[@role='tab' and {label}='budget']"):
                if tab.is_displayed() and tab.is_enabled():
                    tab.click()
                    budget_clicked = True
                    return False
        if not menu_clicked:
            for menu in d.find_elements(By.XPATH,
                    f"//a[contains({label}, 'menu') and not(contains({label}, 'close'))] | "
                    f"//button[contains({label}, 'menu') and not(contains({label}, 'close'))]"):
                if menu.is_displayed() and menu.is_enabled():
                    menu.click()
                    menu_clicked = True
                    return False
        return False

    return WebDriverWait(driver, 25, ignored_exceptions=(
        StaleElementReferenceException, ElementClickInterceptedException,
        ElementNotInteractableException,
    )).until(ready)


def prompt_verified_location():
    """Accept 'B03 Line 1' or ask for section after a bare line number."""
    while True:
        answer = input("  Enter verified section and line (e.g. B03 Line 1), or a line number, or 'cancel': ").strip()
        if answer.lower() in ("cancel", "quit", "q"):
            raise SystemExit("Engage reference entry cancelled; comparison workbook is saved.")
        combined = re.fullmatch(r"([A-Z]\d{2})\s*[,/-]?\s*(?:line\s*)?(\d+)", answer, re.I)
        bare = re.fullmatch(r"(?:line\s*)?(\d+)", answer, re.I)
        if combined and int(combined[2]) > 0:
            return int(combined[2]), combined[1].upper()
        if bare and int(bare[1]) > 0:
            while True:
                section = input("  Enter verified budget section (e.g. B03), or 'cancel': ").strip()
                if section.lower() in ("cancel", "quit", "q"):
                    raise SystemExit("Engage reference entry cancelled; comparison workbook is saved.")
                if re.fullmatch(r"[A-Z]\d{2}(?:\s*-\s*.+)?", section, re.I):
                    return int(bare[1]), section[:3].upper() + section[3:]
                print("  Use the section shown in Engage, for example B03. Chrome is still open.")
        else:
            print("  Use B03 Line 1 or a positive line number. Chrome is still open.")


def confirm_continue_to_engage():
    while True:
        answer = input("\nContinue to Engage with this verified amount? [Y/n]: ").strip().lower()
        if answer in ("", "y", "yes"):
            return True
        if answer in ("n", "no", "cancel", "q", "quit"):
            return False
        print("Press Enter to continue, or type 'n' to stop with the comparison workbook saved.")


def prompt_fee_reference(fee, amount):
    while True:
        ref = input(f"Verified bill/line/section funding {fee.lower()} (${amount}), or 'cancel': ").strip()
        if ref.lower() in ("cancel", "quit", "q"):
            raise SystemExit("Fee funding entry cancelled; comparison workbook is saved.")
        if ref:
            return ref
        print(f"{fee} is included in the requested amount and needs a funding reference. "
              "Check its bill/section/line in Engage and retry. Both Chrome windows remain open.")


def lookup_bill_item_locations(driver, bill_no: str, item_names: list[str], *, navigate=True) -> dict[str, dict]:
    """Open Menu -> Budget and match visible, explicit section/line references."""
    if not bill_no or not item_names:
        return {}
    print(f"\n  Resolving Engage funding locations for request #{bill_no}...")
    if navigate:
        driver.get(build_bill_url(bill_no))
    elif not re.search(rf"#/edit/{re.escape(str(bill_no))}(?:[?&]|$)", driver.current_url or ""):
        print("  Open this bill's Budget view before retrying; the current page is a different request.")
        return {}
    try:
        body = open_budget_view(driver)
        by_name = parse_budget_text(body)
    except TimeoutException:
        print("  Could not open/read Menu → Budget. Chrome remains open for recovery.")
        return {}
    if not by_name:
        print("  Budget view loaded, but no verified numbered items could be read.")
        return {}
    sections = {info["section"] for info in by_name.values()}
    print(f"  Read {len(by_name)} numbered items in {len(sections)} nonempty section(s).")
    result = {}
    title = re.search(r"(?im)^Request:\s*(.+)$", body)
    kind = funding_kind_from_title(title[1]) if title else None
    for name in item_names:
        info = find_best_item_match(name, by_name)
        if info:
            result[name] = {**info, **({"funding_kind": kind} if kind else {})}
    print(f"  Matched {len(result)} of {len(item_names)} requested items.")
    return result
