import random, time
from flask import Blueprint, request, jsonify
bp=Blueprint('target',__name__,url_prefix='/mock-target')
STORE={}
@bp.post('/employees')
def create_employee():
    payload=request.get_json(force=True)
    eid=payload.get('employee_id')
    if not eid or not payload.get('full_name'): return jsonify({'success':False,'error':'missing mandatory field'}),400
    # failure for IDs ending in 7, succeeds after the first attempt with a retry key.
    attempt=int(request.headers.get('X-Attempt','1'))
    if str(eid).endswith('7') and attempt==1: return jsonify({'success':False,'error':'simulated upstream timeout'}),503
    STORE[eid]=payload
    return jsonify({'success':True,'target_id':f'TGT-{eid}'}),201
@bp.delete('/employees/<eid>')
def delete_employee(eid):
    existed=eid in STORE
    STORE.pop(eid,None)
    return jsonify({'success':existed})
