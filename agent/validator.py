import re
from datetime import datetime
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from typing import Optional

class Employee(BaseModel):
    model_config = ConfigDict(extra='ignore')
    employee_id: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    date_of_birth: Optional[str] = None
    joining_date: Optional[str] = None
    department: Optional[str] = None

    @field_validator('employee_id','full_name')
    @classmethod
    def required_text(cls, v):
        v = str(v).strip()
        if not v: raise ValueError('required field is empty')
        return v
    @field_validator('email')
    @classmethod
    def email_ok(cls, v):
        if v in (None, ''): return None
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v): raise ValueError('invalid email')
        return v.lower()

def validate_record(payload):
    try:
        e = Employee(**payload)
        return True, e.model_dump(), []
    except ValidationError as exc:
        return False, payload, [x['msg'] for x in exc.errors()]
