# -*- coding: utf-8 -*-
"""
config_loader — טעינת קונפיגורציה משותפת לכל הדוחות (monorepo).

עקרונות:
- כל הקונפיג נטען מ-data/<company>/public.json. אין סודות קשיחים בקוד.
- סודות (משתמש/סיסמה/עוסק מורשה של כספית) נטענים אך ורק ממשתני סביבה.
- הפונקציות כאן משותפות לכל הסקריפטים תחת reports/.

משתני סביבה רלוונטיים:
  COMPANY            מזהה החברה (ברירת מחדל: hamama)
  CASPIT_USER        שם משתמש לכספית
  CASPIT_PWD         סיסמה לכספית
  CASPIT_OSEK        מספר עוסק מורשה
  CASPIT_BUSINESS_ID מזהה עסק (אופציונלי)
"""
import json
import os

# שורש המאגר = התיקייה שבה נמצא הקובץ הזה
ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_COMPANY = os.environ.get("COMPANY", "hamama")


def _public_path(company=None):
    company = company or DEFAULT_COMPANY
    return os.path.join(ROOT, "data", company, "public.json")


def load_public(company=None):
    """טוען ומחזיר את public.json של החברה כ-dict."""
    path = _public_path(company)
    if not os.path.exists(path):
        raise FileNotFoundError("public.json not found: %s" % path)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def all_reports(cfg=None, company=None):
    """מחזיר את כל הדוחות (system + custom) כרשימה אחת."""
    cfg = cfg or load_public(company)
    return list(cfg.get("systemReports", []) or []) + list(cfg.get("customReports", []) or [])


def get_report(report_id, cfg=None, company=None):
    """מאתר רשומת דוח לפי id מתוך systemReports / customReports."""
    for r in all_reports(cfg, company):
        if r.get("id") == report_id:
            return r
    return None


# שמות שדות נרדפים שעשויים להופיע בקובץ סודות קיים (גמיש לכל קונבנציה).
_CRED_ALIASES = {
    "UserName": ("UserName", "user", "username", "CaspitUser", "caspitUser"),
    "Password": ("Password", "pwd", "password", "pass", "CaspitPwd"),
    "OsekMorsheNumber": ("OsekMorsheNumber", "osek", "osekMorshe", "OsekMorshe", "osekMorsheNumber"),
    "BusinessId": ("BusinessId", "businessId", "business_id"),
}

# מיקומי ברירת מחדל לקובץ סודות מקומי (לא נכנסים ל-git; ראה .gitignore).
_SECRET_FILENAMES = ("caspit_secrets.json", "secrets.json", ".caspit.json")


def _load_secret_file():
    """
    מאתר וקורא קובץ סודות מקומי, אם קיים. סדר עדיפות:
      1. נתיב מפורש ב-CASPIT_SECRETS
      2. אחד מ-_SECRET_FILENAMES, בשורש המאגר ובתיקיית האב
    מחזיר dict (אולי ריק). לעולם לא נשמר ב-git.
    """
    candidates = []
    explicit = os.environ.get("CASPIT_SECRETS")
    if explicit:
        candidates.append(explicit)
    for base in (ROOT, os.path.dirname(ROOT)):
        for name in _SECRET_FILENAMES:
            candidates.append(os.path.join(base, name))
    for path in candidates:
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # תמיכה במבנה מקונן: {"caspit": {...}}
                if isinstance(data, dict) and "caspit" in data and isinstance(data["caspit"], dict):
                    return data["caspit"]
                if isinstance(data, dict):
                    return data
            except (ValueError, OSError):
                continue
    return {}


def _pick(d, canonical):
    for alias in _CRED_ALIASES[canonical]:
        if d.get(alias):
            return d[alias]
    return None


def caspit_credentials():
    """
    מחזיר את פרטי ההתחברות לכספית — בלי סודות קשיחים בקוד.
    מקורות (לפי עדיפות): משתני סביבה, ואז קובץ סודות מקומי (CASPIT_SECRETS
    או caspit_secrets.json/secrets.json). שמות השדות גמישים כדי להתחבר
    לקובץ קודים קיים. מעלה RuntimeError אם חסרים פרטי חובה.
    """
    env = {
        "UserName": os.environ.get("CASPIT_USER"),
        "Password": os.environ.get("CASPIT_PWD"),
        "OsekMorsheNumber": os.environ.get("CASPIT_OSEK"),
        "BusinessId": os.environ.get("CASPIT_BUSINESS_ID"),
    }
    file_creds = _load_secret_file()
    creds = {}
    for canonical in ("UserName", "Password", "OsekMorsheNumber", "BusinessId"):
        creds[canonical] = env.get(canonical) or _pick(file_creds, canonical) or ""

    missing = [c for c in ("UserName", "Password", "OsekMorsheNumber") if not creds[c]]
    if missing:
        raise RuntimeError(
            "Missing Caspit credentials (%s). Set env CASPIT_USER/CASPIT_PWD/"
            "CASPIT_OSEK, or point CASPIT_SECRETS to your existing codes file."
            % ", ".join(missing))
    return creds


def _management_index(cfg):
    """ממפה שם איש קשר -> רשומת ההנהלה (טלפון/מייל אם קיים)."""
    idx = {}
    for m in cfg.get("management", []) or []:
        if m.get("name"):
            idx[m["name"]] = m
    return idx


def resolve_delivery(report, cfg=None, company=None):
    """
    מתרגם את delivery של הדוח ליעדים ממשיים.
    מחזיר dict: {"whatsapp": [phones...], "email": [addresses...]}.
    הפניות מסוג person נפתרות מול רשימת ההנהלה לפי שם.
    """
    cfg = cfg or load_public(company)
    mgmt = _management_index(cfg)
    delivery = (report or {}).get("delivery", {}) or {}

    phones, emails = [], []
    for entry in delivery.get("whatsapp", []) or []:
        if entry.get("type") == "person":
            person = mgmt.get(entry.get("ref"))
            if person and person.get("phone"):
                phones.append(person["phone"])
        elif entry.get("type") == "number" and entry.get("ref"):
            phones.append(entry["ref"])
    for entry in delivery.get("email", []) or []:
        ref = entry.get("ref") if isinstance(entry, dict) else entry
        if ref:
            emails.append(ref)

    return {"whatsapp": phones, "email": emails}
