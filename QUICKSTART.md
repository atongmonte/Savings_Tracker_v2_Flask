# 🚀 Quick Start Guide - Savings Tracker v2

## Run the Application

```bash
# Navigate to project directory
cd "C:\Users\atong\OneDrive - Montefiore Medicine\Savings_Tracker_v2_Flask"

# Run the Flask application
py run.py
```

The application will start on: **http://localhost:5000**

## Access the Pages

| Page | URL | Description |
|------|-----|-------------|
| Dashboard | http://localhost:5000/ | Main landing page with all initiatives |
| Dashboard | http://localhost:5000/dashboard | Same as above |
| Cost Savings | http://localhost:5000/cost-savings/form | Create cost savings initiative |
| Rebate | http://localhost:5000/rebate/form | Create rebate initiative |
| Cost Avoidance | http://localhost:5000/cost-avoidance/form | Create cost avoidance initiative |

## What You Can Do Now

### ✅ View Dashboard
- See all initiatives in a grid
- Filter by type and status
- Search by vendor, contract, description
- View statistics cards

### ✅ Create Initiatives
- Fill out the forms
- Add facility allocations (must total 100%)
- Upload supporting documents
- Save as draft or submit for review

### ✅ Manage Initiatives
- View initiative details
- Edit existing initiatives
- Approve or reject (if you're a reviewer)
- Add comments when rejecting

## Testing the Forms

### Cost Savings Form
1. Go to http://localhost:5000/cost-savings/form
2. Fill in required fields (marked with *)
3. Enter baseline spend and new contract spend
4. Watch savings amount calculate automatically
5. Allocate to facilities (must total 100%)
6. Click "Submit for Review"

### Rebate Form
1. Go to http://localhost:5000/rebate/form
2. Select rebate type
3. Enter vendor and check information
4. Enter rebate amount and period dates
5. Allocate to facilities
6. Click "Submit for Review"

### Cost Avoidance Form
1. Go to http://localhost:5000/cost-avoidance/form
2. Select avoidance type
3. Enter projected and actual spend
4. Watch avoidance amount calculate automatically
5. Provide justification
6. Allocate to facilities
7. Click "Submit for Review"

## Common Issues & Solutions

### ❌ "Database connection error"
**Solution:** Make sure the database initialization was successful:
```bash
py init_db.py
```

### ❌ "Template not found"
**Solution:** Check that all template files exist in `app/templates/`

### ❌ "Static files not loading"
**Solution:** Verify static files are in `app/static/css/` and `app/static/js/`

### ❌ "API endpoint returns 404"
**Solution:** Ensure all API blueprints are registered in `app/__init__.py`

### ❌ Logo not showing
**Solution:** The placeholder logo is SVG. Replace with actual Montefiore logo at:
```
app/static/images/monte_logo.svg
```

## File Structure Overview

```
app/
├── templates/           # HTML files
│   ├── base.html           # Master template
│   ├── dashboard.html      # Main grid view
│   ├── cost_savings_form.html
│   ├── rebate_form.html
│   └── cost_avoidance_form.html
│
├── static/             # CSS, JS, Images
│   ├── css/
│   │   └── forms.css       # Form styles
│   ├── js/
│   │   ├── dashboard.js
│   │   ├── cost_savings_form.js
│   │   ├── rebate_form.js
│   │   └── cost_avoidance_form.js
│   └── images/
│       └── monte_logo.svg
│
├── api/                # API endpoints
├── models/             # Database models
└── views.py            # HTML page routes
```

## Next Steps

1. **Replace the logo:**
   - Copy actual Montefiore logo to `app/static/images/`
   - Update filename in `base.html` if needed

2. **Test the API:**
   - Create some test initiatives
   - Try filtering and searching
   - Test approve/reject workflows

3. **Customize colors:**
   - Edit CSS variables in `base.html`
   - Update `forms.css` if needed

4. **Add real authentication:**
   - Currently shows "User" as username
   - Update `views.py` to get actual Windows user from IIS
   - Update `app/api/auth.py` to use IIS authentication

5. **Deploy to IIS:**
   - Follow instructions in `README.md`
   - Configure `web.config`
   - Set up FastCGI

## Tips

💡 **Facility Allocation:** Always make sure the percentages add up to exactly 100%

💡 **Required Fields:** Fields marked with a red asterisk (*) must be filled

💡 **Draft vs Submit:** Use "Save as Draft" to save work in progress, "Submit for Review" when ready

💡 **File Uploads:** Supported formats: PDF, Word, Excel, PowerPoint, Images, ZIP

💡 **Browser DevTools:** Press F12 to see console logs and network requests for debugging

## Support

If you encounter issues:
1. Check the browser console (F12) for JavaScript errors
2. Check the terminal where Flask is running for Python errors
3. Review the API responses in the Network tab
4. Verify database tables exist: `py -c "from app import db; print(db.engine.table_names())"`

---

**Enjoy your new Savings Tracker application!** 🎉
