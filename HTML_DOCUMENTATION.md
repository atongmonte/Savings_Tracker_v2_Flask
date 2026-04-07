# HTML Pages Created

## Overview
Modern, responsive web application interface built with Bootstrap 5, AG-Grid, and Font Awesome icons.

## Pages Created

### 1. Base Template (`base.html`)
- **Purpose**: Master template for all pages
- **Features**:
  - Responsive navigation bar with Montefiore branding
  - User welcome message
  - Dropdown menu for creating new initiatives
  - Flash message support
  - Logout functionality
  - Consistent footer
  - Modern dark blue (#112B46) color scheme

### 2. Dashboard (`dashboard.html`)
- **Purpose**: Main landing page showing all initiatives
- **Features**:
  - Statistics cards showing:
    - Total initiative count
    - Total cost savings
    - Total rebates
    - Total cost avoidance
  - Advanced filtering:
    - By initiative type (Cost Savings, Rebate, Cost Avoidance)
    - By status (Draft, Submitted, Approved, Rejected)
    - Search box for vendor, contract, description
  - AG-Grid data table with:
    - Sortable columns
    - Action buttons (View, Edit, Approve, Reject)
    - Status badges with color coding
    - Pagination
  - Approve/Reject modals for reviewers
  - Responsive design for mobile/tablet

### 3. Cost Savings Form (`cost_savings_form.html`)
- **Purpose**: Create/Edit Cost Savings initiatives
- **Sections**:
  - Contract Information (Category, Vendor, Dates, Description)
  - Savings Details (Baseline spend, New spend, Calculation)
  - Facility Allocation (8 facilities with percentage distribution)
  - File Attachments
- **Features**:
  - Auto-calculation of savings amount
  - Real-time facility allocation validation (must equal 100%)
  - File upload with preview
  - Save as Draft or Submit for Review
  - Form validation

### 4. Rebate Form (`rebate_form.html`)
- **Purpose**: Create/Edit Rebate initiatives
- **Sections**:
  - Rebate Information (Type, Vendor, Category)
  - Rebate Details (Check number, Amount, Period dates)
  - Facility Allocation
  - File Attachments
- **Features**:
  - Rebate type selection (Volume, Performance, GPO, etc.)
  - Payment method tracking
  - Period date validation
  - File upload for check copies

### 5. Cost Avoidance Form (`cost_avoidance_form.html`)
- **Purpose**: Create/Edit Cost Avoidance initiatives
- **Sections**:
  - Initiative Information (Category, Type, Vendor)
  - Avoidance Details (Projected vs Actual spend, Justification)
  - Facility Allocation
  - File Attachments
- **Features**:
  - Auto-calculation of avoidance amount
  - Time period selection (Monthly, Quarterly, Annual, One-Time)
  - Baseline/benchmark documentation
  - Justification requirement

## CSS Files

### `forms.css`
- Form section styling with left border accent
- Input group styling for currency fields
- File upload list styling
- Facility allocation styles
- Loading overlay with spinner
- Validation state styles (is-valid, is-invalid)
- Responsive adjustments for mobile

## JavaScript Files

### `dashboard.js`
- **Functions**:
  - `loadInitiatives()` - Fetch initiatives from API
  - `updateStatistics()` - Calculate and display totals
  - `applyFilters()` - Filter grid data
  - `viewInitiative()` - Show initiative details modal
  - `editInitiative()` - Navigate to edit form
  - `approveInitiative()` - Approve with confirmation
  - `rejectInitiative()` - Show rejection modal
  - `submitRejection()` - Submit rejection with comment
- AG-Grid configuration with custom cell renderers

### `cost_savings_form.js`
- **Functions**:
  - Auto-calculation of savings amount
  - Facility allocation tracking and validation
  - File upload with preview and removal
  - Form submission to API
  - Draft saving functionality
  - Multi-file upload handling
  - Form validation

### `rebate_form.js`
- Similar structure to cost_savings_form.js
- Handles rebate-specific fields
- Period date validation
- Check number and payment method tracking

### `cost_avoidance_form.js`
- Similar structure to cost_savings_form.js
- Auto-calculation of avoidance amount
- Time period handling
- Effective/end date validation

## Design Improvements Over Old Version

1. **Modern UI Framework**: Bootstrap 5 instead of Bootstrap 3
2. **Better Grid**: AG-Grid 30.0 with better performance
3. **Responsive Design**: Mobile-first approach
4. **Color Scheme**: Consistent Montefiore branding
5. **Icons**: Font Awesome 6 for modern icons
6. **Status Badges**: Visual status indicators
7. **Loading States**: Loading overlay during API calls
8. **File Management**: Better file upload UI with preview
9. **Validation**: Real-time form validation with visual feedback
10. **Modular JavaScript**: Separate JS files for each form
11. **Accessibility**: Better semantic HTML and ARIA labels
12. **Performance**: CDN resources, optimized loading

## Color Palette

- Primary Color: `#112B46` (Montefiore Dark Blue)
- Secondary Color: `#00A8E1` (Montefiore Light Blue)
- Success Color: `#28a745` (Green for savings)
- Danger Color: `#dc3545` (Red for rejected)
- Warning Color: `#ffc107` (Yellow for cost avoidance)
- Light Background: `#f8f9fa`

## API Integration

All forms are connected to the REST API:
- `GET /api/initiatives` - List initiatives
- `POST /api/cost-savings` - Create cost savings
- `POST /api/rebate` - Create rebate
- `POST /api/cost-avoidance` - Create cost avoidance
- `POST /api/initiatives/{id}/approve` - Approve initiative
- `POST /api/initiatives/{id}/reject` - Reject initiative
- `POST /api/initiatives/{id}/files` - Upload files

## Next Steps

1. **Replace Placeholder Logo**: Update `app/static/images/monte_logo.svg` with actual Montefiore logo
2. **Test Forms**: Test all three forms with API endpoints
3. **File Upload**: Implement server-side file upload handling
4. **User Authentication**: Integrate with IIS Windows Authentication
5. **Permissions**: Add role-based UI element showing/hiding
6. **Export Feature**: Add export to Excel functionality
7. **Audit Trail**: Add audit log viewing page
8. **Reports**: Create reporting/analytics dashboard
