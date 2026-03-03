Pipways - Institutional Forex Trader Development Platform v3.0
An AI-powered trading journal, educational platform, and discipline coaching system for serious forex traders.
 Dashboard 

 Version 

 License 
🚀 Live Demo
Production URL: https://pipways-web.onrender.com
✨ Features
Core Platform
📊 Dashboard - Real-time trading metrics and performance stats
📷 Trade Journal - Log trades with pair, direction, pips, grade, screenshots
📈 Advanced Analytics - Equity curves, session performance, pair analysis
🛡️ Discipline Score - Track trading discipline with pre-trade checklists
🤖 AI Mentor - Chat interface with conversation history
💳 Subscription Management - Trial, Pro plans with Paystack integration
Admin CMS (New in v3.0)
📝 Blog Management - Full CMS with SEO tools, media library, WYSIWYG editor
🎓 Course Management - LMS with modules, lessons, video uploads, progress tracking
👥 User Management - Role-based access control (Admin/Student/User)
📧 Email Campaigns - Send notifications to users
📊 Platform Analytics - Revenue, enrollments, engagement metrics
AI-Powered Tools (Enhanced in v3.0)
🔍 Chart Analysis - AI vision analysis with technical indicators (MACD, RSI, MA)
📊 Performance Analysis - AI-generated insights from trade history
💬 AI Mentor - Context-aware trading psychology coaching
📈 Market Data - Real-time OHLC data with technical indicators
🛠️ Tech Stack
Table
Layer	Technology
Frontend	HTML5, Tailwind CSS, Vanilla JS, Chart.js
Backend	FastAPI (Python 3.11), Uvicorn
Database	PostgreSQL 15+ with asyncpg
Authentication	JWT with bcrypt, RBAC
AI/ML	OpenRouter API (Claude, GPT-4o)
Payments	Paystack
Email	SendGrid
File Storage	Local filesystem (configurable for S3)
Hosting	Render (Web Service + PostgreSQL)
📁 Project Structure
plain
Copy
pipways/
├── main.py                      # Main FastAPI application
├── config.py                    # Configuration management
├── requirements.txt             # Python dependencies
├── render.yaml                  # Render deployment config
├── README.md                    # This file
│
├── backend/
│   ├── auth_rbac.py            # Authentication & RBAC
│   ├── blog_courses.py         # Blog & Course management
│   ├── ai_integration.py       # AI services integration
│   ├── chart_analysis.py       # Technical analysis
│   └── trades_analytics.py     # Trading features
│
├── frontend/
│   ├── index.html              # Main SPA
│   ├── components.js           # Reusable UI components
│   ├── auth.js                 # Authentication flows
│   ├── admin_blog.js           # Blog management UI
│   ├── courses.js              # Course management UI
│   └── chart_analysis.js       # Chart analysis UI
│
├── database/
│   └── migrations.sql          # Database schema
│
├── uploads/                    # File uploads (gitignored)
│   ├── images/
│   ├── videos/
│   └── pdfs/
│
└── tests/
    └── test_integration.py     # Integration tests
🚀 Quick Start
Prerequisites
Python 3.11+
PostgreSQL 15+
Node.js (for local development, optional)
1. Clone and Setup
bash
Copy
git clone https://github.com/yourusername/pipways.git
cd pipways
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
2. Environment Variables
Create .env file:
bash
Copy
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/pipways

# Security
SECRET_KEY=your-super-secret-key-here-min-32-chars

# AI Services
OPENROUTER_API_KEY=sk-or-v1-...
ALPHA_VANTAGE_API_KEY=your-alpha-vantage-key

# Payments
PAYSTACK_SECRET_KEY=sk_test_...
PAYSTACK_PUBLIC_KEY=pk_test_...

# Email
SENDGRID_API_KEY=SG.xxx

# App Configuration
ENVIRONMENT=development
FRONTEND_URL=http://localhost:8000
DEBUG=true
3. Database Setup
bash
Copy
# Create database
createdb pipways

# Run migrations
psql $DATABASE_URL -f database/migrations.sql
4. Run Development Server
bash
Copy
uvicorn main:app --reload --host 0.0.0.0 --port 8000
Access the application at:
App: http://localhost:8000
API Docs: http://localhost:8000/docs
Admin: http://localhost:8000/admin-login
📚 API Documentation
Authentication Endpoints
Table
Method	Endpoint	Description
POST	/auth/register	User registration
POST	/auth/login	User login
POST	/auth/admin-login	Admin login (separate route)
POST	/auth/forgot-password	Password reset request
POST	/auth/reset-password	Reset password with token
POST	/auth/logout	Invalidate token
GET	/auth/me	Get current user info
GET	/auth/me/permissions	Get user permissions
Blog Endpoints (Admin)
Table
Method	Endpoint	Description
POST	/admin/blog/posts	Create blog post
PUT	/admin/blog/posts/{id}	Update blog post
DELETE	/admin/blog/posts/{id}	Delete blog post
GET	/admin/blog/posts	List all posts
POST	/admin/blog/upload-image	Upload image
GET	/admin/blog/media	List media files
Course Endpoints (Admin)
Table
Method	Endpoint	Description
POST	/admin/courses	Create course
PUT	/admin/courses/{id}	Update course
DELETE	/admin/courses/{id}	Delete course
POST	/admin/courses/{id}/modules	Create module
POST	/admin/courses/{id}/modules/{mid}/lessons	Create lesson
POST	/admin/courses/upload-video	Upload video
POST	/admin/courses/upload-pdf	Upload PDF
Course Endpoints (Student)
Table
Method	Endpoint	Description
GET	/courses	List all courses
GET	/courses/{id}	Get course details
POST	/courses/{id}/enroll	Enroll in course
GET	/courses/{id}/lessons/{lid}	Get lesson content
POST	/courses/{id}/lessons/{lid}/progress	Update progress
GET	/courses/enrolled	My enrolled courses
AI Endpoints
Table
Method	Endpoint	Description
POST	/analyze-chart	AI chart analysis
POST	/analyze-chart-indicators	Technical indicators
GET	/market-data/{pair}	OHLC market data
POST	/performance/analyze	Performance analysis
GET	/mentor-chat	AI mentor chat
GET	/mentor-chat/history	Chat history
🔐 Authentication & Roles
Role-Based Access Control (RBAC)
Admin Role:
Full platform access
Blog & Course management
User management
Analytics & reporting
Email campaigns
Student Role:
Access enrolled courses
Track progress
AI mentor chat
Trade journal
Analytics (own data only)
User Role:
Trade journal
Basic analytics
Blog access
Trial features
Permission System
Permissions are granular and checked at endpoint level:
Python
Copy
@require_permission("manage:courses")
@require_role(["admin"])
@require_subscription(["active", "trial"])
🤖 AI Integration
OpenRouter Configuration
The platform uses OpenRouter for AI features with fallback models:
anthropic/claude-3.5-sonnet (primary)
openai/gpt-4o (fallback 1)
google/gemini-pro-vision (fallback 2)
anthropic/claude-3-haiku (fallback 3)
openai/gpt-3.5-turbo (fallback 4)
Features
Chart Analysis: Vision-based technical analysis
Performance Analysis: Trade history insights
AI Mentor: Context-aware coaching
Indicator Calculation: MACD, RSI, Moving Averages
💳 Payment Integration
Paystack Setup
Create Paystack account
Get API keys from dashboard
Add to environment variables
Configure webhook URL: /subscription/verify
Subscription Plans
Table
Plan	Price	Features
Free Trial	$0	3 days, 5 trades, 1 chart analysis
Pro	$15/month	Unlimited trades, all courses, AI features
📧 Email Configuration
SendGrid Setup
Create SendGrid account
Create API key with Mail Send permissions
Add to environment variables
Configure sender authentication
Email Types
Welcome emails
Subscription confirmations
Password reset
Admin notifications
Marketing campaigns
🛡️ Security Features
Password Hashing: bcrypt with salt
JWT Tokens: HS256 with expiration
Rate Limiting: Per-endpoint configurable
Role-Based Access: Granular permissions
Input Validation: Pydantic models
SQL Injection Prevention: Parameterized queries
XSS Protection: Security headers
Account Lockout: 5 failed attempts = 30min lock
Password History: Prevents reuse of last 5 passwords
📊 Performance Optimizations
Database connection pooling (asyncpg)
In-memory caching with TTL
Response compression (gzip)
Pagination for list endpoints
Async file uploads
Lazy loading for media
Database indexes for common queries
🧪 Testing
bash
Copy
# Run integration tests
python -m pytest tests/

# Test AI integration
python tests/test_ai_integration.py

# Load testing
locust -f tests/locustfile.py
🚢 Deployment
Render Deployment
Connect GitHub repository to Render
Create PostgreSQL database
Set environment variables in Render dashboard
Deploy web service
The render.yaml blueprint automates this process.
Manual Deployment
bash
Copy
# Production build
pip install -r requirements.txt

# Run migrations
psql $DATABASE_URL -f database/migrations.sql

# Start server
uvicorn main:app --host 0.0.0.0 --port $PORT
📈 Monitoring
Health Check
bash
Copy
curl https://your-api.com/health
Response:
JSON
Copy
{
  "status": "healthy",
  "timestamp": "2026-03-03T12:00:00Z",
  "database": "connected",
  "version": "3.0.0"
}
Metrics
Active users
Trade volume
Course enrollments
Revenue
AI API usage
🤝 Contributing
Fork the repository
Create feature branch (git checkout -b feature/amazing-feature)
Commit changes (git commit -m 'Add amazing feature')
Push to branch (git push origin feature/amazing-feature)
Open Pull Request
📝 License
This project is licensed under the MIT License - see LICENSE file for details.
🆘 Support
For support, email support@pipways.com or join our Discord community.
🙏 Acknowledgments
FastAPI team for the amazing framework
Tailwind CSS for utility-first styling
Chart.js for beautiful charts
OpenRouter for AI model access
Render for hosting platform
Version: 3.0.0
Last Updated: March 3, 2026
Maintained by: Pipways Team
