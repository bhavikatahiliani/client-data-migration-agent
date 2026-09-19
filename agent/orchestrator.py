import json, uuid, os
import pandas as pd
from datetime import datetime, timezone
from .mapper import propose_mapping
from .cleaner import normalize_record
from .deduplicator import merge_records
from .validator import validate_record
from .audit import audit
from .db import get_db

def read_file(path):
    if path.lower().endswith('.csv'): return pd.read_csv(path, dtype=str)
    return pd.read_excel(path, dtype=str)

def create_migration(paths):
    migration_id=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
    db=get_db(); db.execute('INSERT INTO migrations(id,status,created_at,updated_at) VALUES(?,?,?,?)',(migration_id,'processing',now,now)); db.commit()
    audit('migration_started','Started migration',{'files':[os.path.basename(p) for p in paths]},migration_id)
    frames=[]
    for path in paths:
        df=read_file(path).fillna('')
        df.columns=[str(c).strip() for c in df.columns]
        frames.append(df)
        audit('file_ingested',f'Loaded {os.path.basename(path)}',{'rows':len(df),'columns':list(df.columns)},migration_id)
    allcols=[]; samples={}
    for df in frames:
        for c in df.columns:
            if c not in allcols: allcols.append(c); samples[c]=df[c].head(3).tolist()
    mapping, engine=propose_mapping(allcols,samples)
    records=[]; escalations=[]
    for source_col, info in mapping.items():
        if not info.get('target') or info.get('confidence',0)<.70:
            escalations.append({'kind':'mapping','title':f'Uncertain mapping: {source_col}','reason':info.get('reason','Low confidence'),
                'options':[x for x in ['employee_id','full_name','email','phone','date_of_birth','joining_date','department']],'evidence':{'source_column':source_col,'samples':samples[source_col],'proposal':info}})
    audit('mapping_proposed','Proposed source-to-target mappings',{'mapping':mapping,'engine':engine},migration_id)
    for df in frames:
        rename={c:info['target'] for c,info in mapping.items() if info.get('target')}
        clean=df.rename(columns=rename)
        
        # Preserve unresolved source columns so a human correction can be applied after review.
        keep_cols=[c for c in clean.columns if c in ['employee_id','full_name','email','phone','date_of_birth','joining_date','department'] or c in [sc for sc,info in mapping.items() if not info.get('target')]]
        clean=clean[keep_cols]
        for _,row in clean.iterrows():
            rr=normalize_record(row.to_dict())
            for sc,info in mapping.items():
                if not info.get('target') and sc in rr:
                    rr[f'_source:{sc}']=rr.pop(sc)
            records.append(rr)
    merged, dup_escalations=merge_records(records); escalations.extend(dup_escalations)
    audit('deduplication','Reconciled source records',{'source_rows':len(records),'canonical_rows':len(merged),'escalations':len(dup_escalations)},migration_id)
    valid=[]
    for r in merged:
        ok,payload,errors=validate_record(r)
        if not ok:
            # bounded repair: missing optional values are okay; mandatory errors escalate
            escalations.append({'kind':'validation','title':f'Validation failed for {r.get("employee_id") or "unknown employee"}',
              'reason':'Record failed target schema validation after normalization.', 'options':['approve_as_is','reject'], 'evidence':{'record':r,'errors':errors}})
        else: valid.append(payload)
    db.execute('UPDATE migrations SET status=?,total_source_rows=?,canonical_rows=?,updated_at=? WHERE id=?',('awaiting_review' if escalations else 'ready',len(records),len(valid),datetime.now(timezone.utc).isoformat(),migration_id))
    for e in escalations:
        db.execute('INSERT INTO escalations(migration_id,kind,title,reason,options,evidence,status,created_at) VALUES(?,?,?,?,?,?,?,?)',
                   (migration_id,e['kind'],e['title'],e['reason'],json.dumps(e['options']),json.dumps(e['evidence'],default=str),'open',now))
    for r in valid:
        db.execute('INSERT INTO records(migration_id,employee_id,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?)',
                   (migration_id,r['employee_id'],json.dumps(r), 'ready',now,now))
    db.commit(); audit('validation_complete','Validation complete',{'valid_records':len(valid),'open_escalations':len(escalations)},migration_id)
    return migration_id
