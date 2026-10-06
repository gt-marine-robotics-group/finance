import os
from unittest.mock import MagicMock

import pytest
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

from mrg_finance import engage_bill_lookup as lookup


# Visible row structure checked in Chrome on Bill 344042, Menu -> Budget.
BUDGET = """Sections (27)
# of Line Items (50)
B03 - General Inventoried Goods
5
$1,950.70
Budget Section:
B03 - General Inventoried Goods
Inventoried Items are durable goods.
1.
Rapsberry Pi 4
B03 - General Inventoried Goods
10 x $63.35
$633.50
2.
Voltage Regulator
B03 - General Inventoried Goods
10 x $17.95
$179.50
Budget Section:
B06 - Non-Inventoried Items
Non-Inventoried Items are not required to be tracked.
1.
Foam sheets
B06 - Non-Inventoried Items
5 x $57.66
$288.30
"""


def test_visible_budget_preserves_product_number_and_section_relative_line():
    rows = lookup.parse_budget_text(BUDGET)
    assert len(rows) == 3
    assert rows["rapsberry pi 4"] == {
        "section": "B03 - General Inventoried Goods", "line_number": 1, "section_line_number": 1}
    assert rows["foam sheets"]["section_line_number"] == 1
    assert lookup.find_best_item_match("Raspberry Pi 4", rows) == rows["rapsberry pi 4"]


def test_parser_does_not_invent_section_or_global_line_number():
    assert lookup.parse_budget_text("Request History\n1. Raspberry Pi 4") == {}
    assert lookup.parse_budget_text("Budget Section:\nB03\n5. Raspberry Pi 4")["raspberry pi 4"]["section_line_number"] == 5
    ambiguous = BUDGET.replace("Foam sheets", "Rapsberry Pi 4")
    assert "rapsberry pi 4" not in lookup.parse_budget_text(ambiguous)


def test_single_line_rows_exclude_vendor_amounts_from_section():
    rows = lookup.parse_budget_text("Budget Section: B03 - General Inventoried Goods\n"
                                    "1. Rapsberry Pi 4 B03 - General Inventoried Goods 10 x $63.35 $633.50")
    assert rows["rapsberry pi 4"]["section"] == "B03 - General Inventoried Goods"


def test_open_budget_expands_menu_and_waits_until_rows_loaded(monkeypatch):
    from selenium.webdriver.support.ui import WebDriverWait
    driver = MagicMock()
    state = {"menu": False, "budget": False, "reads": 0}
    menu, tab = MagicMock(), MagicMock()
    menu.is_displayed.return_value = True
    tab.is_displayed.side_effect = lambda: state["menu"]
    menu.click.side_effect = lambda: state.update(menu=True)
    tab.click.side_effect = lambda: state.update(budget=True)

    def body(*a):
        state["reads"] += 1
        # Budget headings render before Angular populates line rows.
        text = BUDGET if state["budget"] and state["reads"] > 3 else "Budget Section:\nB03" if state["budget"] else "Request Id\n344042"
        return MagicMock(text=text)

    driver.find_element.side_effect = body
    driver.find_elements.side_effect = lambda by, selector: [menu] if "not(contains" in selector else [tab]
    monkeypatch.setattr(lookup, "WebDriverWait", lambda d, *a, **kw: WebDriverWait(d, 1, poll_frequency=.01, **kw))
    assert lookup.open_budget_view(driver) == BUDGET
    menu.click.assert_called_once()
    tab.click.assert_called_once()


def test_already_loaded_budget_does_not_toggle_menu_or_tab():
    driver = MagicMock()
    driver.find_element.return_value.text = BUDGET
    assert lookup.open_budget_view(driver) == BUDGET
    driver.find_elements.assert_not_called()


def test_failed_lookup_reports_unread_page_instead_of_zero_success(monkeypatch, capsys):
    driver = MagicMock()
    monkeypatch.setattr(lookup, "open_budget_view", MagicMock(side_effect=TimeoutException()))
    assert lookup.lookup_bill_item_locations(driver, "344042", ["Rapsberry Pi 4"]) == {}
    assert "Could not open/read" in capsys.readouterr().out


def test_lookup_retry_reads_current_bill_without_renavigation(monkeypatch):
    driver = MagicMock(current_url=lookup.build_bill_url("344042") + "?selectedTab=budget")
    monkeypatch.setattr(lookup, "open_budget_view", lambda d: BUDGET)
    result = lookup.lookup_bill_item_locations(driver, "344042", ["Rapsberry Pi 4"], navigate=False)
    assert result["Rapsberry Pi 4"]["section_line_number"] == 1
    driver.get.assert_not_called()
    driver.current_url = lookup.build_bill_url("999")
    assert lookup.lookup_bill_item_locations(driver, "344042", ["Rapsberry Pi 4"], navigate=False) == {}


@pytest.mark.parametrize("answers,expected", [
    (["B03 Line 1"], (1, "B03")), (["b03, line 1"], (1, "B03")),
    (["Line 1", "B03"], (1, "B03")), (["100 dollars", "0", "1", "wrong", "B03"], (1, "B03")),
])
def test_reference_entry_accepts_combined_answer_and_recovers_typos(monkeypatch, answers, expected):
    replies = iter(answers)
    monkeypatch.setattr("builtins.input", lambda p: next(replies))
    assert lookup.prompt_verified_location() == expected


@pytest.mark.parametrize("answer,expected", [("", True), ("y", True), ("n", False), ("cancel", False)])
def test_engage_confirmation_defaults_yes(monkeypatch, answer, expected):
    monkeypatch.setattr("builtins.input", lambda p: answer)
    assert lookup.confirm_continue_to_engage() is expected


def test_blank_fee_reference_retries_without_discarding_browser(monkeypatch, capsys):
    answers = iter(["", "", "Bill 344042, B03, Line 1"])
    monkeypatch.setattr("builtins.input", lambda p: next(answers))
    assert lookup.prompt_fee_reference("Tax", "30.00") == "Bill 344042, B03, Line 1"
    assert "Both Chrome windows remain open" in capsys.readouterr().out


def test_fee_reference_can_be_explicitly_cancelled(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda p: "cancel")
    with pytest.raises(SystemExit, match="cancelled"):
        lookup.prompt_fee_reference("Tax", "30.00")


@pytest.mark.skipif(os.environ.get("MRG_RUN_BROWSER_TESTS") != "1", reason="Opt-in local Chrome DOM regression")
def test_real_dom_hidden_menu_budget_lookup(tmp_path):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    page = tmp_path / "bill.html"
    page.write_text("""<a href='#' onclick="document.querySelector('#budget').style.display='block';return false">MENU</a>
    <a id='budget' style='display:none' onclick="document.querySelector('#rows').style.display='block';return false">BUDGET</a>
    <div id='rows' style='display:none'>Budget Section:<h4>B03 - General Inventoried Goods</h4>
    <div><div>1.</div><div><a href='#'>Rapsberry Pi 4</a></div><div>B03 - General Inventoried Goods</div>
    <div>10 x $63.35</div><div>$633.50</div></div></div>""")
    options = Options()
    options.add_argument("--headless=new")
    driver = webdriver.Chrome(options=options)
    try:
        driver.get(page.as_uri())
        rows = lookup.parse_budget_text(lookup.open_budget_view(driver))
        assert rows["rapsberry pi 4"]["section_line_number"] == 1
        assert rows["rapsberry pi 4"]["section"] == "B03 - General Inventoried Goods"
    finally:
        driver.quit()
