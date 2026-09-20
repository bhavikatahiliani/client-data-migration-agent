import re
import pandas as pd
from dateutil import parser

def clean_text(v):
    if pd.isna(v): return None
    s = re.sub(r'\s+', ' ', str(v)).strip()
    return s or None

def clean_email(v):
    s = clean_text(v)
    return s.lower() if s else None

def clean_phone(v):
    s = clean_text(v)
    if not s: return None
    digits = re.sub(r'\D', '', s)
    if digits.startswith('00'): digits = digits[2:]
    return '+' + digits if len(digits) >= 10 else s

def clean_date(v):
    s = clean_text(v)
    if not s:
        return None

    # format: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        try:
            dt = parser.parse(s, fuzzy=False)
            return dt.date().isoformat()
        except Exception:
            return None

    # Year-first numeric formats such as YYYY/MM/DD
    if re.match(r"^\d{4}[/-]\d{1,2}[/-]\d{1,2}$", s):
        try:
            dt = parser.parse(s, yearfirst=True, fuzzy=False)
            return dt.date().isoformat()
        except Exception:
            return None

    # Numeric dates such as DD/MM/YYYY or MM/DD/YYYY
    match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)

    if match:
        first = int(match.group(1))
        second = int(match.group(2))
        year = int(match.group(3))

        # Clearly DD/MM/YYYY
        if first > 12 and second <= 12:
            try:
                dt = parser.parse(s, dayfirst=True, fuzzy=False)
                return dt.date().isoformat()
            except Exception:
                return None

        # Clearly MM/DD/YYYY
        if second > 12 and first <= 12:
            try:
                dt = parser.parse(s, dayfirst=False, fuzzy=False)
                return dt.date().isoformat()
            except Exception:
                return None

        return None

    # "May 12, 1995", "14-Feb-1997", etc.
    try:
        dt = parser.parse(s, dayfirst=False, fuzzy=False)
        return dt.date().isoformat()
    except Exception:
        return None

def normalize_record(r):
    out = {k: clean_text(v) for k,v in r.items()}
    if 'email' in out: out['email'] = clean_email(out['email'])
    if 'phone' in out: out['phone'] = clean_phone(out['phone'])
    for k in ('date_of_birth','joining_date'):
        if k in out: out[k] = clean_date(out[k])
    return out
