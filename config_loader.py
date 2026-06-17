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


def caspit_credentials():
    """
    מחזיר את פרטי ההתחברות לכספית ממשתני הסביבה בלבד.
    מעלה RuntimeError אם חסרים פרטי חובה — אף פעם לא משובצים בקוד.
    """
    user = os.environ.get("CASPIT_USER")
    pwd = os.environ.get("CASPIT_PWD")
    osek = os.environ.get("CASPIT_OSEK")
    business_id = os.environ.get("CASPIT_BUSINESS_ID", "")
    missing = [name for name, val in
               (("CASPIT_USER", user), ("CASPIT_PWD", pwd), ("CASPIT_OSEK", osek))
               if not val]
    if missing:
        raise RuntimeError(
            "Missing Caspit credentials in environment: %s" % ", ".join(missing))
    return {
        "UserName": user,
        "Password": pwd,
        "OsekMorsheNumber": osek,
        "BusinessId": business_id,
    }


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
