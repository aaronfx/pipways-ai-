-- Pipways Trading Platform Database Schema

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trades table
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    user_email VARCHAR(255) REFERENCES users(email) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    entry_price DECIMAL(15, 5) NOT NULL,
    exit_price DECIMAL(15, 5),
    position VARCHAR(10) NOT NULL CHECK (position IN ('long', 'short')),
    size DECIMAL(15, 2) NOT NULL,
    pnl DECIMAL(15, 2),
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Blog posts table
CREATE TABLE IF NOT EXISTS blog_posts (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    author VARCHAR(255) REFERENCES users(email) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_trades_user_email ON trades(user_email);
CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_blog_posts_created_at ON blog_posts(created_at);

-- Insert default admin user (password: admin123)
-- Note: In production, change this password immediately!
INSERT INTO users (name, email, password_hash, role) 
VALUES (
    'Admin User', 
    'admin@pipways.com', 
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.VTtYA.qGZvKG6G', 
    'admin'
)
ON CONFLICT (email) DO NOTHING;

-- Insert sample blog posts
INSERT INTO blog_posts (title, content, author, created_at) VALUES
('Welcome to Pipways AI', 'Start your trading journey with our advanced AI-powered platform. Track your trades, analyze performance, and improve your strategy.', 'admin@pipways.com', NOW() - INTERVAL '7 days'),

('Understanding Risk Management', 'Risk management is crucial for long-term trading success. Never risk more than 2% of your account on a single trade. Always use stop losses.', 'admin@pipways.com', NOW() - INTERVAL '5 days'),

('Technical Analysis Basics', 'Learn the fundamentals of technical analysis including support/resistance levels, trend lines, and key chart patterns.', 'admin@pipways.com', NOW() - INTERVAL '3 days')

ON CONFLICT DO NOTHING;

-- Insert sample trades for admin
INSERT INTO trades (user_email, symbol, entry_price, exit_price, position, size, pnl, notes, created_at) VALUES
('admin@pipways.com', 'EURUSD', 1.0850, 1.0920, 'long', 1.0, 70.00, 'Breakout trade - good momentum', NOW() - INTERVAL '10 days'),
('admin@pipways.com', 'GBPUSD', 1.2650, 1.2600, 'short', 0.5, -25.00, 'Stopped out - trend reversed', NOW() - INTERVAL '8 days'),
('admin@pipways.com', 'USDJPY', 150.50, 151.20, 'long', 1.0, 46.50, 'Followed trend successfully', NOW() - INTERVAL '6 days'),
('admin@pipways.com', 'AUDUSD', 0.6550, 0.6520, 'short', 0.75, 22.50, 'Resistance held nicely', NOW() - INTERVAL '4 days'),
('admin@pipways.com', 'USDCAD', 1.3500, 1.3480, 'long', 1.0, -15.00, 'Small loss, good setup though', NOW() - INTERVAL '2 days')

ON CONFLICT DO NOTHING;
