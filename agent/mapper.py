import json, os, re, requests
TARGET_FIELDS=['employee_id','full_name','email','phone','date_of_birth','joining_date','department']
SYNONYMS={
 'employee_id':['employee id','emp id','empid','employee number','staff id','id','worker id'],
 'full_name':['full name','name','employee name','staff name','employee'],
 'email':['email','email address','mail','work email'],
 'phone':['phone','mobile','mobile number','contact number','telephone'],
 'date_of_birth':['dob','birth date','birthdate','date of birth'],
 'joining_date':['joining date','join date','date joined','employment start date','start date'],
 'department':['department','dept','team','function']}

def token_score(source,target):
    s=re.sub(r'[_\-]+',' ',source.lower()).strip()
    if s in SYNONYMS.get(target,[]): return 1.0
    if s.replace(' ','')==target.replace('_',''): return .95
    toks=set(s.split())
    tt=set(target.split('_'))
    return len(toks & tt)/max(len(toks|tt),1)

def ollama_map(columns, samples):
    url=os.getenv('OLLAMA_URL','http://localhost:11434/api/generate'); model=os.getenv('OLLAMA_MODEL','qwen2.5:3b')
    prompt=f'''Map source columns to target fields. Target fields: {TARGET_FIELDS}. Return ONLY JSON object where each source column maps to {{"target": field or null, "confidence": number 0-1, "reason": string}}. Do not invent fields. Source columns: {columns}. Sample values: {samples}'''
    r=requests.post(url,json={'model':model,'prompt':prompt,'stream':False,'format':'json'},timeout=12)
    r.raise_for_status(); return json.loads(r.json()['response'])

def propose_mapping(columns, samples):
    try:
        data=ollama_map(columns,samples)
        if isinstance(data,dict): return data, 'ollama'
    except Exception:
        pass
    result={}
    for c in columns:
        scores=sorted(((t,token_score(c,t)) for t in TARGET_FIELDS), key=lambda x:x[1], reverse=True)
        top, second=scores[0],scores[1]
        confidence=top[1]
        # Start Date is intentionally ambiguous for the demo.
        if c.lower().replace('_',' ').strip() in {'start date','start_date'}:
            result[c]={'target':None,'confidence':0.52,'reason':'Could mean joining_date or another employment-start field; semantic meaning is ambiguous.'}
        elif confidence>=0.85:
            result[c]={'target':top[0],'confidence':confidence,'reason':'Strong name/alias match.'}
        elif confidence>=0.55 and confidence-second[1] >= .20:
            result[c]={'target':top[0],'confidence':max(confidence,.82),'reason':'Reasonable semantic match with clear margin over alternatives.'}
        else:
            result[c]={'target':top[0] if confidence>=.55 else None,'confidence':confidence,'reason':'Weak or ambiguous semantic match.'}
    return result, 'deterministic_fallback'
