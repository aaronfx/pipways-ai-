-- =============================================================================
-- Pipways v3.0 Database Migrations
-- Run this SQL file to upgrade from v2.0 to v3.0
-- =============================================================================

-- =============================================================================
-- USERS TABLE ENHANCEMENTS
-- =============================================================================

-- Add role column if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role') THEN
        ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'user';
        UPDATE users SET role = CASE WHEN is_admin = TRUE THEN 'admin' ELSE 'user' END;
    END IF;
END $$;

-- Add permissions column
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'permissions') THEN
        ALTER TABLE users ADD COLUMN permissions JSONB DEFAULT '{}';
    END IF;
END $$;

-- Add last_login_at column
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'last_login_at') THEN
        ALTER TABLE users ADD COLUMN last_login_at TIMESTAMP;
    END IF;
END $$;

-- Add login_attempts column
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'login_attempts') THEN
        ALTER TABLE users ADD COLUMN login_attempts INTEGER DEFAULT 0;
    END IF;
END $$;

-- Add locked_until column
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'locked_until') THEN
        ALTER TABLE users ADD COLUMN locked_until TIMESTAMP;
    END IF;
END $$;

-- Add password_changed_at column
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'password_changed_at') THEN
        ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP;
    END IF;
END $$;

-- Add password_history column
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'password_history') THEN
        ALTER TABLE users ADD COLUMN password_history JSONB DEFAULT '[]';
    END IF;
END $$;

-- =============================================================================
-- NEW TABLES FOR v3.0
-- =============================================================================

-- Token blacklist for logout
CREATE TABLE IF NOT EXISTS token_blacklist (
    jti VARCHAR(255) PRIMARY KEY,
    expires_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Password reset tokens
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    token VARCHAR(255) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL,
    used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Admin login logs
CREATE TABLE IF NOT EXISTS admin_login_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    ip_address VARCHAR(45),
    user_agent TEXT,
    success BOOLEAN,
    failure_reason VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Enhanced trades table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'screenshot_url') THEN
        ALTER TABLE trades ADD COLUMN screenshot_url TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'psychology_rating') THEN
        ALTER TABLE trades ADD COLUMN psychology_rating INTEGER;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'trades' AND column_name = 'setup_quality') THEN
        ALTER TABLE trades ADD COLUMN setup_quality VARCHAR(10);
    END IF;
END $$;

-- =============================================================================
-- COURSES TABLE ENHANCEMENTS
-- =============================================================================

-- Add new columns to courses
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'slug') THEN
        ALTER TABLE courses ADD COLUMN slug VARCHAR(255) UNIQUE;
        -- Generate slugs for existing courses
        UPDATE courses SET slug = LOWER(REGEXP_REPLACE(title, '[^a-zA-Z0-9]+', '-', 'g'));
        ALTER TABLE courses ALTER COLUMN slug SET NOT NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'short_description') THEN
        ALTER TABLE courses ADD COLUMN short_description TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'price') THEN
        ALTER TABLE courses ADD COLUMN price DECIMAL(10,2) DEFAULT 0;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'is_free') THEN
        ALTER TABLE courses ADD COLUMN is_free BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'instructor_name') THEN
        ALTER TABLE courses ADD COLUMN instructor_name VARCHAR(255);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'duration_minutes') THEN
        ALTER TABLE courses ADD COLUMN duration_minutes INTEGER DEFAULT 0;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'status') THEN
        ALTER TABLE courses ADD COLUMN status VARCHAR(20) DEFAULT 'draft';
        UPDATE courses SET status = 'published' WHERE id IS NOT NULL;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'enrolled_count') THEN
        ALTER TABLE courses ADD COLUMN enrolled_count INTEGER DEFAULT 0;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'rating') THEN
        ALTER TABLE courses ADD COLUMN rating DECIMAL(3,2) DEFAULT 0;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'rating_count') THEN
        ALTER TABLE courses ADD COLUMN rating_count INTEGER DEFAULT 0;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'courses' AND column_name = 'published_at') THEN
        ALTER TABLE courses ADD COLUMN published_at TIMESTAMP;
    END IF;
END $$;

-- =============================================================================
-- COURSE MODULES TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS course_modules (
    id SERIAL PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    order_index INTEGER DEFAULT 0,
    is_free_preview BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- COURSE LESSONS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS course_lessons (
    id SERIAL PRIMARY KEY,
    module_id INTEGER REFERENCES course_modules(id) ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    content TEXT,
    video_url TEXT,
    video_file_path TEXT,
    pdf_url TEXT,
    duration_minutes INTEGER DEFAULT 0,
    order_index INTEGER DEFAULT 0,
    is_free_preview BOOLEAN DEFAULT FALSE,
    is_published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- COURSE RESOURCES TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS course_resources (
    id SERIAL PRIMARY KEY,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    lesson_id INTEGER REFERENCES course_lessons(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(50),
    file_size INTEGER,
    download_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- COURSE ENROLLMENTS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS course_enrollments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    enrolled_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP,
    progress_percentage INTEGER DEFAULT 0,
    total_watch_time INTEGER DEFAULT 0,
    is_completed BOOLEAN DEFAULT FALSE,
    last_accessed_at TIMESTAMP,
    UNIQUE(user_id, course_id)
);

-- =============================================================================
-- LESSON PROGRESS TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS lesson_progress (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    lesson_id INTEGER REFERENCES course_lessons(id) ON DELETE CASCADE,
    course_id INTEGER REFERENCES courses(id) ON DELETE CASCADE,
    is_completed BOOLEAN DEFAULT FALSE,
    watch_time_seconds INTEGER DEFAULT 0,
    completed_at TIMESTAMP,
    last_position_seconds INTEGER DEFAULT 0,
    last_accessed_at TIMESTAMP,
    UNIQUE(user_id, lesson_id)
);

-- Migrate existing user_courses data
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'user_courses') THEN
        INSERT INTO course_enrollments (user_id, course_id, enrolled_at, completed_at, progress_percentage, is_completed)
        SELECT user_id, course_id, started_at, completed_at, progress_percentage, certificate_issued
        FROM user_courses
        ON CONFLICT (user_id, course_id) DO NOTHING;
        
        DROP TABLE user_courses;
    END IF;
END $$;

-- =============================================================================
-- WEBINARS TABLE ENHANCEMENTS
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'webinars' AND column_name = 'slug') THEN
        ALTER TABLE webinars ADD COLUMN slug VARCHAR(255) UNIQUE;
        UPDATE webinars SET slug = LOWER(REGEXP_REPLACE(title, '[^a-zA-Z0-9]+', '-', 'g')) || '-' || EXTRACT(EPOCH FROM created_at)::bigint;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'webinars' AND column_name = 'duration_minutes') THEN
        ALTER TABLE webinars ADD COLUMN duration_minutes INTEGER DEFAULT 60;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'webinars' AND column_name = 'is_live') THEN
        ALTER TABLE webinars ADD COLUMN is_live BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'webinars' AND column_name = 'max_attendees') THEN
        ALTER TABLE webinars ADD COLUMN max_attendees INTEGER;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'webinars' AND column_name = 'status') THEN
        ALTER TABLE webinars ADD COLUMN status VARCHAR(20) DEFAULT 'scheduled';
    END IF;
END $$;

-- Add attended_at to webinar_registrations
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'webinar_registrations' AND column_name = 'attended_at') THEN
        ALTER TABLE webinar_registrations ADD COLUMN attended_at TIMESTAMP;
    END IF;
END $$;

-- =============================================================================
-- BLOG POSTS TABLE ENHANCEMENTS
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'seo_meta_title') THEN
        ALTER TABLE blog_posts ADD COLUMN seo_meta_title VARCHAR(255);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'seo_meta_description') THEN
        ALTER TABLE blog_posts ADD COLUMN seo_meta_description TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'focus_keywords') THEN
        ALTER TABLE blog_posts ADD COLUMN focus_keywords TEXT[];
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'canonical_url') THEN
        ALTER TABLE blog_posts ADD COLUMN canonical_url TEXT;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'author_id') THEN
        ALTER TABLE blog_posts ADD COLUMN author_id INTEGER REFERENCES users(id);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'status') THEN
        ALTER TABLE blog_posts ADD COLUMN status VARCHAR(20) DEFAULT 'published';
        UPDATE blog_posts SET status = CASE WHEN published = TRUE THEN 'published' ELSE 'draft' END;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'scheduled_at') THEN
        ALTER TABLE blog_posts ADD COLUMN scheduled_at TIMESTAMP;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'published_at') THEN
        ALTER TABLE blog_posts ADD COLUMN published_at TIMESTAMP;
        UPDATE blog_posts SET published_at = created_at WHERE published = TRUE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'blog_posts' AND column_name = 'seo_score') THEN
        ALTER TABLE blog_posts ADD COLUMN seo_score INTEGER;
    END IF;
END $$;

-- =============================================================================
-- BLOG MEDIA TABLE
-- =============================================================================

CREATE TABLE IF NOT EXISTS blog_media (
    id SERIAL PRIMARY KEY,
    filename VARCHAR(255) NOT NULL,
    original_name VARCHAR(255),
    file_path TEXT NOT NULL,
    file_type VARCHAR(50),
    file_size INTEGER,
    alt_text VARCHAR(255),
    uploaded_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- PERFORMANCE ANALYSES ENHANCEMENTS
-- =============================================================================

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'performance_analyses' AND column_name = 'ai_insights') THEN
        ALTER TABLE performance_analyses ADD COLUMN ai_insights TEXT;
    END IF;
END $$;

-- =============================================================================
-- NEW TABLES FOR AI FEATURES
-- =============================================================================

-- Chart analysis history
CREATE TABLE IF NOT EXISTS chart_analyses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    image_path TEXT,
    analysis_result JSONB,
    pair VARCHAR(20),
    direction VARCHAR(10),
    setup_quality VARCHAR(5),
    confidence_score INTEGER,
    saved_to_journal BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- AI mentor chat history
CREATE TABLE IF NOT EXISTS mentor_chat_history (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    message TEXT NOT NULL,
    response TEXT,
    context JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- System settings
CREATE TABLE IF NOT EXISTS system_settings (
    key VARCHAR(255) PRIMARY KEY,
    value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- =============================================================================
-- INDEXES FOR PERFORMANCE
-- =============================================================================

CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_courses_status ON courses(status);
CREATE INDEX IF NOT EXISTS idx_courses_slug ON courses(slug);
CREATE INDEX IF NOT EXISTS idx_blog_posts_status ON blog_posts(status);
CREATE INDEX IF NOT EXISTS idx_blog_posts_slug ON blog_posts(slug);
CREATE INDEX IF NOT EXISTS idx_blog_posts_published_at ON blog_posts(published_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read);
CREATE INDEX IF NOT EXISTS idx_course_enrollments_user ON course_enrollments(user_id);
CREATE INDEX IF NOT EXISTS idx_lesson_progress_user ON lesson_progress(user_id, course_id);
CREATE INDEX IF NOT EXISTS idx_mentor_chat_user ON mentor_chat_history(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_chart_analyses_user ON chart_analyses(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_admin_login_logs_user ON admin_login_logs(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_expires ON password_reset_tokens(expires_at);
CREATE INDEX IF NOT EXISTS idx_token_blacklist_expires ON token_blacklist(expires_at);

-- =============================================================================
-- SAMPLE DATA (only if tables are empty)
-- =============================================================================

-- Insert sample courses if none exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM courses LIMIT 1) THEN
        INSERT INTO courses (title, slug, description, short_description, category, level, is_free, status, instructor_name, duration_minutes) VALUES
        ('Forex Fundamentals', 'forex-fundamentals', 
         'Learn the basics of forex trading including currency pairs, pips, leverage, and market structure.',
         'Master the basics of currency trading',
         'basics', 'beginner', TRUE, 'published', 'John Smith', 180),
        ('Technical Analysis Mastery', 'technical-analysis-mastery',
         'Master chart patterns, indicators, and price action strategies for consistent profits.',
         'Advanced technical analysis strategies',
         'technical', 'intermediate', FALSE, 'published', 'Sarah Johnson', 360),
        ('Risk Management Essentials', 'risk-management-essentials',
         'Protect your capital with proper position sizing, stop losses, and risk-reward ratios.',
         'Essential risk management techniques',
         'risk', 'beginner', TRUE, 'published', 'Mike Davis', 120);
    END IF;
END $$;

-- Insert sample blog posts if none exist
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM blog_posts LIMIT 1) THEN
        INSERT INTO blog_posts (title, slug, content, excerpt, category, status, seo_meta_title, seo_meta_description, tags, published_at) VALUES
        ('Getting Started with Forex Trading', 'getting-started-forex', 
         'Forex trading is the exchange of currencies on the foreign exchange market. It is the largest and most liquid financial market in the world...',
         'Learn the basics of forex trading and start your journey to becoming a successful trader.',
         'basics', 'published', 'Getting Started with Forex Trading | Pipways',
         'Learn forex trading basics with our comprehensive guide for beginners. Start your trading journey today.',
         ARRAY['forex', 'trading', 'beginners'], NOW()),
        ('Top 5 Risk Management Strategies', 'top-5-risk-management-strategies',
         'Risk management is crucial for trading success. Here are the top 5 strategies every trader should know...',
         'Essential risk management strategies to protect your trading capital.',
         'risk', 'published', 'Top 5 Risk Management Strategies | Pipways',
         'Discover the top 5 risk management strategies used by professional forex traders.',
         ARRAY['risk management', 'trading psychology', 'capital protection'], NOW());
    END IF;
END $$;

-- Create default admin user if not exists
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM users WHERE email = 'admin@pipways.com') THEN
        INSERT INTO users (name, email, password_hash, role, is_admin, subscription_status, trial_ends_at) 
        VALUES ('Admin', 'admin@pipways.com', '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewKyNiAYMyzJ/I1K', 'admin', TRUE, 'active', NOW() + INTERVAL '10 years');
    END IF;
END $$;

-- =============================================================================
-- MIGRATION COMPLETE
-- =============================================================================

SELECT 'Database migration to v3.0 completed successfully!' as status;
