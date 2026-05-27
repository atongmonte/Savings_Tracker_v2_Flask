# Savings Tracker v2 - Frontend Summary

## Current Frontend Stack
- Server-rendered pages with Flask + Jinja templates.
- Styling/layout with Bootstrap 5 and custom CSS.
- Icons with Font Awesome.
- Dashboard table is rendered as standard HTML and managed by custom JavaScript.

## Current Template Inventory
- `app/templates/base.html`
- `app/templates/dashboard.html`
- `app/templates/savings_dashboard.html`
- `app/templates/cost_savings_form.html`
- `app/templates/rebate_form.html`
- `app/templates/cost_avoidance_form.html`
- `app/templates/rebate_extraction.html`
- `app/templates/email_notifications.html`
- `app/templates/user_management.html`
- `app/templates/index.html`

## Current Route Coverage (`app/views.py`)
- `/` redirects to `/dashboard`
- `/dashboard`
- `/savings-dashboard`
- `/cost-savings/form`
- `/rebate/form`
- `/rebate/extraction`
- `/rebate/extraction/export`
- `/cost-avoidance/form`
- `/admin/email-notifications`
- `/admin/users`
- `/logout`

## JavaScript Files in Use
- `app/static/js/dashboard.js`
- `app/static/js/cost_savings_form.js`
- `app/static/js/rebate_form.js`
- `app/static/js/cost_avoidance_form.js`
- `app/static/js/contract_categories.js`
- `app/static/js/number-format.js`

## Dashboard Behavior Summary
- Fetches initiatives and statistics from API endpoints.
- Renders rows to `#initiativesTableBody` as HTML rows.
- Supports sorting, filtering, searching, pagination, and row actions.
- Uses modal workflows for view/edit/review actions.

## API Endpoints Used by Frontend
- `GET /api/auth/current-user`
- `GET /api/auth/check`
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
- `POST /api/cost-savings`
- `POST /api/cost-savings/{id}`
- `POST /api/rebates`
- `POST /api/rebates/{id}`
- `POST /api/cost-avoidance`
- `POST /api/cost-avoidance/{id}`
- `GET /api/analytics/summary`
- `GET /api/analytics/details`
- `GET /api/analytics/facilities`

## Notes
- Prior AG-Grid references were removed from this summary because the current implementation does not include AG-Grid imports or initialization.
- IIS Windows Authentication and role-based permissions are active in the current code path.
