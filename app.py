import os
import json
import tempfile
import shutil

from datetime import datetime, timezone

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    redirect,
    url_for,
    flash
)

from agent.db import (
    init_db,
    close_db,
    get_db
)

from agent.orchestrator import create_migration

from agent.validator import validate_record

from agent.audit import audit

from api.mock_target import (
    bp as target_bp,
    STORE
)


BASE = os.path.dirname(
    os.path.abspath(__file__)
)


app = Flask(__name__)

app.secret_key = os.getenv(
    'SECRET_KEY',
    'dev-secret'
)

app.config['DB_PATH'] = os.path.join(
    BASE,
    'instance',
    'migration.db'
)


app.teardown_appcontext(
    close_db
)

init_db(app)

app.register_blueprint(
    target_bp
)


@app.get('/')
def index():

    db = get_db()

    migrations = db.execute(
        '''
        SELECT *
        FROM migrations
        ORDER BY created_at DESC
        '''
    ).fetchall()

    return render_template(
        'index.html',
        migrations=migrations
    )


@app.post('/demo')
def demo():

    paths = [
        os.path.join(
            BASE,
            'data',
            'employees_a.csv'
        ),
        os.path.join(
            BASE,
            'data',
            'employees_b.xlsx'
        ),
        os.path.join(
            BASE,
            'data',
            'contacts.csv'
        )
    ]

    migration_id = create_migration(
        paths
    )

    return redirect(
        url_for(
            'review',
            mid=migration_id
        )
    )

@app.post('/upload') # FILE UPLOAD
def upload():

    files = [
        file
        for file in request.files.getlist('files')
        if file and file.filename
    ]

    if not files:

        flash(
            'Select at least one CSV or XLSX file.'
        )

        return redirect(
            url_for('index')
        )

    temp_directory = tempfile.mkdtemp(
        prefix='migration_',
        dir=os.path.join(
            BASE,
            'instance'
        )
    )

    paths = []

    try:

        for file in files:

            if not file.filename.lower().endswith(
                ('.csv', '.xlsx')
            ):
                continue

            path = os.path.join(
                temp_directory,
                os.path.basename(
                    file.filename
                )
            )

            file.save(path)

            paths.append(path)

        if not paths:

            flash(
                'Only CSV/XLSX files are supported.'
            )

            return redirect(
                url_for('index')
            )

        migration_id = create_migration(
            paths
        )

        return redirect(
            url_for(
                'review',
                mid=migration_id
            )
        )

    finally:

        shutil.rmtree(
            temp_directory,
            ignore_errors=True
        )


def migration(mid): # MIGRATION LOOKUP

    db = get_db()

    return db.execute(
        '''
        SELECT *
        FROM migrations
        WHERE id=?
        ''',
        (mid,)
    ).fetchone()


@app.get('/migration/<mid>') # HUMAN REVIEW PAGE
def review(mid):

    migration_row = migration(mid)

    if not migration_row:

        return 'Not found', 404

    db = get_db()

    raw_escalations = db.execute(
        '''
        SELECT *
        FROM escalations
        WHERE migration_id=?
          AND status='open'
        ORDER BY id
        ''',
        (mid,)
    ).fetchall()

    escalations = []

    for row in raw_escalations:

        item = dict(row)

        try:

            item['evidence'] = json.loads(
                item.get('evidence') or '{}'
            )

        except Exception:

            item['evidence'] = {}

        try:

            item['options'] = json.loads(
                item.get('options') or '[]'
            )

        except Exception:

            item['options'] = []

        escalations.append(item)

    records = db.execute(
        '''
        SELECT *
        FROM records
        WHERE migration_id=?
        ORDER BY id
        ''',
        (mid,)
    ).fetchall()

    return render_template(
        'review.html',
        m=migration_row,
        esc=escalations,
        records=records
    )


def find_record_for_escalation( # FIND RECORD FOR ESCALATION
    migration_id,
    evidence_record
):

    db = get_db()

    rows = db.execute(
        '''
        SELECT id, payload, status
        FROM records
        WHERE migration_id=?
        ORDER BY id
        ''',
        (migration_id,)
    ).fetchall()

    expected_employee_id = (
        evidence_record.get('employee_id')
    )

    expected_email = (
        evidence_record.get('email')
    )

    expected_name = (
        evidence_record.get('full_name')
    )


    if expected_employee_id: # Employee ID match

        for row in rows:

            payload = json.loads(
                row['payload']
            )

            if (
                payload.get('employee_id')
                == expected_employee_id
            ):

                return row


    if expected_email: # Email match

        for row in rows:

            payload = json.loads(
                row['payload']
            )

            if (
                payload.get('email')
                == expected_email
            ):

                return row

    if expected_name: #Full name match

        for row in rows:

            payload = json.loads(
                row['payload']
            )

            if (
                payload.get('full_name')
                == expected_name
            ):

                return row

    return None


@app.post(
    '/migration/<mid>/escalation/<int:eid>' # HUMAN REVIEW ACTION
)
def resolve(mid, eid):

    action = request.form.get(
        'action',
        ''
    ).strip()

    correction = request.form.get(
        'correction',
        ''
    ).strip()

    correction_field = request.form.get(
        'correction_field',
        ''
    ).strip()

    db = get_db()

    escalation = db.execute(
        '''
        SELECT *
        FROM escalations
        WHERE id=?
          AND migration_id=?
        ''',
        (
            eid,
            mid
        )
    ).fetchone()

    if not escalation:

        return 'Not found', 404

    if action == 'reject':     # REJECT

        try:

            evidence = json.loads(
                escalation['evidence'] or '{}'
            )

            evidence_record = evidence.get(
                'record',
                {}
            )

            # Validation escalation:
            # mark the corresponding record rejected.
            if (
                escalation['kind']
                == 'validation'
            ):

                record = find_record_for_escalation(
                    mid,
                    evidence_record
                )

                if record:

                    db.execute(
                        '''
                        UPDATE records
                        SET
                            status=?,
                            error=?,
                            updated_at=?
                        WHERE id=?
                        ''',
                        (
                            'rejected',
                            'Rejected during human review.',
                            datetime.now(
                                timezone.utc
                            ).isoformat(),
                            record['id']
                        )
                    )

            # Mapping escalation:
            elif (
                escalation['kind']
                == 'mapping'
            ):

                source = evidence.get(
                    'source_column'
                )

                if source:

                    source_key = (
                        f'_source:{source}'
                    )

                    rows = db.execute(
                        '''
                        SELECT id, payload
                        FROM records
                        WHERE migration_id=?
                        ''',
                        (mid,)
                    ).fetchall()

                    for row in rows:

                        payload = json.loads(
                            row['payload']
                        )

                        if source_key in payload:

                            db.execute(
                                '''
                                UPDATE records
                                SET
                                    status=?,
                                    error=?,
                                    updated_at=?
                                WHERE id=?
                                ''',
                                (
                                    'rejected',
                                    (
                                        'Rejected because '
                                        f'the source field '
                                        f'"{source}" was not '
                                        'mapped.'
                                    ),
                                    datetime.now(
                                        timezone.utc
                                    ).isoformat(),
                                    row['id']
                                )
                            )

            db.execute(
                '''
                UPDATE escalations
                SET
                    status=?,
                    resolution=?,
                    resolved_at=?
                WHERE id=?
                ''',
                (
                    'resolved',
                    'reject',
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    eid
                )
            )

            db.commit()

            audit(
                'human_resolution',
                'Reviewer rejected a record/escalation',
                {
                    'escalation_id': eid,
                    'action': 'reject'
                },
                mid
            )

        except Exception as exc:

            db.rollback()

            audit(
                'human_resolution_error',
                'Could not reject escalation',
                {
                    'escalation_id': eid,
                    'error': str(exc)
                },
                mid
            )

            flash(
                'Could not reject this item.'
            )

            return redirect(
                url_for(
                    'review',
                    mid=mid
                )
            )

    elif (
        action == 'correct'
        and escalation['kind']
        == 'validation' 
    ):  # CORRECT VALIDATION ISSUE

        if (
            not correction
            or not correction_field
        ):

            flash(
                'Please provide a correction before saving.'
            )

            return redirect(
                url_for(
                    'review',
                    mid=mid
                )
            )

        try:

            evidence = json.loads(
                escalation['evidence']
                or '{}'
            )

            evidence_record = evidence.get(
                'record',
                {}
            )

            record = find_record_for_escalation(
                mid,
                evidence_record
            )

            if not record:

                flash(
                    'Could not find the affected record.'
                )

                return redirect(
                    url_for(
                        'review',
                        mid=mid
                    )
                )

            payload = json.loads(
                record['payload']
            )

            # Apply human correction.
            payload[
                correction_field
            ] = correction

            is_valid, validated_payload, errors = (
                validate_record(payload)
            )

            if not is_valid:

                # Correction did not fix the record.
                # Keep escalation open.
                db.execute(
                    '''
                    UPDATE records
                    SET
                        payload=?,
                        employee_id=?,
                        status=?,
                        error=?,
                        updated_at=?
                    WHERE id=?
                    ''',
                    (
                        json.dumps(payload),
                        payload.get(
                            'employee_id'
                        ),
                        'awaiting_review',
                        '; '.join(
                            str(error)
                            for error in errors
                        ),
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                        record['id']
                    )
                )

                evidence['record'] = payload
                evidence['errors'] = errors

                db.execute(
                    '''
                    UPDATE escalations
                    SET evidence=?
                    WHERE id=?
                    ''',
                    (
                        json.dumps(
                            evidence,
                            default=str
                        ),
                        eid
                    )
                )

                db.commit()

                flash(
                    'The correction is still invalid. '
                    'Please correct the reported value.'
                )

                return redirect(
                    url_for(
                        'review',
                        mid=mid
                    )
                )
            # Validation passed.

            db.execute(
                '''
                UPDATE records
                SET
                    payload=?,
                    employee_id=?,
                    status=?,
                    error=NULL,
                    updated_at=?
                WHERE id=?
                ''',
                (
                    json.dumps(
                        validated_payload
                    ),
                    validated_payload.get(
                        'employee_id'
                    ),
                    'ready',
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    record['id']
                )
            )

            # Close escalation only after validation passes.
            db.execute(
                '''
                UPDATE escalations
                SET
                    status=?,
                    resolution=?,
                    resolved_at=?
                WHERE id=?
                ''',
                (
                    'resolved',
                    f'Corrected {correction_field}',
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    eid
                )
            )

            db.commit()

            audit(
                'human_resolution',
                'Reviewer corrected and revalidated a validation issue',
                {
                    'escalation_id': eid,
                    'record_id': record['id'],
                    'field': correction_field,
                    'action': 'correct',
                    'validation': 'passed'
                },
                mid
            )

        except Exception as exc:

            db.rollback()

            audit(
                'human_resolution_error',
                'Could not apply validation correction',
                {
                    'escalation_id': eid,
                    'error': str(exc)
                },
                mid
            )

            flash(
                'Could not apply the correction.'
            )

            return redirect(
                url_for(
                    'review',
                    mid=mid
                )
            )

    elif (
        action == 'correct'
        and escalation['kind']
        == 'mapping'
    ):     # CORRECT MAPPING ISSUE

        if not correction:

            flash(
                'Please select a target field.'
            )

            return redirect(
                url_for(
                    'review',
                    mid=mid
                )
            )

        try:

            evidence = json.loads(
                escalation['evidence']
                or '{}'
            )

            source = evidence.get(
                'source_column'
            )

            target = correction

            if target not in {
                'employee_id',
                'full_name',
                'email',
                'phone',
                'date_of_birth',
                'joining_date',
                'department'
            }:

                flash(
                    'Invalid target field selected.'
                )

                return redirect(
                    url_for(
                        'review',
                        mid=mid
                    )
                )

            rows = db.execute(
                '''
                SELECT id, payload
                FROM records
                WHERE migration_id=?
                ''',
                (mid,)
            ).fetchall()

            updated = 0

            for row in rows:

                payload = json.loads(
                    row['payload']
                )

                source_key = (
                    f'_source:{source}'
                )

                if source_key not in payload:
                    continue

                value = payload.pop(
                    source_key
                )

                payload[target] = value

                # Re-run validation after mapping correction.
                is_valid, validated_payload, errors = (
                    validate_record(payload)
                )

                if is_valid:

                    db.execute(
                        '''
                        UPDATE records
                        SET
                            payload=?,
                            employee_id=?,
                            status=?,
                            error=NULL,
                            updated_at=?
                        WHERE id=?
                        ''',
                        (
                            json.dumps(
                                validated_payload
                            ),
                            validated_payload.get(
                                'employee_id'
                            ),
                            'ready',
                            datetime.now(
                                timezone.utc
                            ).isoformat(),
                            row['id']
                        )
                    )

                else:

                    db.execute(
                        '''
                        UPDATE records
                        SET
                            payload=?,
                            employee_id=?,
                            status=?,
                            error=?,
                            updated_at=?
                        WHERE id=?
                        ''',
                        (
                            json.dumps(payload),
                            payload.get(
                                'employee_id'
                            ),
                            'awaiting_review',
                            '; '.join(
                                str(error)
                                for error in errors
                            ),
                            datetime.now(
                                timezone.utc
                            ).isoformat(),
                            row['id']
                        )
                    )

                updated += 1

            # Close the mapping escalation.
            db.execute(
                '''
                UPDATE escalations
                SET
                    status=?,
                    resolution=?,
                    resolved_at=?
                WHERE id=?
                ''',
                (
                    'resolved',
                    f'Mapped {source} to {target}',
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    eid
                )
            )

            db.commit()

            audit(
                'mapping_corrected',
                'Reviewer corrected a field mapping',
                {
                    'escalation_id': eid,
                    'source': source,
                    'target': target,
                    'records_updated': updated
                },
                mid
            )

        except Exception as exc:

            db.rollback()

            audit(
                'mapping_correction_error',
                'Could not apply the mapping correction',
                {
                    'escalation_id': eid,
                    'error': str(exc)
                },
                mid
            )

            flash(
                'Could not apply the mapping correction.'
            )

            return redirect(
                url_for(
                    'review',
                    mid=mid
                )
            )

    else:

        flash(
            'Unsupported review action.'
        )

        return redirect(
            url_for(
                'review',
                mid=mid
            )
        )
 # UPDATE MIGRATION STATUS
    open_count = db.execute(
        '''
        SELECT COUNT(*) AS c
        FROM escalations
        WHERE migration_id=?
          AND status='open'
        ''',
        (mid,)
    ).fetchone()['c']

    if open_count == 0:

        db.execute(
            '''
            UPDATE migrations
            SET
                status=?,
                updated_at=?
            WHERE id=?
            ''',
            (
                'ready',
                datetime.now(
                    timezone.utc
                ).isoformat(),
                mid
            )
        )

        db.commit()

    return redirect(
        url_for(
            'review',
            mid=mid
        )
    )

# PUSH TO TARGET
@app.post('/migration/<mid>/push')
def push(mid):

    migration_row = migration(mid)

    db = get_db()

    if not migration_row:

        return 'Not found', 404

    # Never push while there are unresolved escalations.
    open_count = db.execute(
        '''
        SELECT COUNT(*) AS c
        FROM escalations
        WHERE migration_id=?
          AND status='open'
        ''',
        (mid,)
    ).fetchone()['c']

    if open_count:

        flash(
            'Resolve all open escalations before pushing.'
        )

        return redirect(
            url_for(
                'review',
                mid=mid
            )
        )
    rows = db.execute(
        '''
        SELECT *
        FROM records
        WHERE migration_id=?
          AND status IN ('ready', 'failed')
        ORDER BY id
        ''',
        (mid,)
    ).fetchall()

    import requests

    success = 0
    failed = 0

    for row in rows:

        payload = json.loads(
            row['payload']
        )

        attempts = row['attempts'] + 1

        try:
            print("\n========== FINAL DATA BEING PUSHED TO TARGET ==========")
            print(json.dumps(payload, indent=2, default=str))
            print("=======================================================\n")

            response = requests.post(
                'http://127.0.0.1:5000/mock-target/employees',
                json=payload,
                headers={
                    'X-Attempt': str(attempts)
                },
                timeout=3
            )

            data = response.json()

            if response.ok:

                db.execute(
                    '''
                    UPDATE records
                    SET
                        status=?,
                        attempts=?,
                        target_id=?,
                        error=NULL,
                        updated_at=?
                    WHERE id=?
                    ''',
                    (
                        'success',
                        attempts,
                        data.get('target_id'),
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                        row['id']
                    )
                )

                success += 1

            else:

                db.execute(
                    '''
                    UPDATE records
                    SET
                        status=?,
                        attempts=?,
                        error=?,
                        updated_at=?
                    WHERE id=?
                    ''',
                    (
                        'failed',
                        attempts,
                        data.get(
                            'error',
                            'target error'
                        ),
                        datetime.now(
                            timezone.utc
                        ).isoformat(),
                        row['id']
                    )
                )

                failed += 1

        except Exception as exc:

            db.execute(
                '''
                UPDATE records
                SET
                    status=?,
                    attempts=?,
                    error=?,
                    updated_at=?
                WHERE id=?
                ''',
                (
                    'failed',
                    attempts,
                    str(exc),
                    datetime.now(
                        timezone.utc
                    ).isoformat(),
                    row['id']
                )
            )

            failed += 1

    db.execute(
        '''
        UPDATE migrations
        SET
            status=?,
            success_count=(
                SELECT COUNT(*)
                FROM records
                WHERE migration_id=?
                  AND status='success'
            ),
            failed_count=(
                SELECT COUNT(*)
                FROM records
                WHERE migration_id=?
                  AND status='failed'
            ),
            updated_at=?
        WHERE id=?
        ''',
        (
            'pushed',
            mid,
            mid,
            datetime.now(
                timezone.utc
            ).isoformat(),
            mid
        )
    )

    db.commit()

    audit(
        'target_push',
        'Pushed records to target API',
        {
            'success': success,
            'failed': failed
        },
        mid
    )

    return redirect(
        url_for(
            'review',
            mid=mid
        )
    )
# RETRY FAILED
@app.post('/migration/<mid>/retry')
def retry(mid):

    # Reuse push().
    # Mock target intentionally succeeds on attempt 2
    # for the deterministic demo failure.
    return push(mid)

# ROLLBACK
@app.post('/migration/<mid>/rollback')
def rollback(mid):

    db = get_db()

    rows = db.execute(
        '''
        SELECT *
        FROM records
        WHERE migration_id=?
          AND status='success'
        ''',
        (mid,)
    ).fetchall()

    removed = 0

    for row in rows:

        employee_id = row['employee_id']

        STORE.pop(
            employee_id,
            None
        )

        db.execute(
            '''
            UPDATE records
            SET
                status=?,
                updated_at=?
            WHERE id=?
            ''',
            (
                'rolled_back',
                datetime.now(
                    timezone.utc
                ).isoformat(),
                row['id']
            )
        )

        removed += 1

    db.execute(
        '''
        UPDATE migrations
        SET
            status=?,
            rollback_count=rollback_count+?,
            updated_at=?
        WHERE id=?
        ''',
        (
            'rolled_back',
            removed,
            datetime.now(
                timezone.utc
            ).isoformat(),
            mid
        )
    )

    db.commit()

    audit(
        'rollback',
        'Rolled back target records',
        {
            'count': removed
        },
        mid
    )

    return redirect(
        url_for(
            'review',
            mid=mid
        )
    )

# AUDIT LOG
@app.get('/migration/<mid>/audit')
def audit_view(mid):

    migration_row = migration(mid)

    db = get_db()

    events = db.execute(
        '''
        SELECT *
        FROM audit_events
        WHERE migration_id=?
        ORDER BY id DESC
        ''',
        (mid,)
    ).fetchall()

    return render_template(
        'audit.html',
        m=migration_row,
        events=events
    )

# MIGRATION API
@app.get('/api/migration/<mid>')
def migration_json(mid):

    db = get_db()

    migration_row = db.execute(
        '''
        SELECT *
        FROM migrations
        WHERE id=?
        ''',
        (mid,)
    ).fetchone()

    if not migration_row:

        return jsonify(
            {
                'error': 'not found'
            }
        ), 404

    return jsonify(
        dict(migration_row)
    )

# RUN
if __name__ == '__main__':
    app.run(
        debug=True
    )