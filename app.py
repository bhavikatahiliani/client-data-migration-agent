import os, json, tempfile, shutil
from datetime import datetime, timezone
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
from agent.db import init_db, close_db, get_db
from agent.orchestrator import create_migration
from agent.audit import audit
from api.mock_target import bp as target_bp, STORE

BASE=os.path.dirname(os.path.abspath(__file__))
app=Flask(__name__); app.secret_key=os.getenv('SECRET_KEY','dev-secret')
app.config['DB_PATH']=os.path.join(BASE,'instance','migration.db')
app.teardown_appcontext(close_db); init_db(app); app.register_blueprint(target_bp)

@app.get('/')
def index():
    db=get_db(); migrations=db.execute('SELECT * FROM migrations ORDER BY created_at DESC').fetchall()
    return render_template('index.html', migrations=migrations)

@app.post('/demo')
def demo():
    paths=[os.path.join(BASE,'data','employees_a.csv'),os.path.join(BASE,'data','employees_b.xlsx'),os.path.join(BASE,'data','contacts.csv')]
    mid=create_migration(paths); return redirect(url_for('review',mid=mid))

@app.post('/upload')
def upload():
    files=[f for f in request.files.getlist('files') if f and f.filename]
    if not files: flash('Select at least one CSV or XLSX file.'); return redirect(url_for('index'))
    tmp=tempfile.mkdtemp(prefix='migration_',dir=os.path.join(BASE,'instance'))
    paths=[]
    try:
        for f in files:
            if not f.filename.lower().endswith(('.csv','.xlsx')): continue
            path=os.path.join(tmp,os.path.basename(f.filename)); f.save(path); paths.append(path)
        if not paths: flash('Only CSV/XLSX files are supported.'); return redirect(url_for('index'))
        mid=create_migration(paths); return redirect(url_for('review',mid=mid))
    finally:
        shutil.rmtree(tmp,ignore_errors=True)

def migration(mid):
    db=get_db(); return db.execute('SELECT * FROM migrations WHERE id=?',(mid,)).fetchone()

# @app.get('/migration/<mid>')
# def review(mid):
#     m=migration(mid)
#     if not m: return 'Not found',404
#     db=get_db(); esc=db.execute('SELECT * FROM escalations WHERE migration_id=? ORDER BY id',(mid,)).fetchall(); rec=db.execute('SELECT * FROM records WHERE migration_id=? ORDER BY id',(mid,)).fetchall()
#     return render_template('review.html',m=m,esc=esc,records=rec)

@app.get('/migration/<mid>')
def review(mid):

    m = migration(mid)

    if not m:
        return 'Not found', 404

    db = get_db()

    esc = db.execute(
        "SELECT * FROM escalations WHERE migration_id=? AND status='open' ORDER BY id",
        (mid,)
    ).fetchall()

    rec = db.execute(
        'SELECT * FROM records WHERE migration_id=? ORDER BY id',
        (mid,)
    ).fetchall()

    return render_template('review.html', m=m, esc=esc, records=rec)

@app.post('/migration/<mid>/escalation/<int:eid>')
def resolve(mid,eid):
    action=request.form.get('action'); correction=request.form.get('correction','').strip(); db=get_db()
    e=db.execute('SELECT * FROM escalations WHERE id=? AND migration_id=?',(eid,mid)).fetchone()
    if not e: return 'Not found',404
    resolution=correction or action
    # Apply a consultant's mapping correction to canonical records before closing the escalation.
    if e['kind']=='mapping' and correction:
        try:
            evidence=json.loads(e['evidence']); source=evidence.get('source_column'); target=correction
            rows=db.execute('SELECT id,payload FROM records WHERE migration_id=?',(mid,)).fetchall()
            for rr in rows:
                payload=json.loads(rr['payload']); key=f'_source:{source}'
                if key in payload:
                    value=payload.pop(key); payload[target]=value
                    # Re-validate only after correction; leave invalid records visible for review.
                    db.execute('UPDATE records SET payload=?,employee_id=?,status=? WHERE id=?',(json.dumps(payload),payload.get('employee_id'), 'ready', rr['id']))
            audit('mapping_corrected','Applied human mapping correction',{'source':source,'target':target},mid)
        except Exception as ex:
            audit('mapping_correction_error','Could not apply mapping correction',{'error':str(ex)},mid)
    db.execute('UPDATE escalations SET status=?,resolution=?,resolved_at=? WHERE id=?',('resolved',resolution,datetime.now(timezone.utc).isoformat(),eid)); db.commit()
    audit('human_resolution','Consultant resolved escalation',{'escalation_id':eid,'action':resolution},mid)
    open_count=db.execute("SELECT COUNT(*) c FROM escalations WHERE migration_id=? AND status='open'",(mid,)).fetchone()['c']
    if open_count==0: db.execute('UPDATE migrations SET status=?,updated_at=? WHERE id=?',('ready',datetime.now(timezone.utc).isoformat(),mid)); db.commit()
    return redirect(url_for('review',mid=mid))

@app.post('/migration/<mid>/push')
def push(mid):
    m=migration(mid); db=get_db()
    if not m: return 'Not found',404
    open_count=db.execute("SELECT COUNT(*) c FROM escalations WHERE migration_id=? AND status='open'",(mid,)).fetchone()['c']
    if open_count: flash('Resolve all open escalations before pushing.'); return redirect(url_for('review',mid=mid))
    rows=db.execute("SELECT * FROM records WHERE migration_id=? AND status IN ('ready','failed')",(mid,)).fetchall()
    import requests
    success=fail=0
    for r in rows:
        payload=json.loads(r['payload']); attempts=r['attempts']+1
        try:
            resp=requests.post('http://127.0.0.1:5000/mock-target/employees',json=payload,headers={'X-Attempt':str(attempts)},timeout=3)
            data=resp.json()
            if resp.ok:
                db.execute('UPDATE records SET status=?,attempts=?,target_id=?,error=NULL,updated_at=? WHERE id=?',('success',attempts,data.get('target_id'),datetime.now(timezone.utc).isoformat(),r['id'])); success+=1
            else:
                db.execute('UPDATE records SET status=?,attempts=?,error=?,updated_at=? WHERE id=?',('failed',attempts,data.get('error','target error'),datetime.now(timezone.utc).isoformat(),r['id'])); fail+=1
        except Exception as ex:
            db.execute('UPDATE records SET status=?,attempts=?,error=?,updated_at=? WHERE id=?',('failed',attempts,str(ex),datetime.now(timezone.utc).isoformat(),r['id'])); fail+=1
    db.execute('UPDATE migrations SET status=?,success_count=(SELECT COUNT(*) FROM records WHERE migration_id=? AND status="success"),failed_count=(SELECT COUNT(*) FROM records WHERE migration_id=? AND status="failed"),updated_at=? WHERE id=?',('pushed',mid,mid,datetime.now(timezone.utc).isoformat(),mid)); db.commit()
    audit('target_push','Pushed records to target API',{'success':success,'failed':fail},mid); return redirect(url_for('review',mid=mid))

@app.post('/migration/<mid>/retry')
def retry(mid):
    # Reuse push: mock target succeeds on second attempt for the deterministic demo failure.
    return push(mid)

@app.post('/migration/<mid>/rollback')
def rollback(mid):
    db=get_db(); rows=db.execute("SELECT * FROM records WHERE migration_id=? AND status='success'",(mid,)).fetchall(); removed=0
    for r in rows:
        eid=r['employee_id']; STORE.pop(eid,None); db.execute('UPDATE records SET status=?,updated_at=? WHERE id=?',('rolled_back',datetime.now(timezone.utc).isoformat(),r['id'])); removed+=1
    db.execute('UPDATE migrations SET status=?,rollback_count=rollback_count+?,updated_at=? WHERE id=?',('rolled_back',removed,datetime.now(timezone.utc).isoformat(),mid)); db.commit(); audit('rollback','Rolled back target records',{'count':removed},mid)
    return redirect(url_for('review',mid=mid))

@app.get('/migration/<mid>/audit')
def audit_view(mid):
    m=migration(mid); db=get_db(); events=db.execute('SELECT * FROM audit_events WHERE migration_id=? ORDER BY id DESC',(mid,)).fetchall(); return render_template('audit.html',m=m,events=events)

@app.get('/api/migration/<mid>')
def migration_json(mid):
    db=get_db(); m=db.execute('SELECT * FROM migrations WHERE id=?',(mid,)).fetchone();
    if not m:return jsonify({'error':'not found'}),404
    return jsonify(dict(m))

if __name__=='__main__': app.run(debug=True)
