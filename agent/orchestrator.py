import json
import uuid
import os

import pandas as pd

from datetime import datetime, timezone

from .mapper import propose_mapping
from .cleaner import normalize_record
from .deduplicator import merge_records
from .validator import validate_record
from .audit import audit
from .db import get_db

TARGET_FIELDS = [
    'employee_id',
    'full_name',
    'email',
    'phone',
    'date_of_birth',
    'joining_date',
    'department'
]


def read_file(path):
    if path.lower().endswith('.csv'):
        return pd.read_csv(path, dtype=str)

    return pd.read_excel(path, dtype=str)


def create_migration(paths):

    migration_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    db = get_db()

    db.execute(
        '''
        INSERT INTO migrations(
            id,
            status,
            created_at,
            updated_at
        )
        VALUES(?,?,?,?)
        ''',
        (
            migration_id,
            'processing',
            now,
            now
        )
    )

    db.commit()

    audit(
        'migration_started',
        'Started migration',
        {
            'files': [
                os.path.basename(p)
                for p in paths
            ]
        },
        migration_id
    )

    # 1. INGEST FILES
    frames = []

    for path in paths:

        df = read_file(path).fillna('')

        df.columns = [
            str(c).strip()
            for c in df.columns
        ]

        frames.append(df)

        audit(
            'file_ingested',
            f'Loaded {os.path.basename(path)}',
            {
                'rows': len(df),
                'columns': list(df.columns)
            },
            migration_id
        )

    # 2. COLLECT SOURCE COLUMNS + SAMPLES
    allcols = []
    samples = {}

    for df in frames:

        for column in df.columns:

            if column not in allcols:

                allcols.append(column)

                samples[column] = (
                    df[column]
                    .head(3)
                    .tolist()
                )

    # 3. AI / HYBRID FIELD MAPPING
    mapping, engine = propose_mapping(
        allcols,
        samples
    )

    escalations = []

    for source_col, info in mapping.items():

        target = info.get('target')
        confidence = info.get('confidence', 0)

        if not target or confidence < 0.70:

            escalations.append(
                {
                    'kind': 'mapping',
                    'title': f'Uncertain mapping: {source_col}',
                    'reason': info.get(
                        'reason',
                        'Low-confidence field mapping.'
                    ),
                    'options': [
                        'employee_id',
                        'full_name',
                        'email',
                        'phone',
                        'date_of_birth',
                        'joining_date',
                        'department'
                    ],
                    'evidence': {
                        'source_column': source_col,
                        'samples': samples.get(
                            source_col,
                            []
                        ),
                        'proposal': info
                    }
                }
            )

    audit(
        'mapping_proposed',
        'Proposed source-to-target mappings',
        {
            'mapping': mapping,
            'engine': engine
        },
        migration_id
    )

    # 4. NORMALIZE ALL SOURCE RECORDS
    records = []

    for df in frames:

        rename = {
            column: info['target']
            for column, info in mapping.items()
            if info.get('target')
        }

        clean = df.rename(
            columns=rename
        )

        # known target fields and unresolved source columns.
        unresolved_columns = [
            source_column
            for source_column, info in mapping.items()
            if not info.get('target')
        ]

        keep_columns = [
            column
            for column in clean.columns
            if (
                column in TARGET_FIELDS
                or column in unresolved_columns
            )
        ]

        clean = clean[keep_columns]

        for _, row in clean.iterrows():

            record = normalize_record(
                row.to_dict()
            )

            # Preserve unresolved fields for human review.
            for source_column, info in mapping.items():

                if (
                    not info.get('target')
                    and source_column in record
                ):

                    record[
                        f'_source:{source_column}'
                    ] = record.pop(
                        source_column
                    )

            records.append(record)

    # 5. DEDUPLICATION
    merged, duplicate_escalations = merge_records(
        records
    )

    escalations.extend(
        duplicate_escalations
    )

    audit(
        'deduplication',
        'Reconciled source records',
        {
            'source_rows': len(records),
            'canonical_rows': len(merged),
            'escalations': len(
                duplicate_escalations
            )
        },
        migration_id
    )

    # 6. VALIDATION
    valid_records = []
    review_records = []

    for record in merged:

        ok, payload, errors = validate_record(
            record
        )

        if not ok:

            review_records.append(
                {
                    'record': record,
                    'errors': errors
                }
            )

            escalations.append(
                {
                    'kind': 'validation',
                    'title': (
                        'Validation issue: '
                        f'{record.get("full_name") }'
                        'or '
                        'record.get("employee_id") '
                        'or "Unknown employee"}'
                    ),
                    'reason': (
                        'This record does not satisfy the '
                        'target schema. Correct the reported '
                        'value and validate again, or reject '
                        'the record.'
                    ),
                    'options': [
                        'correct',
                        'reject'
                    ],
                    'evidence': {
                        'record': record,
                        'errors': errors
                    }
                }
            )

        else:

            valid_records.append(
                payload
            )

    # 7. SAVE MIGRATION SUMMARY
    migration_status = (
        'awaiting_review'
        if escalations
        else 'ready'
    )

    db.execute(
        '''
        UPDATE migrations
        SET
            status=?,
            total_source_rows=?,
            canonical_rows=?,
            updated_at=?
        WHERE id=?
        ''',
        (
            migration_status,
            len(records),
            len(merged),
            datetime.now(timezone.utc).isoformat(),
            migration_id
        )
    )

    # 8. SAVE ALL ESCALATIONS
    for escalation in escalations:

        db.execute(
            '''
            INSERT INTO escalations(
                migration_id,
                kind,
                title,
                reason,
                options,
                evidence,
                status,
                created_at
            )
            VALUES(?,?,?,?,?,?,?,?)
            ''',
            (
                migration_id,
                escalation['kind'],
                escalation['title'],
                escalation['reason'],
                json.dumps(
                    escalation['options']
                ),
                json.dumps(
                    escalation['evidence'],
                    default=str
                ),
                'open',
                now
            )
        )

    # 9. SAVE VALID RECORDS
    for payload in valid_records:

        db.execute(
            '''
            INSERT INTO records(
                migration_id,
                employee_id,
                payload,
                status,
                created_at,
                updated_at
            )
            VALUES(?,?,?,?,?,?)
            ''',
            (
                migration_id,
                payload.get('employee_id'),
                json.dumps(payload),
                'ready',
                now,
                now
            )
        )

    # 10. SAVE INVALID RECORDS TOO
    for item in review_records:

        record = item['record']
        errors = item['errors']

        db.execute(
            '''
            INSERT INTO records(
                migration_id,
                employee_id,
                payload,
                status,
                error,
                created_at,
                updated_at
            )
            VALUES(?,?,?,?,?,?,?)
            ''',
            (
                migration_id,
                record.get('employee_id'),
                json.dumps(record),
                'awaiting_review',
                '; '.join(
                    str(error)
                    for error in errors
                ),
                now,
                now
            )
        )

    db.commit()

    audit(
        'validation_complete',
        'Validation complete',
        {
            'valid_records': len(
                valid_records
            ),
            'review_records': len(
                review_records
            ),
            'open_escalations': len(
                escalations
            )
        },
        migration_id
    )

    return migration_id