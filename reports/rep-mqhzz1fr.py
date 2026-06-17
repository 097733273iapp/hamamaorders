# -*- coding: utf-8 -*-
"""
rep-mqhzz1fr — "קריאת נתונים מכספית"

דוח עזר שמאגד את רוב המידע שכספית חושפת ב-API שלה, על ידי קריאה (read-only)
של כמה שיותר ENDPOINTS במכה אחת. המטרה: בסיס שעליו נבנה אחר כך מלא דוחות.

הדוח:
- מתחבר ל-API של כספית (טוקן נטען מפרטי התחברות שב-config_loader / משתני סביבה).
- עובר על רשימת ENDPOINTS (ניתנת להגדרה ב-config תחת המפתח "endpoints").
- לכל endpoint: מושך עמוד/ים, סופר רשומות, ושומר דגימה.
- מפיק פלט טקסט מסכם (format: text), config-driven, בלי סודות קשיחים.

הרצה:
  CASPIT_USER=.. CASPIT_PWD=.. CASPIT_OSEK=.. python reports/rep-mqhzz1fr.py
"""
import json
import os
import sys
import urllib.request
import urllib.error

# לאפשר ייבוא של config_loader מתיקיית השורש של המאגר
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config_loader  # noqa: E402

REPORT_ID = "rep-mqhzz1fr"
BASE_URL = os.environ.get("CASPIT_BASE_URL", "https://app.caspit.biz/api/v1")
HTTP_TIMEOUT = int(os.environ.get("CASPIT_TIMEOUT", "30"))

# רשימת ברירת מחדל של ENDPOINTS לקריאה (read-only, GET, עם דפדוף page).
# ניתן לעקוף דרך config: report["endpoints"] = ["Customers", "Products", ...]
# הערה: כספית לא חושפת "רשימת endpoints". הרשימה כאן משלבת מה שאומת מול
# התיעוד (Products/Customers/Documents/Accounts/Suppliers/Expenses/Currencies/
# Users/Log/Hashavshevet/Pdf) יחד עם מועמדים ידועים נוספים. הדוח מדווח לכל
# endpoint אם הוחזרו רשומות או שגיאה — כך שמות לא־קיימים מסומנים ✗ אוטומטית.
DEFAULT_ENDPOINTS = [
    "Accounts",
    "Customers",
    "Suppliers",
    "Agents",
    "Products",
    "ProductCategories",
    "ProductGroups",
    "PriceLists",
    "Documents",
    "Expenses",
    "Currencies",
    "PaymentTerms",
    "Banks",
    "Branches",
    "Users",
    "Log",
]


def _request(url, data=None, timeout=HTTP_TIMEOUT):
    """בקשת HTTP בסיסית. data=dict -> POST JSON, אחרת GET."""
    headers = {"Accept": "application/json"}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers,
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    raw = raw.strip()
    try:
        return json.loads(raw)
    except ValueError:
        # תגובת הטוקן מגיעה לעיתים כמחרוזת עם מרכאות
        return raw.strip('"')


def get_token(creds):
    """POST api/v1/Token -> מחרוזת טוקן (תקף ~10 דקות, חלון מתגלגל)."""
    token = _request("%s/Token" % BASE_URL, data=creds)
    if not isinstance(token, str) or not token:
        raise RuntimeError("Unexpected token response: %r" % (token,))
    return token


def fetch_endpoint(endpoint, token, max_pages=1):
    """
    מושך עד max_pages עמודים מ-endpoint נתון (50 רשומות לעמוד).
    מחזיר (records, error). שגיאה לא מפילה את כל הדוח.
    """
    records = []
    try:
        for page in range(max_pages):
            url = "%s/%s?token=%s&page=%d" % (BASE_URL, endpoint, token, page)
            data = _request(url)
            # מבני תגובה אפשריים: רשימה ישירה, או dict עם Results/Items
            if isinstance(data, dict):
                items = data.get("Results") or data.get("Items") or data.get("Value") or []
            elif isinstance(data, list):
                items = data
            else:
                items = []
            if not items:
                break
            records.extend(items)
            if len(items) < 50:
                break
        return records, None
    except urllib.error.HTTPError as e:
        return records, "HTTP %s" % e.code
    except Exception as e:  # noqa: BLE001
        return records, str(e)


def build_report(cfg=None):
    cfg = cfg or config_loader.load_public()
    report = config_loader.get_report(REPORT_ID, cfg) or {}
    endpoints = report.get("endpoints") or DEFAULT_ENDPOINTS
    max_pages = int(report.get("maxPages", 1))

    creds = config_loader.caspit_credentials()
    token = get_token(creds)

    company = (cfg.get("company") or {}).get("name", "")
    lines = []
    lines.append("📊 קריאת נתונים מכספית — %s" % company)
    lines.append("מקור: %s | endpoints: %d" % (BASE_URL, len(endpoints)))
    lines.append("")

    total = 0
    for ep in endpoints:
        records, err = fetch_endpoint(ep, token, max_pages=max_pages)
        if err:
            lines.append("• %-18s ✗ (%s)" % (ep, err))
            continue
        count = len(records)
        total += count
        sample_keys = ""
        if records and isinstance(records[0], dict):
            sample_keys = ", ".join(list(records[0].keys())[:6])
        suffix = (" | שדות: %s" % sample_keys) if sample_keys else ""
        lines.append("• %-18s %d רשומות%s" % (ep, count, suffix))

    lines.append("")
    lines.append("סה\"כ רשומות שנקראו: %d" % total)
    return "\n".join(lines)


def main():
    try:
        print(build_report())
    except Exception as e:  # noqa: BLE001
        print("שגיאה בהפקת הדוח %s: %s" % (REPORT_ID, e))
        sys.exit(1)


if __name__ == "__main__":
    main()
