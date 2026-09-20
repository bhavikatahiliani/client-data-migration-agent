import json
import os
import re
import requests


TARGET_FIELDS = [
    'employee_id',
    'full_name',
    'email',
    'phone',
    'date_of_birth',
    'joining_date',
    'department'
]


SYNONYMS = {
    'employee_id': [
        'employee id',
        'emp id',
        'empid',
        'employee number',
        'staff id',
        'id',
        'worker id'
    ],
    'full_name': [
        'full name',
        'name',
        'employee name',
        'staff name',
        'employee'
    ],
    'email': [
        'email',
        'email address',
        'mail',
        'work email'
    ],
    'phone': [
        'phone',
        'mobile',
        'mobile number',
        'contact number',
        'telephone'
    ],
    'date_of_birth': [
        'dob',
        'birth date',
        'birthdate',
        'date of birth'
    ],
    'joining_date': [
        'joining date',
        'join date',
        'date joined',
        'employment start date',
        'start date'
    ],
    'department': [
        'department',
        'dept',
        'team',
        'function'
    ]
}


def normalize_column_name(source):
    return re.sub(r'[_\-]+', ' ', str(source).lower()).strip()


def token_score(source, target):
    s = normalize_column_name(source)

    if s in SYNONYMS.get(target, []):
        return 1.0

    if s.replace(' ', '') == target.replace('_', ''):
        return 0.95

    toks = set(s.split())
    tt = set(target.split('_'))

    return len(toks & tt) / max(len(toks | tt), 1)


def deterministic_mapping(source):
    """
    Protect obvious mappings from LLM mistakes.

    These mappings are safe enough to resolve without asking
    the human reviewer.
    """

    normalized = normalize_column_name(source)

    for target, aliases in SYNONYMS.items():
        if normalized in aliases:
            return {
                'target': target,
                'confidence': 0.99,
                'reason': 'Deterministic schema rule: exact column alias match.'
            }

    if normalized in {'start date', 'start_date'}:
        return {
            'target': None,
            'confidence': 0.52,
            'reason': (
                'Could mean joining_date or another employment-start field; '
                'semantic meaning is ambiguous.'
            )
        }

    return None


def ollama_map(columns, samples):
    print("using ollama for mapping")

    url = os.getenv(
        'OLLAMA_URL',
        'http://localhost:11434/api/generate'
    )

    model = os.getenv(
        'OLLAMA_MODEL',
        'gemma2:2b'
    )

    prompt = f'''
Map source columns to target fields.

Target fields:
{TARGET_FIELDS}

Return ONLY a JSON object where each source column maps to:

{{
  "target": "target_field_or_null",
  "confidence": number between 0 and 1,
  "reason": "short explanation"
}}

Do not invent target fields.

Source columns:
{columns}

Sample values:
{samples}
'''

    response = requests.post(
        url,
        json={
            'model': model,
            'prompt': prompt,
            'stream': False,
            'format': 'json'
        },
        timeout=12
    )

    print(f"ollama response: {response.text}")

    response.raise_for_status()

    return json.loads(response.json()['response'])


def deterministic_fallback(columns):
    result = {}

    for column in columns:

        forced = deterministic_mapping(column)

        if forced:
            result[column] = forced
            continue

        scores = sorted(
            (
                (target, token_score(column, target))
                for target in TARGET_FIELDS
            ),
            key=lambda x: x[1],
            reverse=True
        )

        top = scores[0]
        second = scores[1]

        confidence = top[1]

        if confidence >= 0.85:

            result[column] = {
                'target': top[0],
                'confidence': confidence,
                'reason': 'Strong name/alias match.'
            }

        elif confidence >= 0.55 and confidence - second[1] >= 0.20:

            result[column] = {
                'target': top[0],
                'confidence': max(confidence, 0.82),
                'reason': (
                    'Reasonable semantic match with clear margin '
                    'over alternatives.'
                )
            }

        else:

            result[column] = {
                'target': top[0] if confidence >= 0.55 else None,
                'confidence': confidence,
                'reason': 'Weak or ambiguous semantic match.'
            }

    return result


def propose_mapping(columns, samples):

    ai_result = {}

    # AI model
    try:
        data = ollama_map(columns, samples)

        if isinstance(data, dict):
            ai_result = data

    except Exception as exc:
        print(f"Ollama mapping unavailable: {exc}")

    result = {}

    for column in columns:

        # Deterministic protection
        forced = deterministic_mapping(column)

        if forced:
            result[column] = forced
            continue

        # Use AI proposal
        ai_info = ai_result.get(column)

        if isinstance(ai_info, dict):

            target = ai_info.get('target')
            confidence = float(ai_info.get('confidence', 0))
            reason = ai_info.get(
                'reason',
                'Semantic mapping proposed by the AI model.'
            )

            if target in TARGET_FIELDS:

                result[column] = {
                    'target': target,
                    'confidence': confidence,
                    'reason': reason
                }

                continue

        # fallback.
        fallback = deterministic_fallback([column])

        result[column] = fallback[column]

    return result, ('ollama_hybrid' if ai_result else 'deterministic_fallback')