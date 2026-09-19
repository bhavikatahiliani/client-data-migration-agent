from agent.cleaner import clean_date, clean_phone
from agent.deduplicator import merge_records
from agent.validator import validate_record

def test_date_formats():
    assert clean_date('May 12, 1995') == '1995-05-12'
    assert clean_date('21/07/1998') == '1998-07-21'

def test_phone():
    assert clean_phone('+91 98765 43210') == '+919876543210'

def test_validation():
    ok, _, errors = validate_record({'employee_id':'1','full_name':'A','email':'bad'})
    assert not ok and errors

def test_exact_duplicate_merge():
    rows=[{'employee_id':'1','full_name':'A','email':'a@x.com'},{'employee_id':'1','full_name':'A','email':'a@x.com'}]
    merged, esc=merge_records(rows)
    assert len(merged)==1
