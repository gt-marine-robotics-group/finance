"""Resolve custom Engage controls by their associated labels, never document-wide text."""

from selenium.webdriver.common.by import By
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


def fill_and_verify(field, value):
    value = str(value)
    field.clear()
    field.send_keys(value)
    actual = (field.get_attribute("value") or "").replace("\r\n", "\n")
    if actual != value.replace("\r\n", "\n"):
        raise FormFieldError("Engage did not retain the field value.")


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
            fields[key] = candidates[0]
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
    for key, field in fields.items():
        value = values[key]
        if value is not None:
            fill_and_verify(field, value)
        elif (field.get_attribute("required") or field.get_attribute("aria-required") == "true") and not field.get_attribute("value"):
            raise FormFieldError(f"Vendor data missing for {key}. Fill that field in Chrome, then retry.")
        excluded.append(key)
    return True


def fill_payee_email(driver, payee, excluded):
    """Fill the separate email question; don't silently skip a known vendor email."""
    labels = ["payee email", "payee e-mail", "vendor email"]
    email = payee.get("email")
    if email:
        field = find_labeled_field(driver, labels, excluded)
        fill_and_verify(field, email)
        print(f"  Filled Payee Email: {email}")
        if field.get_attribute("id"):
            excluded.append(field.get_attribute("id"))
        return
    try:
        field = find_labeled_field(driver, labels, excluded)
    except FormFieldError:
        return
    if field.get_attribute("value"):
        return
    if field.get_attribute("required") or field.get_attribute("aria-required") == "true":
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


def run_engage_step(driver, folder, title, action):
    """Retry a failed stage without navigating away or tearing down either browser."""
    while True:
        try:
            return action()
        except Exception as error:
            print(f"\n{title} needs attention: {str(error).split('Stacktrace:')[0].strip()}\n"
                  "Both Chrome windows remain open. Correct the form or wait for it to load, then retry.")
            save_engage_diagnostic(driver, folder)
            while True:
                answer = input("Enter to retry this step in the current page, or 'cancel' to stop: ").strip().lower()
                if answer in ("cancel", "quit", "q"):
                    raise SystemExit("Purchase preparation cancelled; comparison workbook and cart link are saved.")
                if not answer:
                    break
                print("Press Enter to retry, or type 'cancel'.")


def fill_purchase_fields(driver, *, amount, cart_total, bill_refs, payee, sga_lines="", funding_lines=None):
    excluded = ["Subject", "Description", "Amount"]
    amount_fields = driver.find_elements(By.ID, "Amount") or driver.find_elements(By.NAME, "Amount")
    amount_field = amount_fields[0] if amount_fields else find_labeled_field(driver, ["requested amount"], excluded)
    fill_and_verify(amount_field, f"{money(amount):.2f}")
    require_matching_total(cart_total, amount_field.get_attribute("value"))
    used = [amount_field]
    groups = funding_lines or {"bill": sga_lines}
    controls = sga_funding_controls(driver, excluded)
    native_groups = [c for c in controls if isinstance(c, dict)]
    if native_groups:
        selected = {c["kind"] for c in native_groups if c["selected"]}
        if selected != set(groups):
            raise FormFieldError(f"Select {' and '.join('SGA ' + k.title() for k in groups)} in Engage. "
                                 f"Currently selected: {', '.join(selected) or 'none'}.")
    field = find_labeled_field(driver, ["What is the Budget/Bill # and Request Line #", "Budget/Bill #"], excluded)
    fill_and_verify(field, bill_refs)
    used.append(field)
    if field.get_attribute("id"):
        excluded.append(field.get_attribute("id"))
    for kind, text in groups.items():
        if native_groups:
            matches = [c["field"] for c in native_groups if c["kind"] == kind and c["selected"] and c["field"] is not None]
            if len(matches) != 1:
                raise FormFieldError(f"Could not resolve the selected SGA {kind.title()} write-in answer.")
            field = matches[0]
            if not field.is_displayed() or not field.is_enabled():
                raise FormFieldError(f"SGA {kind.title()} answer has not loaded yet.")
        else:
            labels = (["SGA Budget", "Include total $ reimbursement amount below"] if kind == "budget" else
                      ["Include Bill # and total reimbursement amount below", "SGA Bill", "Bill Details"])
            field = find_labeled_field(driver, labels, excluded)
        if field in used:
            raise FormFieldError("Engage bill-reference and SGA fields resolved to the same control.")
        fill_and_verify(field, text)
        used.append(field)
        if field.get_attribute("id"):
            excluded.append(field.get_attribute("id"))

    if fill_native_payee(driver, payee, excluded):
        fill_payee_email(driver, payee, excluded)
        return amount_field

    name_labels = ["payee name", "name of payee", "vendor name", "who is the payee", "=payee"]
    try:
        name_field = find_labeled_field(driver, name_labels, excluded)
        fill_and_verify(name_field, payee["name"])
    except FormFieldError:
        info_field = find_labeled_field(driver, ["payee information", "payee details"], excluded)
        text = "\n".join(str(payee[k]) for k in ("name", "address", "phone", "email") if payee.get(k))
        fill_and_verify(info_field, text)
        if info_field.get_attribute("id"):
            excluded.append(info_field.get_attribute("id"))
        fill_payee_email(driver, payee, excluded)
        return amount_field
    if name_field.get_attribute("id"):
        excluded.append(name_field.get_attribute("id"))
    optional = (
        (["payee address", "vendor address"], "address"),
        (["payee phone", "vendor phone"], "phone"),
    )
    for labels, key in optional:
        try:
            field = find_labeled_field(driver, labels, excluded)
        except FormFieldError:
            continue
        if not payee.get(key):
            if field.get_attribute("required") or field.get_attribute("aria-required") == "true":
                raise FormFieldError(f"Required {labels[0]} was not found on the vendor's official site.")
            continue
        fill_and_verify(field, payee[key])
    fill_payee_email(driver, payee, excluded)
    return amount_field
