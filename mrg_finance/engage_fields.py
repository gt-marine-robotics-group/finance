"""Resolve custom Engage controls by their associated labels, never document-wide text."""

from selenium.webdriver.common.by import By
from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
import json
from pathlib import Path

from .screenshot_capture import save_page_screenshot

from .purchase_validation import money, require_matching_total


class FormFieldError(RuntimeError):
    pass


def find_labeled_field(driver, labels, excluded=()):
    # Dynamic CampusLabs IDs cannot be hardcoded. Labels can use for=, ARIA,
    # or a question container, including conditional SGA questions.
    candidates = driver.execute_script(r"""
        const normalize = text => (text || '').toLowerCase().trim().replace(/\s+/g, ' ');
        const needles = arguments[0].map(normalize);
        const excluded = new Set(arguments[1]);
        const controls = [...document.querySelectorAll('input,textarea,select')]
          .filter(e => !excluded.has(e.id) && !['hidden','file','radio','checkbox','submit','button'].includes(e.type)
            && e.getClientRects().length && !e.disabled && !e.readOnly);
        const match = text => needles.some(n => n.startsWith('=')
          ? normalize(text) === n.slice(1) : normalize(text).includes(n));
        const found = new Set();
        for (const e of controls) {
          const text = [...(e.labels || [])].map(l => l.innerText).join(' ') + ' ' +
            (e.getAttribute('aria-label') || '') + ' ' +
            (e.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ');
          if (match(text)) found.add(e);
        }
        if (!found.size) {
          const nodes = [...document.querySelectorAll('label,legend,h2,h3,h4,p,span,div')]
            .filter(n => match(n.innerText) && ![...n.children].some(c => match(c.innerText)));
          for (const node of nodes) {
            for (let parent = node; parent && !['BODY','HTML','FORM'].includes(parent.tagName); parent = parent.parentElement) {
              const local = controls.filter(e => parent.contains(e));
              if (local.length === 1) { found.add(local[0]); break; }
              if (local.length > 1) break;
            }
          }
        }
        return [...found];
    """, list(labels), list(excluded))
    if len(candidates) != 1:
        raise FormFieldError(f"Expected one field for '{labels[0]}', found {len(candidates)}. "
                             "Check conditional questions in Engage; details were not placed in Description.")
    return candidates[0]


def _field_data(field):
    """Keep identifiers and values, never handles to controls that can be replaced."""
    field_id = field.get_attribute("id")
    return {"id": field_id, "identity": field_id or field.get_attribute("name") or getattr(field, "id", id(field)),
            "value": (field.get_attribute("value") or "").replace("\r\n", "\n"),
            "required": bool(field.get_attribute("required") or field.get_attribute("aria-required") == "true"),
            "single_line": getattr(field, "tag_name", "") == "input"}


def read_field(driver, resolve):
    try:
        return WebDriverWait(driver, 5, poll_frequency=.1,
            ignored_exceptions=(StaleElementReferenceException,)).until(lambda _: _field_data(resolve()))
    except TimeoutException as error:
        raise FormFieldError("Engage is still replacing the field. Wait for the form to finish loading, then retry.") from error


def fill_and_verify(driver, resolve, value, *, used=()):
    """Re-find after clear/type and avoid Enter keys submitting single-line answers."""
    value = str(value).replace("\r\n", "\n")

    def fill_current(_):
        current = _field_data(resolve())
        if current["identity"] in used:
            raise FormFieldError("Engage bill-reference and SGA fields resolved to the same control.")
        expected = "; ".join(value.splitlines()) if current["single_line"] else value
        if current["value"] != expected:
            resolve().clear()
            resolve().send_keys(expected)
        actual = _field_data(resolve())
        return actual if actual["value"] == expected else False

    try:
        return WebDriverWait(driver, 5, poll_frequency=.1,
            ignored_exceptions=(StaleElementReferenceException, ElementNotInteractableException)).until(fill_current)
    except TimeoutException as error:
        raise FormFieldError("Engage did not retain the field value after refreshing its controls. Wait and retry.") from error


def find_requested_amount(driver):
    candidates = driver.find_elements(By.ID, "Amount") or driver.find_elements(By.NAME, "Amount")
    if len(candidates) > 1:
        raise FormFieldError("Multiple requested amount fields found.")
    return candidates[0] if candidates else find_labeled_field(driver, ["requested amount"], ["Subject", "Description"])


def read_requested_amount(driver):
    return read_field(driver, lambda: find_requested_amount(driver))["value"]


def sga_funding_controls(driver, excluded):
    """Resolve each SGA checkbox's own write-in answer, including unchecked rows."""
    return driver.execute_script(r"""
        // __sga_funding_groups__: do not match SGA labels elsewhere in the form.
        return [...document.querySelectorAll('input[type=checkbox]')].flatMap(e => {
          if (!e.getClientRects().length) return [];
          const label = [...(e.labels || [])].map(l => l.innerText).join(' ').trim();
          const match = label.match(/^SGA\s+(Budget|Bill)\b/i);
          if (!match) return [];
          let field = document.getElementById('answerTextBox-' + e.id + '-free');
          if (!field) {
            for (let p=e.parentElement; p && !['FORM','BODY','HTML'].includes(p.tagName); p=p.parentElement) {
              const fields = [...p.querySelectorAll('textarea')];
              if (fields.length===1) { field=fields[0]; break; }
              if (fields.length>1) break;
            }
          }
          return [{kind:match[1].toLowerCase(), selected:e.checked, field}];
        });
    """, ["__sga_funding_groups__"], excluded)


def fill_native_payee(driver, payee, excluded):
    fields = {}
    for key in ("PayeeFirstName", "PayeeLastName", "PayeeStreet", "PayeeStreet2",
                "PayeeCity", "PayeeState", "PayeeZipCode"):
        candidates = [e for e in driver.find_elements(By.ID, key) if e.is_displayed() and e.is_enabled()]
        if len(candidates) > 1:
            raise FormFieldError(f"Ambiguous native {key} fields.")
        if candidates:
            fields[key] = True
    if not fields:
        return False
    if not all(key in fields for key in ("PayeeFirstName", "PayeeLastName")):
        raise FormFieldError("Engage's native payee name fields are incomplete; wait for the form to load.")
    # Keep a company's complete legal name across the native two-part name inputs.
    first, _, last = payee["name"].partition(" ")
    values = {"PayeeFirstName": first, "PayeeLastName": last,
              "PayeeStreet": payee.get("street"), "PayeeStreet2": payee.get("street2"),
              "PayeeCity": payee.get("city"), "PayeeState": payee.get("state"),
              "PayeeZipCode": payee.get("postal_code")}
    for key in fields:
        def resolve(key=key):
            candidates = [e for e in driver.find_elements(By.ID, key) if e.is_displayed() and e.is_enabled()]
            if len(candidates) != 1:
                raise FormFieldError(f"Expected one native {key} field, found {len(candidates)}.")
            return candidates[0]
        value = values[key]
        if value is not None:
            fill_and_verify(driver, resolve, value)
        else:
            field = read_field(driver, resolve)
            if field["required"] and not field["value"]:
                raise FormFieldError(f"Vendor data missing for {key}. Fill that field in Chrome, then retry.")
        excluded.append(key)
    return True


def fill_payee_email(driver, payee, excluded):
    """Fill the separate email question; don't silently skip a known vendor email."""
    labels = ["payee email", "payee e-mail", "vendor email"]
    email = payee.get("email")
    resolve = lambda: find_labeled_field(driver, labels, excluded)
    if email:
        field = fill_and_verify(driver, resolve, email)
        print(f"  Filled Payee Email: {email}")
        if field["id"]:
            excluded.append(field["id"])
        return
    try:
        field = read_field(driver, resolve)
    except FormFieldError:
        return
    if field["value"]:
        return
    if field["required"]:
        raise FormFieldError("No verified vendor email available. Fill Payee Email in Chrome, then retry.")
    print("  No verified vendor email available; review Payee Email in Chrome.")


def save_engage_diagnostic(driver, folder):
    """Capture the current form and control labels without exporting entered values."""
    try:
        path = Path(folder) / "engage_form_error.png"
        save_page_screenshot(driver, path)
        print(f"Engage form diagnostic: {path}")
        fields = driver.execute_script("return [...document.querySelectorAll('input,textarea,select')].map(e => ({id:e.id,name:e.name,type:e.type,labels:[...(e.labels || [])].map(l => l.innerText)}));")
        path.with_name("engage_fields.json").write_text(json.dumps(fields, indent=2), encoding="utf-8")
    except Exception:
        pass  # Diagnostics must not prevent same-browser recovery.


def run_engage_step(driver, folder, title, action, *, instructions=None, cancel_message=None):
    """Retry a failed stage without navigating away or tearing down either browser."""
    while True:
        try:
            return action()
        except Exception as error:
            print(f"\n{title} needs attention: {str(error).split('Stacktrace:')[0].strip()}\n" +
                  (instructions or "Both Chrome windows remain open. Correct the form or wait for it to load, then retry."))
            save_engage_diagnostic(driver, folder)
            while True:
                answer = input("Enter to retry this step in the current page, or 'cancel' to stop: ").strip().lower()
                if answer in ("cancel", "quit", "q"):
                    raise SystemExit(cancel_message or "Purchase preparation cancelled; comparison workbook and cart link are saved.")
                if not answer:
                    break
                print("Press Enter to retry, or type 'cancel'.")


def fill_purchase_fields(driver, *, amount, cart_total, bill_refs, payee, sga_lines="", funding_lines=None):
    excluded = ["Subject", "Description", "Amount"]
    amount_data = fill_and_verify(driver, lambda: find_requested_amount(driver), f"{money(amount):.2f}")
    require_matching_total(cart_total, amount_data["value"])
    used = [amount_data["identity"]]
    if amount_data["id"]:
        excluded.append(amount_data["id"])
    groups = funding_lines or {"bill": sga_lines}
    native_groups = [{"kind": c["kind"], "selected": c["selected"]}
                     for c in sga_funding_controls(driver, excluded) if isinstance(c, dict)]
    if native_groups:
        selected = {c["kind"] for c in native_groups if c["selected"]}
        if selected != set(groups):
            raise FormFieldError(f"Select {' and '.join('SGA ' + k.title() for k in groups)} in Engage. "
                                 f"Currently selected: {', '.join(selected) or 'none'}.")
    field = fill_and_verify(driver, lambda: find_labeled_field(driver,
        ["What is the Budget/Bill # and Request Line #", "Budget/Bill #"], excluded), bill_refs, used=used)
    used.append(field["identity"])
    if field["id"]:
        excluded.append(field["id"])
    for kind, text in groups.items():
        if native_groups:
            def resolve(kind=kind):
                current = [c for c in sga_funding_controls(driver, excluded) if isinstance(c, dict)]
                if {c["kind"] for c in current if c["selected"]} != set(groups):
                    raise FormFieldError("The selected SGA funding options changed. Correct them in Chrome and retry.")
                matches = [c["field"] for c in current if c["kind"] == kind and c["selected"] and c["field"] is not None]
                if len(matches) != 1:
                    raise FormFieldError(f"Could not resolve the selected SGA {kind.title()} write-in answer.")
                if not matches[0].is_displayed() or not matches[0].is_enabled():
                    raise FormFieldError(f"SGA {kind.title()} answer has not loaded yet.")
                return matches[0]
        else:
            labels = (["SGA Budget", "Include total $ reimbursement amount below"] if kind == "budget" else
                      ["Include Bill # and total reimbursement amount below", "SGA Bill", "Bill Details"])
            resolve = lambda labels=labels: find_labeled_field(driver, labels, excluded)
        field = fill_and_verify(driver, resolve, text, used=used)
        used.append(field["identity"])
        if field["id"]:
            excluded.append(field["id"])

    if fill_native_payee(driver, payee, excluded):
        fill_payee_email(driver, payee, excluded)
        return read_requested_amount(driver)

    name_labels = ["payee name", "name of payee", "vendor name", "who is the payee", "=payee"]
    try:
        name_field = fill_and_verify(driver, lambda: find_labeled_field(driver, name_labels, excluded), payee["name"])
    except FormFieldError:
        text = "\n".join(str(payee[k]) for k in ("name", "address", "phone", "email") if payee.get(k))
        info_field = fill_and_verify(driver, lambda: find_labeled_field(driver, ["payee information", "payee details"], excluded), text)
        if info_field["id"]:
            excluded.append(info_field["id"])
        fill_payee_email(driver, payee, excluded)
        return read_requested_amount(driver)
    if name_field["id"]:
        excluded.append(name_field["id"])
    optional = (
        (["payee address", "vendor address"], "address"),
        (["payee phone", "vendor phone"], "phone"),
    )
    for labels, key in optional:
        try:
            field = read_field(driver, lambda: find_labeled_field(driver, labels, excluded))
        except FormFieldError:
            continue
        if not payee.get(key):
            if field["required"]:
                raise FormFieldError(f"Required {labels[0]} was not found on the vendor's official site.")
            continue
        fill_and_verify(driver, lambda: find_labeled_field(driver, labels, excluded), payee[key])
    fill_payee_email(driver, payee, excluded)
    return read_requested_amount(driver)
