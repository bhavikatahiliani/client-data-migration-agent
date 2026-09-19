from difflib import SequenceMatcher

def norm_name(s): return ''.join(ch.lower() for ch in (s or '') if ch.isalnum())

def merge_records(records):
    groups=[]; escalations=[]
    by_id={}
    for r in records:
        eid=r.get('employee_id')
        if eid: by_id.setdefault(eid, []).append(r)
    consumed=set()
    for eid, rows in by_id.items():
        if len(rows)==1: continue
        merged=dict(rows[0]); conflict={}
        for row in rows[1:]:
            for k,v in row.items():
                if not v: continue
                if not merged.get(k): merged[k]=v
                elif merged[k] != v: conflict.setdefault(k,set()).update([merged[k],v])
        if conflict:
            escalations.append({'kind':'conflicting_duplicate','title':f'Conflicting values for employee {eid}',
              'reason':'Records share the same employee_id but contain conflicting non-empty values.',
              'options':['keep_first','keep_latest','reject_merge'], 'evidence':{'employee_id':eid,'rows':rows,'conflicts':{k:list(v) for k,v in conflict.items()}}})
        groups.append(merged); consumed.add(eid)
    # fuzzy candidates without a shared ID
    remaining=[r for r in records if not r.get('employee_id') or r.get('employee_id') not in consumed]
    used=set()
    for i,a in enumerate(remaining):
        if i in used: continue
        best=None
        for j in range(i+1,len(remaining)):
            if j in used: continue
            b=remaining[j]
            score=SequenceMatcher(None,norm_name(a.get('full_name')),norm_name(b.get('full_name'))).ratio()
            if a.get('email') and b.get('email') and a['email']==b['email']: score=max(score,.98)
            if score >= .96: best=(j,score,b); break
        if best:
            j,score,b=best; used.update([i,j])
            if a.get('email') and b.get('email') and a['email']!=b['email']:
                escalations.append({'kind':'possible_duplicate','title':'Possible duplicate with conflicting email',
                  'reason':f'Name similarity {score:.0%}, but emails differ.', 'options':['merge','keep_separate'], 'evidence':{'left':a,'right':b,'score':score}})
            else:
                m=dict(a)
                for k,v in b.items(): m[k]=m.get(k) or v
                groups.append(m)
        else: groups.append(a)
    return groups, escalations
