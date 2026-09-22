"""Merge read-only role aliases, preserving users. Preview unless --apply is given."""
import argparse
import os

from sqlalchemy import create_engine, text

from app.config import config


def migrate(environment, apply=False):
    engine = create_engine(config[environment].SQLALCHEMY_DATABASE_URI)
    with engine.begin() as connection:
        connection.exec_driver_sql('SET XACT_ABORT ON; SET LOCK_TIMEOUT 15000;')
        database = connection.execute(text('SELECT DB_NAME()')).scalar_one()
        roles = connection.execute(text(
            'SELECT id, name FROM user_roles WITH (UPDLOCK, HOLDLOCK) ORDER BY id'
        )).mappings().all()
        aliases = [role for role in roles if ''.join(
            ch for ch in role['name'].lower() if ch.isalnum()
        ) == 'readonly']
        if not aliases:
            raise RuntimeError('No read-only role found; nothing was changed.')
        canonical = next((role for role in aliases if role['name'] == 'ReadOnly'), aliases[0])
        print(f'{database}: roles to consolidate: {[(r["id"], r["name"]) for r in aliases]}')
        before_users = dict(connection.execute(text('SELECT id, role_id FROM users')).all())
        alias_ids = {role['id'] for role in aliases}
        affected = sum(role_id in alias_ids for role_id in before_users.values())
        print(f'Canonical role: ReadOnly (ID {canonical["id"]}); {affected} users preserved.')
        if not apply:
            print('Preview only. Pass --apply to commit.')
            return
        for role in aliases:
            if role['id'] != canonical['id']:
                connection.execute(text('UPDATE users SET role_id = :canonical WHERE role_id = :old'),
                                   {'canonical': canonical['id'], 'old': role['id']})
                connection.execute(text('DELETE FROM user_roles WHERE id = :id'), {'id': role['id']})
        connection.execute(text('''
            UPDATE user_roles SET name = 'ReadOnly',
                description = 'Can view initiatives; cannot modify data or download attachments',
                can_create = 0, can_edit_own = 0, can_edit_all = 0,
                can_delete_own = 0, can_delete_all = 0, can_review = 0,
                can_approve = 0, can_export = 0, can_manage_users = 0,
                updated_at = GETDATE()
            WHERE id = :id
        '''), {'id': canonical['id']})
        expected = {uid: canonical['id'] if rid in alias_ids else rid for uid, rid in before_users.items()}
        after_users = dict(connection.execute(text('SELECT id, role_id FROM users')).all())
        if after_users != expected:
            raise RuntimeError('User preservation check failed; rolling back.')
        print('User preservation verified; consolidation committed when this transaction exits.')
    engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', choices=('development', 'testing', 'production'),
                        default=os.getenv('ENVIRONMENT', os.getenv('FLASK_ENV', 'production')).lower())
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    migrate(args.environment, args.apply)
