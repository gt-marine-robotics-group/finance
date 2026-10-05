"""Resolve custom Engage controls by their associated labels, never document-wide text."""

from selenium.webdriver.common.by import By

from .purchase_validation import money, require_matching_total


class FormFieldError(RuntimeError):
    pass


def find_labeled_field(driver, labels, excluded=()):
    # Dynamic CampusLabs IDs cannot be hardcoded. Labels can use for=, ARIA,
    # or a question container, including conditional SGA questions.
    candidates = driver.execute_script(r"""
        const needles = arguments[0].map(x => x.toLowerCase());
        const excluded = new Set(arguments[1]);
        const controls = [...document.querySelectorAll('input,textarea,select')]
          .filter(e => !excluded.has(e.id) && !['hidden','file','radio','checkbox','submit','button'].includes(e.type)
            && e.getClientRects().length && !e.disabled && !e.readOnly);
        const match = text => needles.some(n => n.startsWith('=')
          ? (text || '').toLowerCase().trim().replace(/\s+/g, ' ') === n.slice(1)
          : (text || '').toLowerCase().includes(n));
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


def fill_purchase_fields(driver, *, amount, cart_total, bill_refs, sga_lines, payee):
    excluded = ["Subject", "Description", "Amount"]
    amount_fields = driver.find_elements(By.ID, "Amount") or driver.find_elements(By.NAME, "Amount")
    amount_field = amount_fields[0] if amount_fields else find_labeled_field(driver, ["requested amount"], excluded)
    fill_and_verify(amount_field, f"{money(amount):.2f}")
    require_matching_total(cart_total, amount_field.get_attribute("value"))
    used = [amount_field]
    for labels, text in (
        (["What is the Budget/Bill # and Request Line #", "Budget/Bill #"], bill_refs),
        (["Include Bill # and total reimbursement amount below", "SGA Bill", "Bill Details"], sga_lines),
    ):
        field = find_labeled_field(driver, labels, excluded)
        if field in used:
            raise FormFieldError("Engage bill-reference and SGA fields resolved to the same control.")
        fill_and_verify(field, text)
        used.append(field)
        if field.get_attribute("id"):
            excluded.append(field.get_attribute("id"))

    name_labels = ["payee name", "name of payee", "vendor name", "who is the payee", "=payee"]
    try:
        name_field = find_labeled_field(driver, name_labels, excluded)
        fill_and_verify(name_field, payee["name"])
    except FormFieldError:
        info_field = find_labeled_field(driver, ["payee information", "payee details"], excluded)
        text = "\n".join(str(payee[k]) for k in ("name", "address", "phone", "email") if payee.get(k))
        fill_and_verify(info_field, text)
        return amount_field
    if name_field.get_attribute("id"):
        excluded.append(name_field.get_attribute("id"))
    optional = (
        (["payee address", "vendor address"], "address"),
        (["payee phone", "vendor phone"], "phone"),
        (["payee email", "vendor email"], "email"),
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
    return amount_field
