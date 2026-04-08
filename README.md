# Savings Tracker v2.0 - Flask Edition

A modernized Flask-based application for tracking procurement savings initiatives at Montefiore Medicine.

## Features

- **RESTful API** - Complete API for all CRUD operations
- **Normalized Database** - Improved database schema with proper relationships
- **Role-Based Access Control** - Fine-grained permissions system
- **Audit Logging** - Complete audit trail of all changes
- **Email Notifications** - Automated notifications using Microsoft Graph
- **IIS Windows Authentication** - Integrated with Windows Auth for SSO
- **Three Initiative Types**:
  - Cost Savings
  - Rebates
  - Cost Avoidance

## Technology Stack

- **Backend**: Flask 3.0, SQLAlchemy ORM, pyodbc
- **Database**: Microsoft SQL Server (savingstracker_v2)
- **Authentication**: IIS Windows Authentication
- **Email**: Microsoft Graph API
- **Server**: IIS with FastCGI

## Project Structure

```
Savings_Tracker_v2_Flask/
├── app/
│   ├── __init__.py           # Application factory
│   ├── config.py             # Configuration settings
│   ├── views.py              # HTML page routes
│   ├── models/               # SQLAlchemy models
│   │   ├── user.py
│   │   ├── initiative.py
│   │   ├── cost_savings.py
│   │   ├── rebate.py
│   │   ├── cost_avoidance.py
│   │   ├── facility_allocation.py
│   │   ├── file_tracking.py
│   │   └── audit.py
│   ├── api/                  # API endpoints
│   │   ├── auth.py
│   │   ├── initiatives.py
│   │   ├── cost_savings.py
│   │   ├── rebate.py
│   │   └── cost_avoidance.py
│   ├── utils/                # Utilities
│   │   ├── decorators.py     # Auth decorators
│   │   ├── validators.py     # Data validation
│   │   └── email.py          # Email notifications
│   ├── static/               # Static files (CSS, JS, images)
│   └── templates/            # HTML templates
├── migrations/               # Database migrations
├── logs/                     # Application logs
├── tests/                    # Unit tests
├── .env                      # Environment variables
├── .env.example              # Example environment file
├── requirements.txt          # Python dependencies
├── web.config                # IIS configuration
├── init_db.py               # Database initialization
└── run.py                    # Application entry point
```

## Installation

### 1. Prerequisites

- Python 3.11+
- SQL Server with ODBC Driver 17 for SQL Server
- IIS (for production deployment)
- Access to network share for file storage

### 2. Clone and Setup

```bash
# From the parent folder that contains this project
cd .\Savings_Tracker_v2_Flask

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
# Create or update the environment file in the project root
notepad .env
```

**Required settings in `.env`:**
- Database connection details
- `MS_GRAPH_TENANT_ID`, `MS_GRAPH_CLIENT_ID`, `MS_GRAPH_CLIENT_SECRET`
- `FILE_STORAGE_PATH`
- `APP_URL`

**Admin-managed email settings:**
- Sender is fixed to `procurementdatateam@montefiore.org`
- CC is fixed to `procurementdatateam@montefiore.org`
- Receiver fields can be updated from the Admin email settings page and support multiple addresses separated by commas or semicolons

### 4. Initialize Database

```bash
# Create database schema and seed initial data
python init_db.py
```

This will create:
- All database tables with proper relationships and indexes
- Default user roles (Admin, Reviewer, User, Read-Only)
- Facility records (MMC, BURKE, AECOM, etc.)

### 5. Run Development Server

```bash
python run.py
```

Access the application at `http://localhost:5000`

## Database Schema

### Core Tables

**initiatives** - Master table for all initiatives
- id, initiative_type, description, wave_id
- status (Pending Review, Approved, Rejected)
- owner_id, created_by_id, reviewed_by_id
- Timestamps, soft delete flag

**cost_savings** - Cost savings specific data
- Initiative details, contract info, vendor
- Start/end dates, baseline/expected spend
- Annual and total savings amounts

**rebates** - Rebate specific data
- Rebate type, contract info, vendor
- Check date, payment type, check number
- Rebate amount

**cost_avoidance** - Cost avoidance specific data
- Avoidance type, Strata project ID
- Contract info, vendor, PO details
- Original quote, new quote, avoidance amount

### Normalized Tables

**facilities** - Reference table for facilities
**facility_allocations** - Percentage allocations per initiative

**users** - User accounts
**user_roles** - Role definitions with permissions

**file_tracking** - File attachments
**audit_logs** - Complete audit trail

## API Endpoints

### Authentication
- `GET /api/auth/current-user` - Get current user info
- `GET /api/auth/check` - Check authentication status

### Initiatives
- `GET /api/initiatives` - List all initiatives (with filtering, pagination)
- `GET /api/initiatives/<id>` - Get single initiative
- `DELETE /api/initiatives/<id>` - Soft delete initiative
- `POST /api/initiatives/<id>/approve` - Approve initiative
- `POST /api/initiatives/<id>/reject` - Reject initiative
- `GET /api/initiatives/<id>/audit-log` - Get audit history
- `GET /api/initiatives/statistics` - Get statistics

### Cost Savings
- `POST /api/cost-savings` - Create cost savings initiative
- `PUT /api/cost-savings/<id>` - Update cost savings initiative

### Rebates
- `POST /api/rebates` - Create rebate initiative
- `PUT /api/rebates/<id>` - Update rebate initiative

### Cost Avoidance
- `POST /api/cost-avoidance` - Create cost avoidance initiative
- `PUT /api/cost-avoidance/<id>` - Update cost avoidance initiative

## Key Improvements from v1

1. **Normalized Database**
   - Facility allocations in separate table
   - Proper foreign key relationships
   - Comprehensive indexes for performance

2. **Audit Trail**
   - All changes tracked in audit_logs table
   - Old and new values stored as JSON
   - User, timestamp, IP address recorded

3. **Better Authorization**
   - Role-based permissions
   - Fine-grained control (create, edit own, edit all, delete, review, approve)
   - IIS Windows Authentication integration

4. **Validation**
   - Duplicate detection for all initiative types
   - Facility allocation sum validation (must equal 100%)
   - Date range overlap detection for cost savings

5. **RESTful API**
   - Clean API design
   - Pagination support
   - Advanced filtering and searching
   - Consistent error handling

## IIS Deployment

1. **Install wfastcgi:**
```bash
pip install wfastcgi
wfastcgi-enable
```

2. **Configure IIS:**
   - Create new site pointing to application directory
   - Enable Windows Authentication
   - Disable Anonymous Authentication
   - Update `web.config` with correct Python paths

3. **Set permissions:**
   - Grant IIS_IUSRS read access to application folder
   - Grant write access to logs folder and file storage path

## User Management

Users are automatically created on first login via IIS authentication. To assign roles:

```sql
-- View users
SELECT * FROM users;

-- Assign role to user
UPDATE users 
SET role_id = (SELECT id FROM user_roles WHERE name = 'Reviewer')
WHERE username = 'username';
```

Or create an admin interface for role management.

## Troubleshooting

**Database connection issues:**
- Verify SQL Server is accessible
- Check ODBC driver is installed
- Validate connection string in .env

**IIS authentication not working:**
- Ensure Windows Authentication is enabled in IIS
- Check application pool identity has database access
- Verify REMOTE_USER header is being passed

**Email notifications not sending:**
- Validate `MS_GRAPH_TENANT_ID`, `MS_GRAPH_CLIENT_ID`, and `MS_GRAPH_CLIENT_SECRET`
- Confirm `procurementdatateam@montefiore.org` is the configured sender mailbox
- Review application logs or the Admin email testing page for details

## Development

**Run tests:**
```bash
pytest
```

**Create database migration:**
```bash
flask db migrate -m "Description of changes"
flask db upgrade
```

**Enable debug mode:**
Set `FLASK_ENV=development` in .env

## License

Internal use - Montefiore Medicine Procurement Department

## Contact

Procurement Data Team - procurementdatateam@montefiore.org
