"""
Database initialization script.
Run this to create the initial database schema and seed data.
"""
from app import create_app, db
from app.models import UserRole, User, Facility


def init_database():
    """Initialize database with schema and seed data."""
    app = create_app('development')
    
    with app.app_context():
        # Create all tables
        print("Creating database tables...")
        db.create_all()
        
        # Create user roles
        print("Creating user roles...")
        roles_data = [
            {
                'name': 'Admin',
                'description': 'System administrator with full access',
                'can_create': True,
                'can_edit_own': True,
                'can_edit_all': True,
                'can_delete_own': True,
                'can_delete_all': True,
                'can_review': True,
                'can_approve': True,
                'can_export': True,
                'can_manage_users': True
            },
            {
                'name': 'Reviewer',
                'description': 'Can review and approve/reject initiatives',
                'can_create': True,
                'can_edit_own': True,
                'can_edit_all': False,
                'can_delete_own': True,
                'can_delete_all': False,
                'can_review': True,
                'can_approve': True,
                'can_export': True,
                'can_manage_users': False
            },
            {
                'name': 'User',
                'description': 'Regular user who can create and manage own initiatives',
                'can_create': True,
                'can_edit_own': True,
                'can_edit_all': False,
                'can_delete_own': True,
                'can_delete_all': False,
                'can_review': False,
                'can_approve': False,
                'can_export': True,
                'can_manage_users': False
            },
            {
                'name': 'Read-Only',
                'description': 'Can only view initiatives',
                'can_create': False,
                'can_edit_own': False,
                'can_edit_all': False,
                'can_delete_own': False,
                'can_delete_all': False,
                'can_review': False,
                'can_approve': False,
                'can_export': True,
                'can_manage_users': False
            },
            {
                'name': 'Finance',
                'description': 'Finance users with access to rebate extraction only',
                'can_create': False,
                'can_edit_own': False,
                'can_edit_all': False,
                'can_delete_own': False,
                'can_delete_all': False,
                'can_review': False,
                'can_approve': False,
                'can_export': True,
                'can_manage_users': False
            }
        ]
        
        for role_data in roles_data:
            existing_role = UserRole.query.filter_by(name=role_data['name']).first()
            if not existing_role:
                role = UserRole(**role_data)
                db.session.add(role)
                print(f"  - Created role: {role_data['name']}")
        
        db.session.commit()
        
        # Create facilities
        print("Creating facilities...")
        facilities_data = [
            {'code': 'MMC', 'name': 'Montefiore Medical Center'},
            {'code': 'BURKE', 'name': 'Burke Rehabilitation Hospital'},
            {'code': 'AECOM', 'name': 'Albert Einstein College of Medicine'},
            {'code': 'MMVO', 'name': 'Montefiore Mount Vernon'},
            {'code': 'MSSO', 'name': 'Montefiore Spring Valley'},
            {'code': 'NYACK', 'name': 'Nyack Hospital'},
            {'code': 'SLCH', 'name': 'St. Luke\'s Cornwall Hospital'},
            {'code': 'WPH', 'name': 'White Plains Hospital'}
        ]
        
        for facility_data in facilities_data:
            existing_facility = Facility.query.filter_by(code=facility_data['code']).first()
            if not existing_facility:
                facility = Facility(**facility_data)
                db.session.add(facility)
                print(f"  - Created facility: {facility_data['code']}")
        
        db.session.commit()
        
        print("\nDatabase initialization complete!")
        print("\nNext steps:")
        print("1. Users will be auto-created when they first login via IIS authentication")
        print("2. Manually assign roles to users in the database or create an admin interface")
        print("3. Run 'flask db init' if you want to use Flask-Migrate for future migrations")


if __name__ == '__main__':
    init_database()
