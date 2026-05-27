# HTML and Frontend Documentation

## Overview
The frontend is server-rendered with Flask + Jinja templates, styled with Bootstrap 5 and Font Awesome. The main dashboard uses a responsive HTML table (not AG-Grid) with client-side filtering, sorting, and pagination logic in JavaScript.

## Templates in Use

### Core layout and dashboards
- `app/templates/base.html`: Shared shell, navigation, branding, flash messages, and page blocks.
- `app/templates/dashboard.html`: Main initiatives table, filter controls, summary cards, and edit/view modal.
- `app/templates/savings_dashboard.html`: Analytics-focused dashboard views.

### Initiative entry/edit pages
- `app/templates/cost_savings_form.html`
- `app/templates/rebate_form.html`
- `app/templates/cost_avoidance_form.html`

### Admin and support pages
- `app/templates/rebate_extraction.html`: Admin rebate extraction and export workflow.
- `app/templates/email_notifications.html`: Admin email notification testing/config page.
- `app/templates/user_management.html`: Admin user role/status management page.
- `app/templates/index.html`: Present in repository, while `/` currently redirects to `/dashboard`.

## Frontend Behavior

### Dashboard (`app/templates/dashboard.html` + `app/static/js/dashboard.js`)
- Loads initiatives from API and renders rows into `#initiativesTableBody`.
- Supports column sorting, filter fields, text search, and pagination.
- Opens detailed modal for view/edit actions.
- Supports reviewer/admin actions (approve/reject/unapprove/revert) based on permissions.
- Supports soft-delete/restore actions for eligible users.

### Forms
- `app/static/js/cost_savings_form.js`: Cost savings creation/edit, calculations, facility allocation validation, and submission.
- `app/static/js/rebate_form.js`: Rebate creation/edit, validations, and submission.
- `app/static/js/cost_avoidance_form.js`: Cost avoidance creation/edit, calculations, and submission.

### Shared scripts
- `app/static/js/contract_categories.js`: Contract category/source utility behavior.
- `app/static/js/number-format.js`: Number/currency formatting helpers.

### Shared styles
- `app/static/css/forms.css`: Common form section styling, validation presentation, and responsive behavior.

## API Endpoints Used by Frontend

### Auth
- `GET /api/auth/current-user`
- `GET /api/auth/check`

### Initiatives and workflow
- `GET /api/initiatives`
- `GET /api/initiatives/{id}`
- `DELETE /api/initiatives/{id}`
- `POST /api/initiatives/{id}/restore`
- `POST /api/initiatives/{id}/approve`
- `POST /api/initiatives/{id}/reject`
- `POST /api/initiatives/{id}/unapprove`
- `POST /api/initiatives/{id}/revert`
- `POST /api/initiatives/{id}/files`
- `GET /api/initiatives/{id}/files/{file_id}/download`
- `DELETE /api/initiatives/{id}/files/{file_id}`
- `GET /api/initiatives/{id}/audit-log`
- `GET /api/initiatives/dashboard-stats`
- `GET /api/initiatives/statistics`

### Initiative-type create/update
- `POST /api/cost-savings`
- `POST /api/cost-savings/{id}`
- `POST /api/rebates`
- `POST /api/rebates/{id}`
- `POST /api/cost-avoidance`
- `POST /api/cost-avoidance/{id}`

### Analytics
- `GET /api/analytics/summary`
- `GET /api/analytics/details`
- `GET /api/analytics/facilities`

## Authentication and Authorization Notes
- IIS Windows Authentication is used for sign-in identity.
- Route and action-level authorization is enforced by role permissions.
- Templates receive `template_current_user` via app context processor for role-aware navigation/actions.
