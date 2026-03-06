Pipways AI - Trading Platform
Complete fixed version with working authentication and all features.
Quick Deploy to Render
Option 1: One-Click Deploy
Fork this repository
Go to Render Dashboard
Click "New +" → "Blueprint"
Connect your GitHub repo
Render will auto-deploy using render.yaml
Option 2: Manual Deploy
Push these files to GitHub:
main.py
index.html (in root)
requirements.txt
schema.sql
render.yaml
In Render Dashboard:
Create new Web Service
Connect your repo
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
Create PostgreSQL database in Render
Set environment variables:
DATABASE_URL: (from your Render database)
SECRET_KEY: (generate a random string)
Run schema.sql on your database to create tables
Default Login
Email: admin@pipways.com
Password: admin123
Change this password immediately after first login!
Features
Secure JWT authentication
User registration
Trading journal (add/view trades)
Dashboard with statistics
Blog system
File uploads
Responsive design
API Endpoints
Table
Endpoint	Method	Description
/health	GET	Health check
/api/auth/login	POST	Login
/api/auth/register	POST	Register
/api/trades	GET	Get all trades
/api/trades	POST	Create trade
/api/trades/stats	GET	Get statistics
/api/blog	GET	Get blog posts
/api/media/upload	POST	Upload file
Troubleshooting
Blank Page
Check browser console (F12) for errors
Ensure index.html is in the root directory
Hard refresh: Ctrl+Shift+R
Login Not Working
Check that database is connected
Verify schema.sql was run
Check Render logs for errors
API Errors
Test /health endpoint first
Check that DATABASE_URL is set correctly
Verify all environment variables
File Structure
plain
Copy
your-project/
├── main.py              # Backend (FastAPI)
├── index.html           # Frontend (place in ROOT)
├── requirements.txt     # Python dependencies
├── schema.sql           # Database schema
└── render.yaml          # Render config (optional)
Local Development
bash
Copy
# 1. Install dependencies
pip install -r requirements.txt

# 2. Setup database
# Create PostgreSQL database and set DATABASE_URL in .env

# 3. Run schema
psql $DATABASE_URL -f schema.sql

# 4. Start server
uvicorn main:app --reload

# 5. Open http://localhost:8000
Security Notes
Change default admin password immediately
Use strong SECRET_KEY in production
Enable HTTPS only in production
Regular database backups recommended
