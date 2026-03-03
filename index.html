<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="theme-color" content="#0f172a">
    <title>Pipways - Forex Trading Journal</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * { font-family: 'Inter', sans-serif; }
        body { background: #0f172a; color: #e2e8f0; }
        .glass { background: rgba(30, 41, 59, 0.7); backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.08); }
        .glass-strong { background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(20px); border: 1px solid rgba(255,255,255,0.1); }
        .gradient-text { background: linear-gradient(135deg, #3b82f6, #8b5cf6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .btn-primary { background: linear-gradient(135deg, #3b82f6, #6366f1); transition: all 0.2s ease; }
        .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 20px rgba(59, 130, 246, 0.4); }
        .loading-spinner { animation: spin 1s linear infinite; }
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        .animate-fade-in { animation: fadeIn 0.3s ease-out; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .sidebar-item.active { background: rgba(59, 130, 246, 0.2); border-right: 3px solid #3b82f6; }
        .skeleton { background: linear-gradient(90deg, #1e293b 25%, #334155 50%, #1e293b 75%); background-size: 200% 100%; animation: skeleton-loading 1.5s infinite; }
        @keyframes skeleton-loading { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
        .live-pulse { animation: pulse-red 2s infinite; }
        @keyframes pulse-red { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .notification-badge { position: absolute; top: -5px; right: -5px; background: #ef4444; color: white; font-size: 10px; padding: 2px 5px; border-radius: 10px; }
        .admin-badge { background: linear-gradient(135deg, #f59e0b, #ef4444); color: white; font-size: 10px; padding: 2px 6px; border-radius: 4px; margin-left: 8px; }
        .line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
        .line-clamp-3 { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
        @media (max-width: 1024px) { .hide-mobile { display: none !important; } }
        @media (min-width: 1025px) { .hide-desktop { display: none !important; } }
    </style>
<base target="_blank">
</head>
<body class="min-h-screen">
    <div id="toast-container" class="fixed top-4 right-4 z-50 space-y-2"></div>

    <!-- Auth Screen -->
    <div id="auth-screen" class="min-h-screen flex items-center justify-center p-4">
        <div class="w-full max-w-md glass rounded-2xl p-8">
            <div class="text-center mb-8">
                <div class="w-16 h-16 mx-auto mb-4 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
                    <i data-lucide="trending-up" class="w-8 h-8 text-white"></i>
                </div>
                <h1 class="text-3xl font-bold gradient-text mb-2">Pipways</h1>
                <p class="text-slate-400">Master Your Trading Journey</p>
            </div>
            <div class="flex mb-6 bg-slate-800/50 rounded-lg p-1">
                <button id="login-tab" class="flex-1 py-2 px-4 rounded-md text-sm font-medium bg-blue-600 text-white" onclick="switchAuthTab('login')">Login</button>
                <button id="register-tab" class="flex-1 py-2 px-4 rounded-md text-sm font-medium text-slate-400" onclick="switchAuthTab('register')">Register</button>
            </div>
            <form id="login-form" class="space-y-4" onsubmit="handleLogin(event)">
                <div>
                    <label class="block text-sm text-slate-400 mb-1">Email</label>
                    <input type="email" id="login-email" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" placeholder="your@email.com" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-400 mb-1">Password</label>
                    <input type="password" id="login-password" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" placeholder="••••••••" required>
                </div>
                <button type="submit" id="login-btn" class="w-full btn-primary py-3 rounded-lg font-medium">Sign In</button>
            </form>
            <form id="register-form" class="space-y-4 hidden" onsubmit="handleRegister(event)">
                <div>
                    <label class="block text-sm text-slate-400 mb-1">Full Name</label>
                    <input type="text" id="register-name" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" placeholder="John Doe" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-400 mb-1">Email</label>
                    <input type="email" id="register-email" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" placeholder="your@email.com" required>
                </div>
                <div>
                    <label class="block text-sm text-slate-400 mb-1">Password</label>
                    <input type="password" id="register-password" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" placeholder="••••••••" required minlength="8">
                </div>
                <button type="submit" id="register-btn" class="w-full btn-primary py-3 rounded-lg font-medium">Create Account</button>
            </form>
            <div class="mt-6 p-4 bg-slate-800/30 rounded-lg">
                <p class="text-xs text-slate-500 mb-2">Demo Credentials</p>
                <p class="text-xs text-slate-400">Email: admin@pipways.com</p>
                <p class="text-xs text-slate-400">Password: admin123</p>
            </div>
        </div>
    </div>

    <!-- Main App -->
    <div id="main-app" class="hidden">
        <!-- Desktop Sidebar -->
        <aside class="hide-mobile w-64 glass-strong h-screen fixed left-0 top-0 z-40 flex flex-col">
            <div class="p-6 border-b border-white/5">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
                        <i data-lucide="trending-up" class="w-5 h-5 text-white"></i>
                    </div>
                    <span class="text-xl font-bold gradient-text">Pipways</span>
                </div>
            </div>
            <nav class="p-4 space-y-1 flex-1 overflow-y-auto" id="sidebar-nav">
                <button onclick="navigateTo('dashboard')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="layout-dashboard" class="w-5 h-5"></i><span>Dashboard</span></button>
                <button onclick="navigateTo('journal')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="book-open" class="w-5 h-5"></i><span>Trade Journal</span></button>
                <button onclick="navigateTo('analytics')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="bar-chart-3" class="w-5 h-5"></i><span>Analytics</span></button>
                <button onclick="navigateTo('performance')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="target" class="w-5 h-5"></i><span>AI Performance</span></button>
                <button onclick="navigateTo('chart-analysis')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="scan-eye" class="w-5 h-5"></i><span>Chart Analysis</span></button>
                <button onclick="navigateTo('discipline')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="shield-check" class="w-5 h-5"></i><span>Discipline</span></button>
                <button onclick="navigateTo('mentor')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="message-circle" class="w-5 h-5"></i><span>AI Mentor</span></button>
                <button onclick="navigateTo('courses')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="graduation-cap" class="w-5 h-5"></i><span>Courses</span></button>
                <button onclick="navigateTo('webinars')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="video" class="w-5 h-5"></i><span>Webinars</span></button>
                <button onclick="navigateTo('subscription')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all"><i data-lucide="crown" class="w-5 h-5"></i><span>Subscription</span></button>
                <button onclick="navigateTo('notifications')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all relative">
                    <i data-lucide="bell" class="w-5 h-5"></i><span>Notifications</span>
                    <span id="sidebar-notification-badge" class="notification-badge hidden">0</span>
                </button>
                <button onclick="navigateTo('blog')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all">
                    <i data-lucide="newspaper" class="w-5 h-5"></i><span>Blog</span>
                </button>
                <button id="admin-menu-item" onclick="navigateTo('admin')" class="sidebar-item w-full flex items-center gap-3 px-4 py-3 rounded-xl text-white/70 hover:text-white hover:bg-white/5 transition-all hidden">
                    <i data-lucide="shield" class="w-5 h-5"></i><span>Admin</span><span class="admin-badge">ADMIN</span>
                </button>
            </nav>
            <div class="p-4 border-t border-white/5">
                <button onclick="logout()" class="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-red-400 hover:bg-red-500/10 transition-all"><i data-lucide="log-out" class="w-5 h-5"></i><span>Sign Out</span></button>
            </div>
        </aside>

        <!-- Main Content -->
        <main class="lg:ml-64 min-h-screen pb-20 lg:pb-0">
            <div id="page-content" class="p-4 lg:p-8"></div>
        </main>

        <!-- Mobile Bottom Navigation -->
        <nav class="hide-desktop fixed bottom-0 left-0 right-0 glass z-50 border-t border-white/5">
            <div class="flex justify-around py-2">
                <button onclick="navigateTo('dashboard')" class="flex flex-col items-center gap-1 p-2 text-slate-400"><i data-lucide="home" class="w-5 h-5"></i><span class="text-xs">Home</span></button>
                <button onclick="navigateTo('analytics')" class="flex flex-col items-center gap-1 p-2 text-slate-400"><i data-lucide="bar-chart-2" class="w-5 h-5"></i><span class="text-xs">Stats</span></button>
                <button onclick="navigateTo('journal')" class="flex flex-col items-center gap-1 p-2 text-slate-400"><div class="w-10 h-10 -mt-4 bg-gradient-to-br from-blue-500 to-violet-600 rounded-full flex items-center justify-center"><i data-lucide="plus" class="w-5 h-5 text-white"></i></div></button>
                <button onclick="navigateTo('notifications')" class="flex flex-col items-center gap-1 p-2 text-slate-400 relative">
                    <i data-lucide="bell" class="w-5 h-5"></i>
                    <span id="mobile-notification-badge" class="notification-badge hidden" style="top: 2px; right: 2px;">0</span>
                    <span class="text-xs">Alerts</span>
                </button>
                <button onclick="showMoreMenu()" class="flex flex-col items-center gap-1 p-2 text-slate-400"><i data-lucide="more-horizontal" class="w-5 h-5"></i><span class="text-xs">More</span></button>
            </div>
        </nav>
    </div>

    <!-- Mobile More Menu -->
    <div id="more-menu" class="hidden fixed inset-0 z-50">
        <div class="absolute inset-0 bg-black/60" onclick="hideMoreMenu()"></div>
        <div class="absolute bottom-20 left-4 right-4 glass rounded-2xl p-4">
            <div class="grid grid-cols-3 gap-4">
                <button onclick="hideMoreMenu(); navigateTo('chart-analysis')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="scan-eye" class="w-6 h-6 text-blue-400"></i><span class="text-xs">Analyze</span></button>
                <button onclick="hideMoreMenu(); navigateTo('discipline')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="shield-check" class="w-6 h-6 text-green-400"></i><span class="text-xs">Discipline</span></button>
                <button onclick="hideMoreMenu(); navigateTo('mentor')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="message-circle" class="w-6 h-6 text-violet-400"></i><span class="text-xs">Mentor</span></button>
                <button onclick="hideMoreMenu(); navigateTo('courses')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="graduation-cap" class="w-6 h-6 text-yellow-400"></i><span class="text-xs">Courses</span></button>
                <button onclick="hideMoreMenu(); navigateTo('webinars')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="video" class="w-6 h-6 text-red-400"></i><span class="text-xs">Webinars</span></button>
                <button onclick="hideMoreMenu(); navigateTo('subscription')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="crown" class="w-6 h-6 text-amber-400"></i><span class="text-xs">Pro</span></button>
                <button onclick="hideMoreMenu(); navigateTo('blog')" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5"><i data-lucide="newspaper" class="w-6 h-6 text-cyan-400"></i><span class="text-xs">Blog</span></button>
                <button onclick="hideMoreMenu(); logout()" class="flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5 text-red-400"><i data-lucide="log-out" class="w-6 h-6 text-red-400"></i><span class="text-xs">Logout</span></button>
            </div>
        </div>
    </div>

    <script>
        // Auto-detect API URL - works for both local and deployed environments
        const API_URL = (() => {
            const hostname = window.location.hostname;
            if (hostname === 'localhost' || hostname === '127.0.0.1') {
                return 'http://localhost:8000';
            }
            // For Render deployments, try to infer the API URL from frontend URL
            if (hostname.includes('render.com')) {
                // Replace web with api in the URL
                const apiHostname = hostname.replace('web', 'api');
                return `https://${apiHostname}`;
            }
            // Fallback to hardcoded API URL
            return 'https://pipways-api.onrender.com';
        })();
        
        console.log('API URL:', API_URL);
        console.log('Hostname:', window.location.hostname);
        
        let authToken = localStorage.getItem('pipways_token');
        let currentUser = null;
        let currentPage = 'dashboard';
        let notificationInterval = null;

        function showToast(message, type = 'info') {
            const container = document.getElementById('toast-container');
            const toast = document.createElement('div');
            const colors = { success: 'bg-green-500', error: 'bg-red-500', info: 'bg-blue-500', warning: 'bg-yellow-500' };
            toast.className = `${colors[type]} text-white px-4 py-3 rounded-lg shadow-lg animate-fade-in`;
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => toast.remove(), 3000);
        }

        function formatDate(dateStr) {
            if (!dateStr) return 'N/A';
            return new Date(dateStr).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
        }

        function formatCurrency(amount) {
            return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount);
        }

        async function apiCall(endpoint, options = {}) {
            const url = `${API_URL}${endpoint}`;
            const config = {
                headers: { 'Authorization': `Bearer ${authToken}`, 'Content-Type': 'application/json', ...options.headers },
                ...options
            };
            try {
                const response = await fetch(url, config);
                if (response.status === 401) { 
                    logout(); 
                    throw new Error('Session expired. Please log in again.'); 
                }
                return response;
            } catch (error) {
                console.error('API Call Error:', error);
                if (error.name === 'TypeError' && error.message.includes('fetch')) {
                    throw new Error('Cannot connect to server. The backend may be down or the API URL is incorrect.');
                }
                if (error.message.includes('Failed to fetch')) {
                    throw new Error('Network error. Please check your internet connection.');
                }
                throw error;
            }
        }

        function switchAuthTab(tab) {
            document.getElementById('login-form').classList.toggle('hidden', tab !== 'login');
            document.getElementById('register-form').classList.toggle('hidden', tab !== 'register');
            document.getElementById('login-tab').className = `flex-1 py-2 px-4 rounded-md text-sm font-medium ${tab === 'login' ? 'bg-blue-600 text-white' : 'text-slate-400'}`;
            document.getElementById('register-tab').className = `flex-1 py-2 px-4 rounded-md text-sm font-medium ${tab === 'register' ? 'bg-blue-600 text-white' : 'text-slate-400'}`;
        }

        async function handleLogin(e) {
            e.preventDefault();
            const btn = document.getElementById('login-btn');
            btn.innerHTML = '<div class="loading-spinner w-5 h-5 border-2 border-white border-t-transparent rounded-full"></div>';
            btn.disabled = true;

            try {
                const formData = new URLSearchParams();
                formData.append('email', document.getElementById('login-email').value);
                formData.append('password', document.getElementById('login-password').value);

                const response = await fetch(`${API_URL}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });

                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || `Login failed (${response.status})`);

                authToken = data.access_token;
                currentUser = data;
                localStorage.setItem('pipways_token', authToken);
                showApp();
                showToast('Welcome back!', 'success');
            } catch (error) {
                console.error('Login error:', error);
                if (error.name === 'TypeError' && error.message.includes('fetch')) {
                    showToast('Cannot connect to server. Please check your internet connection.', 'error');
                } else if (error.message.includes('Failed to fetch')) {
                    showToast('Server unreachable. Please try again later.', 'error');
                } else {
                    showToast(error.message, 'error');
                }
            } finally {
                btn.innerHTML = '<span>Sign In</span>';
                btn.disabled = false;
            }
        }

        async function handleRegister(e) {
            e.preventDefault();
            const btn = document.getElementById('register-btn');
            btn.innerHTML = '<div class="loading-spinner w-5 h-5 border-2 border-white border-t-transparent rounded-full"></div>';
            btn.disabled = true;

            try {
                const formData = new URLSearchParams();
                formData.append('name', document.getElementById('register-name').value);
                formData.append('email', document.getElementById('register-email').value);
                formData.append('password', document.getElementById('register-password').value);

                const response = await fetch(`${API_URL}/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: formData
                });

                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || `Registration failed (${response.status})`);

                authToken = data.access_token;
                currentUser = data;
                localStorage.setItem('pipways_token', authToken);
                showApp();
                showToast('Welcome! Your trial has started.', 'success');
            } catch (error) {
                console.error('Register error:', error);
                if (error.name === 'TypeError' && error.message.includes('fetch')) {
                    showToast('Cannot connect to server. Please check your internet connection.', 'error');
                } else if (error.message.includes('Failed to fetch')) {
                    showToast('Server unreachable. Please try again later.', 'error');
                } else {
                    showToast(error.message, 'error');
                }
            } finally {
                btn.innerHTML = '<span>Create Account</span>';
                btn.disabled = false;
            }
        }

        function logout() {
            authToken = null;
            currentUser = null;
            localStorage.removeItem('pipways_token');
            if (notificationInterval) clearInterval(notificationInterval);
            document.getElementById('auth-screen').classList.remove('hidden');
            document.getElementById('main-app').classList.add('hidden');
        }

        async function showApp() {
            document.getElementById('auth-screen').classList.add('hidden');
            document.getElementById('main-app').classList.remove('hidden');
            
            // Fetch current user info
            try {
                const response = await apiCall('/users/me');
                currentUser = await response.json();
                console.log('Current user:', currentUser);
                
                // Show admin menu if user is admin (handle both boolean and string)
                const isAdmin = currentUser.is_admin === true || currentUser.is_admin === 'true' || currentUser.is_admin === 1;
                if (isAdmin) {
                    console.log('User is admin, showing admin menu');
                    document.getElementById('admin-menu-item').classList.remove('hidden');
                    // Also add admin to mobile menu
                    addAdminToMobileMenu();
                } else {
                    console.log('User is not admin, is_admin value:', currentUser.is_admin, 'type:', typeof currentUser.is_admin);
                }
            } catch (error) {
                console.error('Failed to fetch user info:', error);
            }
            
            navigateTo('dashboard');
            startNotificationPolling();
        }
        
        function addAdminToMobileMenu() {
            const moreMenuGrid = document.querySelector('#more-menu .grid');
            if (moreMenuGrid && !document.getElementById('mobile-admin-btn')) {
                const adminBtn = document.createElement('button');
                adminBtn.id = 'mobile-admin-btn';
                adminBtn.onclick = () => { hideMoreMenu(); navigateTo('admin'); };
                adminBtn.className = 'flex flex-col items-center gap-2 p-3 rounded-lg hover:bg-white/5';
                adminBtn.innerHTML = '<i data-lucide="shield" class="w-6 h-6 text-orange-400"></i><span class="text-xs">Admin</span>';
                moreMenuGrid.appendChild(adminBtn);
            }
        }
        
        // Debug function to check admin status
        async function checkAdminStatus() {
            try {
                const response = await apiCall('/users/me');
                const user = await response.json();
                console.log('Admin check - User data:', user);
                console.log('is_admin value:', user.is_admin);
                console.log('is_admin type:', typeof user.is_admin);
                const isAdmin = user.is_admin === true || user.is_admin === 'true' || user.is_admin === 1;
                alert(`Admin status: ${user.is_admin}\nIs Admin (evaluated): ${isAdmin}\nEmail: ${user.email}\n\nIf not admin, run: fetch('/setup/make-admin-default',{method:'POST'}).then(r=>r.json()).then(console.log)`);
            } catch (error) {
                console.error('Admin check failed:', error);
                alert('Failed to check admin status');
            }
        }
        
        // Force show admin menu (for debugging)
        function showAdminMenu() {
            document.getElementById('admin-menu-item').classList.remove('hidden');
            addAdminToMobileMenu();
            lucide.createIcons();
            console.log('Admin menu force-shown');
        }

        function startNotificationPolling() {
            fetchNotifications();
            notificationInterval = setInterval(fetchNotifications, 30000);
        }

        async function fetchNotifications() {
            try {
                const response = await apiCall('/notifications');
                const notifications = await response.json();
                const unreadCount = notifications.filter(n => !n.is_read).length;
                updateNotificationBadge(unreadCount);
            } catch (error) {
                console.error('Failed to fetch notifications:', error);
            }
        }

        function updateNotificationBadge(count) {
            const sidebarBadge = document.getElementById('sidebar-notification-badge');
            const mobileBadge = document.getElementById('mobile-notification-badge');
            
            if (count > 0) {
                sidebarBadge.textContent = count > 99 ? '99+' : count;
                sidebarBadge.classList.remove('hidden');
                mobileBadge.textContent = count > 99 ? '99+' : count;
                mobileBadge.classList.remove('hidden');
            } else {
                sidebarBadge.classList.add('hidden');
                mobileBadge.classList.add('hidden');
            }
        }

        function navigateTo(page) {
            currentPage = page;
            document.querySelectorAll('.sidebar-item').forEach(el => el.classList.remove('active'));
            document.querySelectorAll(`[onclick="navigateTo('${page}')"]`).forEach(el => el.classList.add('active'));

            const renderers = {
                'dashboard': renderDashboard,
                'journal': renderJournal,
                'analytics': renderAnalytics,
                'performance': renderPerformance,
                'chart-analysis': renderChartAnalysis,
                'discipline': renderDiscipline,
                'mentor': renderMentor,
                'courses': renderCourses,
                'webinars': renderWebinars,
                'subscription': renderSubscription,
                'notifications': renderNotifications,
                'blog': renderBlog,
                'admin': renderAdmin
            };

            if (renderers[page]) renderers[page]();
            lucide.createIcons();
        }

        function showMoreMenu() { document.getElementById('more-menu').classList.remove('hidden'); }
        function hideMoreMenu() { document.getElementById('more-menu').classList.add('hidden'); }

        async function renderDashboard() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';

            try {
                const response = await apiCall('/trades');
                const trades = await response.json();

                const totalPips = trades.reduce((sum, t) => sum + (t.pips || 0), 0);
                const wins = trades.filter(t => t.pips > 0).length;
                const winRate = trades.length ? Math.round((wins / trades.length) * 100) : 0;

                container.innerHTML = `
                    <div class="animate-fade-in">
                        <div class="flex justify-between items-center mb-6">
                            <div>
                                <h1 class="text-2xl font-bold">Dashboard</h1>
                                <p class="text-slate-400 text-sm">Welcome back, ${currentUser?.name || 'Trader'}</p>
                            </div>
                            <button onclick="navigateTo('journal')" class="btn-primary px-4 py-2 rounded-lg">+ New Trade</button>
                        </div>
                        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Total Trades</div>
                                <div class="text-2xl font-bold">${trades.length}</div>
                            </div>
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Win Rate</div>
                                <div class="text-2xl font-bold ${winRate >= 50 ? 'text-green-400' : 'text-red-400'}">${winRate}%</div>
                            </div>
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Total Pips</div>
                                <div class="text-2xl font-bold ${totalPips >= 0 ? 'text-green-400' : 'text-red-400'}">${totalPips > 0 ? '+' : ''}${totalPips}</div>
                            </div>
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Discipline</div>
                                <div class="text-2xl font-bold text-blue-400">87%</div>
                            </div>
                        </div>
                        <div class="glass rounded-xl p-6 mb-6">
                            <h2 class="text-lg font-semibold mb-4">Recent Trades</h2>
                            ${trades.slice(0, 5).map(t => `
                                <div class="flex justify-between items-center py-3 border-b border-white/5">
                                    <div class="flex items-center gap-4">
                                        <span class="text-slate-400 text-sm">${formatDate(t.created_at)}</span>
                                        <span class="font-semibold">${t.pair}</span>
                                        <span class="px-2 py-1 rounded text-xs ${t.direction === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">${t.direction}</span>
                                    </div>
                                    <span class="font-mono font-bold ${t.pips >= 0 ? 'text-green-400' : 'text-red-400'}">${t.pips > 0 ? '+' : ''}${t.pips}</span>
                                </div>
                            `).join('') || '<p class="text-slate-500 text-center py-8">No trades yet</p>'}
                        </div>
                        ${currentUser?.subscription_status === 'trial' ? `
                        <div class="glass rounded-xl p-4 border border-yellow-500/30 bg-yellow-500/10">
                            <div class="flex items-center justify-between">
                                <div class="flex items-center gap-3">
                                    <i data-lucide="clock" class="w-5 h-5 text-yellow-400"></i>
                                    <span class="text-yellow-200">Trial ends in ${Math.ceil((new Date(currentUser.trial_ends_at) - new Date()) / (1000 * 60 * 60 * 24))} days</span>
                                </div>
                                <button onclick="navigateTo('subscription')" class="text-yellow-400 hover:text-yellow-300 text-sm font-medium">Upgrade Now</button>
                            </div>
                        </div>
                        ` : ''}
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        async function renderJournal() {
            const container = document.getElementById('page-content');
            container.innerHTML = `
                <div class="animate-fade-in">
                    <h1 class="text-2xl font-bold mb-6">Trade Journal</h1>
                    <div class="glass rounded-xl p-6 mb-6">
                        <h2 class="text-lg font-semibold mb-4">Log New Trade</h2>
                        <form onsubmit="handleTradeSubmit(event)" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div>
                                <label class="block text-sm text-slate-400 mb-1">Currency Pair</label>
                                <input type="text" name="pair" placeholder="EURUSD" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700 uppercase" required>
                            </div>
                            <div>
                                <label class="block text-sm text-slate-400 mb-1">Direction</label>
                                <select name="direction" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700">
                                    <option value="LONG">Long</option>
                                    <option value="SHORT">Short</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-sm text-slate-400 mb-1">Pips</label>
                                <input type="number" name="pips" step="0.1" placeholder="+45.5" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" required>
                            </div>
                            <div>
                                <label class="block text-sm text-slate-400 mb-1">Grade</label>
                                <select name="grade" class="w-full px-4 py-3 rounded-lg bg-slate-800 border border-slate-700">
                                    <option value="A">A - Excellent</option>
                                    <option value="B">B - Good</option>
                                    <option value="C">C - Poor</option>
                                </select>
                            </div>
                            <div class="md:col-span-2">
                                <button type="submit" class="w-full btn-primary py-3 rounded-lg font-medium">Save Trade</button>
                            </div>
                        </form>
                    </div>
                    <div id="trades-list"></div>
                </div>
            `;
            loadTradesList();
        }

        async function loadTradesList() {
            const container = document.getElementById('trades-list');
            try {
                const response = await apiCall('/trades');
                const trades = await response.json();
                container.innerHTML = `
                    <div class="glass rounded-xl p-6">
                        <h2 class="text-lg font-semibold mb-4">Trade History</h2>
                        <div class="overflow-x-auto">
                            <table class="w-full">
                                <thead class="text-slate-400 text-sm">
                                    <tr>
                                        <th class="text-left py-2">Date</th>
                                        <th class="text-left">Pair</th>
                                        <th class="text-left">Direction</th>
                                        <th class="text-right">Pips</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${trades.map(t => `
                                        <tr class="border-t border-white/5">
                                            <td class="py-3">${formatDate(t.created_at)}</td>
                                            <td class="font-semibold">${t.pair}</td>
                                            <td>
                                                <span class="px-2 py-1 rounded text-xs ${t.direction === 'LONG' ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400'}">${t.direction}</span>
                                            </td>
                                            <td class="text-right font-mono ${t.pips >= 0 ? 'text-green-400' : 'text-red-400'}">${t.pips > 0 ? '+' : ''}${t.pips}</td>
                                        </tr>
                                    `).join('')}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `<div class="text-red-400">${error.message}</div>`;
            }
        }

        async function handleTradeSubmit(e) {
            e.preventDefault();
            const formData = new FormData(e.target);
            try {
                const response = await apiCall('/trades', { 
                    method: 'POST', 
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, 
                    body: new URLSearchParams(formData) 
                });
                if (!response.ok) throw new Error('Failed to save trade');
                showToast('Trade saved!', 'success');
                e.target.reset();
                loadTradesList();
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function renderAnalytics() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            try {
                const response = await apiCall('/analytics/dashboard');
                const data = await response.json();
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <h1 class="text-2xl font-bold mb-6">Analytics</h1>
                        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Total Trades</div>
                                <div class="text-2xl font-bold">${data.total_trades}</div>
                            </div>
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Win Rate</div>
                                <div class="text-2xl font-bold ${data.win_rate >= 50 ? 'text-green-400' : 'text-red-400'}">${data.win_rate}%</div>
                            </div>
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Total Pips</div>
                                <div class="text-2xl font-bold ${data.total_pips >= 0 ? 'text-green-400' : 'text-red-400'}">${data.total_pips > 0 ? '+' : ''}${data.total_pips}</div>
                            </div>
                            <div class="glass rounded-xl p-4">
                                <div class="text-slate-400 text-sm mb-1">Profit Factor</div>
                                <div class="text-2xl font-bold text-blue-400">${data.profit_factor}</div>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                            <div class="glass rounded-xl p-6">
                                <h2 class="text-lg font-semibold mb-4">Equity Curve</h2>
                                <canvas id="equityChart" height="200"></canvas>
                            </div>
                            <div class="glass rounded-xl p-6">
                                <h2 class="text-lg font-semibold mb-4">Monthly Performance</h2>
                                <canvas id="monthlyChart" height="200"></canvas>
                            </div>
                        </div>
                    </div>
                `;
                if (data.equity_curve && data.equity_curve.length > 0) {
                    new Chart(document.getElementById('equityChart'), {
                        type: 'line',
                        data: { 
                            labels: data.equity_curve.map(d => formatDate(d.date)), 
                            datasets: [{ 
                                label: 'Cumulative Pips', 
                                data: data.equity_curve.map(d => d.cumulative_pips), 
                                borderColor: '#3b82f6', 
                                backgroundColor: 'rgba(59, 130, 246, 0.1)', 
                                fill: true, 
                                tension: 0.4 
                            }] 
                        },
                        options: { 
                            responsive: true, 
                            plugins: { legend: { display: false } }, 
                            scales: { 
                                x: { display: false }, 
                                y: { grid: { color: 'rgba(255,255,255,0.05)' } } 
                            } 
                        }
                    });
                }
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        async function renderPerformance() {
            document.getElementById('page-content').innerHTML = `
                <div class="animate-fade-in">
                    <h1 class="text-2xl font-bold mb-6">AI Performance Analysis</h1>
                    <div class="glass rounded-xl p-6 mb-6">
                        <h2 class="text-lg font-semibold mb-4">Upload Trading History</h2>
                        <p class="text-slate-400 mb-4">Upload a CSV file or screenshot of your trading history for AI analysis</p>
                        <input type="file" id="file-input" class="hidden" accept=".csv,.png,.jpg" onchange="handleFileUpload(event)">
                        <button onclick="document.getElementById('file-input').click()" class="btn-primary px-6 py-2 rounded-lg">Select File</button>
                    </div>
                    <div id="analysis-result"></div>
                </div>
            `;
        }

        async function handleFileUpload(event) {
            const file = event.target.files[0];
            if (!file) return;
            const resultContainer = document.getElementById('analysis-result');
            resultContainer.innerHTML = '<div class="flex justify-center py-8"><div class="loading-spinner w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            try {
                const formData = new FormData();
                formData.append('file', file);
                const response = await apiCall('/performance/analyze', { method: 'POST', body: formData });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Analysis failed (${response.status})`);
                }
                
                const data = await response.json();
                console.log('Performance analysis response:', data);
                
                if (!data.analysis) {
                    throw new Error('No analysis data received from server');
                }
                
                const analysis = data.analysis;
                const score = analysis.performance_score || 0;
                const traderType = analysis.trader_type || 'Unknown';
                const strengths = analysis.strengths || [];
                const weaknesses = analysis.weaknesses || [];
                
                resultContainer.innerHTML = `
                    <div class="glass rounded-xl p-6">
                        <div class="flex items-center justify-between mb-6">
                            <div>
                                <h2 class="text-2xl font-bold mb-2">Performance Score</h2>
                                <div class="text-5xl font-bold ${score >= 70 ? 'text-green-400' : score >= 50 ? 'text-yellow-400' : 'text-red-400'}">${score}<span class="text-2xl text-slate-400">/100</span></div>
                            </div>
                            <div class="text-right">
                                <div class="text-slate-400 text-sm mb-1">Trader Type</div>
                                <div class="text-xl font-semibold">${traderType}</div>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <div class="bg-slate-800/30 rounded-lg p-4">
                                <h3 class="font-semibold mb-3 text-green-400 flex items-center gap-2">
                                    <i data-lucide="trending-up" class="w-5 h-5"></i> Strengths
                                </h3>
                                ${strengths.length > 0 ? `
                                    <ul class="space-y-2">
                                        ${strengths.map(s => `<li class="flex items-start gap-2 text-slate-300"><i data-lucide="check-circle" class="w-4 h-4 text-green-400 mt-0.5 flex-shrink-0"></i><span>${s}</span></li>`).join('')}
                                    </ul>
                                ` : '<p class="text-slate-500">No strengths identified yet.</p>'}
                            </div>
                            <div class="bg-slate-800/30 rounded-lg p-4">
                                <h3 class="font-semibold mb-3 text-red-400 flex items-center gap-2">
                                    <i data-lucide="trending-down" class="w-5 h-5"></i> Areas to Improve
                                </h3>
                                ${weaknesses.length > 0 ? `
                                    <ul class="space-y-2">
                                        ${weaknesses.map(w => `<li class="flex items-start gap-2 text-slate-300"><i data-lucide="alert-circle" class="w-4 h-4 text-red-400 mt-0.5 flex-shrink-0"></i><span>${w}</span></li>`).join('')}
                                    </ul>
                                ` : '<p class="text-slate-500">No areas to improve identified.</p>'}
                            </div>
                        </div>
                    </div>
                `;
                lucide.createIcons();
                showToast('Analysis complete!', 'success');
            } catch (error) {
                console.error('Performance analysis error:', error);
                resultContainer.innerHTML = `
                    <div class="glass rounded-xl p-6 border border-red-500/30 bg-red-500/10">
                        <div class="flex items-center gap-3 mb-2">
                            <i data-lucide="alert-circle" class="w-6 h-6 text-red-400"></i>
                            <h3 class="text-lg font-semibold text-red-400">Analysis Error</h3>
                        </div>
                        <p class="text-slate-300">${error.message}</p>
                        <p class="text-slate-500 text-sm mt-2">Please try again with a valid trading history file.</p>
                    </div>
                `;
                lucide.createIcons();
            }
        }

        async function renderChartAnalysis() {
            document.getElementById('page-content').innerHTML = `
                <div class="animate-fade-in">
                    <h1 class="text-2xl font-bold mb-6">Chart Analysis</h1>
                    <div class="glass rounded-xl p-6 mb-6">
                        <p class="text-slate-400 mb-4">Upload a chart image for AI-powered technical analysis</p>
                        <input type="file" id="chart-input" class="hidden" accept="image/*" onchange="handleChartUpload(event)">
                        <button onclick="document.getElementById('chart-input').click()" class="btn-primary px-6 py-2 rounded-lg">Upload Chart Image</button>
                    </div>
                    <div id="chart-analysis-result"></div>
                </div>
            `;
        }

        async function handleChartUpload(event) {
            const file = event.target.files[0];
            if (!file) return;
            const resultContainer = document.getElementById('chart-analysis-result');
            resultContainer.innerHTML = '<div class="flex justify-center py-8"><div class="loading-spinner w-8 h-8 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            try {
                const formData = new FormData();
                formData.append('file', file);
                const response = await apiCall('/analyze-chart', { method: 'POST', body: formData });
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Analysis failed (${response.status})`);
                }
                
                const data = await response.json();
                console.log('Chart analysis response:', data);
                
                // Check if analysis exists
                if (!data.analysis) {
                    throw new Error('No analysis data received from server');
                }
                
                const analysis = data.analysis;
                
                // Handle missing fields gracefully
                const setupQuality = analysis.setup_quality || 'N/A';
                const pair = analysis.pair || 'Unknown';
                const direction = analysis.direction || 'Unknown';
                const entryPrice = analysis.entry_price || 'N/A';
                const riskReward = analysis.risk_reward || 'N/A';
                const analysisText = analysis.analysis || 'No detailed analysis available.';
                
                resultContainer.innerHTML = `
                    <div class="glass rounded-xl p-6">
                        <div class="flex items-center justify-between mb-4">
                            <h2 class="text-xl font-bold">Setup Analysis</h2>
                            <span class="px-3 py-1 rounded-full text-sm font-semibold ${setupQuality === 'A' ? 'bg-green-500/20 text-green-400' : setupQuality === 'B' ? 'bg-blue-500/20 text-blue-400' : 'bg-yellow-500/20 text-yellow-400'}">Grade ${setupQuality}</span>
                        </div>
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                            <div class="bg-slate-800/50 rounded-lg p-3">
                                <div class="text-slate-400 text-sm">Pair</div>
                                <div class="font-semibold">${pair}</div>
                            </div>
                            <div class="bg-slate-800/50 rounded-lg p-3">
                                <div class="text-slate-400 text-sm">Direction</div>
                                <div class="font-semibold ${direction === 'LONG' ? 'text-green-400' : direction === 'SHORT' ? 'text-red-400' : ''}">${direction}</div>
                            </div>
                            <div class="bg-slate-800/50 rounded-lg p-3">
                                <div class="text-slate-400 text-sm">Entry</div>
                                <div class="font-mono">${entryPrice}</div>
                            </div>
                            <div class="bg-slate-800/50 rounded-lg p-3">
                                <div class="text-slate-400 text-sm">R:R</div>
                                <div class="font-mono text-blue-400">${riskReward}</div>
                            </div>
                        </div>
                        <div class="bg-slate-800/30 rounded-lg p-4">
                            <p class="text-slate-300 leading-relaxed">${analysisText.replace(/\n/g, '<br>')}</p>
                        </div>
                    </div>
                `;
                showToast('Chart analysis complete!', 'success');
            } catch (error) {
                console.error('Chart analysis error:', error);
                resultContainer.innerHTML = `
                    <div class="glass rounded-xl p-6 border border-red-500/30 bg-red-500/10">
                        <div class="flex items-center gap-3 mb-2">
                            <i data-lucide="alert-circle" class="w-6 h-6 text-red-400"></i>
                            <h3 class="text-lg font-semibold text-red-400">Analysis Error</h3>
                        </div>
                        <p class="text-slate-300">${error.message}</p>
                        <p class="text-slate-500 text-sm mt-2">Please try again with a clearer chart image.</p>
                    </div>
                `;
                lucide.createIcons();
            }
        }

        async function renderDiscipline() {
            document.getElementById('page-content').innerHTML = `
                <div class="animate-fade-in">
                    <h1 class="text-2xl font-bold mb-6">Trading Discipline</h1>
                    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
                        <div class="glass rounded-xl p-6 text-center">
                            <div class="text-5xl font-bold gradient-text mb-2">87</div>
                            <div class="text-slate-400">Discipline Score</div>
                        </div>
                        <div class="glass rounded-xl p-6 text-center">
                            <div class="text-5xl font-bold text-green-400 mb-2">12</div>
                            <div class="text-slate-400">Day Streak</div>
                        </div>
                        <div class="glass rounded-xl p-6 text-center">
                            <div class="text-5xl font-bold text-blue-400 mb-2">94%</div>
                            <div class="text-slate-400">Checklist Adherence</div>
                        </div>
                    </div>
                    <div class="glass rounded-xl p-6">
                        <h2 class="text-lg font-semibold mb-4">Pre-Trade Checklist</h2>
                        <div class="space-y-3">
                            ${['Clear entry strategy', 'Stop loss identified', 'Take profit target set', 'Position size calculated', 'No FOMO/emotion', 'News checked', 'A/B grade criteria met', 'HTF trend analyzed'].map(item => `
                                <label class="flex items-center gap-3 p-3 bg-slate-800/50 rounded-lg cursor-pointer">
                                    <input type="checkbox" class="w-5 h-5 rounded">
                                    <span>${item}</span>
                                </label>
                            `).join('')}
                        </div>
                    </div>
                </div>
            `;
        }

        async function renderMentor() {
            document.getElementById('page-content').innerHTML = `
                <div class="animate-fade-in">
                    <h1 class="text-2xl font-bold mb-6">AI Trading Mentor</h1>
                    <div class="glass rounded-xl p-6 mb-6">
                        <div class="flex items-start gap-4">
                            <div class="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
                                <i data-lucide="bot" class="w-5 h-5 text-white"></i>
                            </div>
                            <div class="bg-slate-800/50 rounded-lg p-4 max-w-[80%]">
                                <p>Hello! I'm your AI trading mentor. How can I help you today?</p>
                            </div>
                        </div>
                        <div id="chat-messages"></div>
                    </div>
                    <form onsubmit="sendMentorMessage(event)" class="flex gap-2">
                        <input type="text" id="mentor-input" class="flex-1 px-4 py-3 rounded-lg bg-slate-800 border border-slate-700" placeholder="Ask your question...">
                        <button type="submit" class="btn-primary px-6 py-3 rounded-lg">
                            <i data-lucide="send" class="w-5 h-5"></i>
                        </button>
                    </form>
                </div>
            `;
        }

        async function sendMentorMessage(e) {
            e.preventDefault();
            const input = document.getElementById('mentor-input');
            const message = input.value.trim();
            if (!message) return;
            const chatContainer = document.getElementById('chat-messages');
            chatContainer.innerHTML += `
                <div class="flex items-start gap-4 mb-4 justify-end">
                    <div class="bg-blue-600 rounded-lg p-4 max-w-[80%]">
                        <p>${message}</p>
                    </div>
                </div>
            `;
            input.value = '';
            try {
                const response = await apiCall(`/mentor-chat?message=${encodeURIComponent(message)}`);
                const data = await response.json();
                chatContainer.innerHTML += `
                    <div class="flex items-start gap-4 mb-4">
                        <div class="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center flex-shrink-0">
                            <i data-lucide="bot" class="w-5 h-5 text-white"></i>
                        </div>
                        <div class="bg-slate-800/50 rounded-lg p-4 max-w-[80%]">
                            <p>${data.response}</p>
                        </div>
                    </div>
                `;
            } catch (error) {
                chatContainer.innerHTML += `<div class="text-red-400">Failed to get response</div>`;
            }
            lucide.createIcons();
        }

        async function renderCourses() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            try {
                const response = await apiCall('/courses');
                const courses = await response.json();
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <h1 class="text-2xl font-bold mb-6">Trading Courses</h1>
                        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            ${courses.map(course => `
                                <div class="glass rounded-xl overflow-hidden">
                                    <div class="h-40 bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center">
                                        <i data-lucide="graduation-cap" class="w-16 h-16 text-white/50"></i>
                                    </div>
                                    <div class="p-6">
                                        <span class="px-2 py-1 rounded text-xs ${course.level === 'beginner' ? 'bg-green-500/20 text-green-400' : course.level === 'intermediate' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-red-500/20 text-red-400'}">${course.level}</span>
                                        <h3 class="text-lg font-semibold mt-2 mb-2">${course.title}</h3>
                                        <p class="text-slate-400 text-sm mb-4">${course.description || ''}</p>
                                        <button onclick="enrollCourse(${course.id})" class="w-full btn-primary py-2 rounded-lg text-sm">Start Learning</button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        async function enrollCourse(courseId) {
            try {
                const response = await apiCall(`/courses/${courseId}/enroll`, { method: 'POST' });
                if (response.ok) { 
                    showToast('Enrolled successfully!', 'success'); 
                    renderCourses(); 
                }
            } catch (error) { 
                showToast(error.message, 'error'); 
            }
        }

        async function renderWebinars() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            try {
                const response = await apiCall('/webinars');
                const webinars = await response.json();
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <h1 class="text-2xl font-bold mb-6">Live Webinars</h1>
                        <div class="space-y-4">
                            ${webinars.map(w => `
                                <div class="glass rounded-xl p-6">
                                    <div class="flex items-center justify-between">
                                        <div>
                                            <h3 class="text-xl font-semibold">${w.title}</h3>
                                            <p class="text-slate-400">${w.scheduled_at ? formatDate(w.scheduled_at) : ''}</p>
                                        </div>
                                        <button onclick="registerWebinar(${w.id})" class="btn-primary px-4 py-2 rounded-lg">Register</button>
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        async function registerWebinar(webinarId) {
            try {
                const response = await apiCall(`/webinars/${webinarId}/register`, { method: 'POST' });
                if (response.ok) { 
                    showToast('Registered for webinar!', 'success'); 
                    renderWebinars(); 
                }
            } catch (error) { 
                showToast(error.message, 'error'); 
            }
        }

        async function renderSubscription() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            
            try {
                const response = await apiCall('/subscription/status');
                const subData = await response.json();
                
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <h1 class="text-2xl font-bold mb-6">Subscription</h1>
                        
                        ${subData.status !== 'active' ? `
                        <div class="glass rounded-xl p-4 mb-6 border border-yellow-500/30 bg-yellow-500/10">
                            <div class="flex items-center gap-3">
                                <i data-lucide="info" class="w-5 h-5 text-yellow-400"></i>
                                <span class="text-yellow-200">Current Status: <strong>${subData.status}</strong></span>
                            </div>
                        </div>
                        ` : ''}
                        
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
                            <div class="glass rounded-xl p-6">
                                <div class="text-center mb-6">
                                    <h2 class="text-xl font-semibold mb-2">Free Trial</h2>
                                    <div class="text-4xl font-bold mb-2">$0</div>
                                    <p class="text-slate-400">3 days access</p>
                                </div>
                                <ul class="space-y-3 mb-6">
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>5 trade logs</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>1 chart analysis</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>Basic analytics</span></li>
                                </ul>
                                <button disabled class="w-full py-3 bg-slate-700 text-slate-500 rounded-lg cursor-not-allowed">
                                    ${subData.status === 'trial' ? 'Current Plan' : 'Expired'}
                                </button>
                            </div>
                            <div class="glass rounded-xl p-6 border-2 border-blue-500 relative">
                                <div class="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-500 text-white text-xs px-3 py-1 rounded-full">RECOMMENDED</div>
                                <div class="text-center mb-6">
                                    <h2 class="text-xl font-semibold mb-2">Pro Trader</h2>
                                    <div class="text-4xl font-bold mb-2">$15<span class="text-lg text-slate-400">/month</span></div>
                                </div>
                                <ul class="space-y-3 mb-6">
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>Unlimited trades</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>All courses</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>AI chart analysis</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>Priority support</span></li>
                                </ul>
                                <button onclick="initiatePayment()" class="w-full btn-primary py-3 rounded-lg font-medium">
                                    ${subData.status === 'active' ? 'Renew Subscription' : 'Subscribe Now'}
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            } catch (error) {
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <h1 class="text-2xl font-bold mb-6">Subscription</h1>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl mx-auto">
                            <div class="glass rounded-xl p-6">
                                <div class="text-center mb-6">
                                    <h2 class="text-xl font-semibold mb-2">Free Trial</h2>
                                    <div class="text-4xl font-bold mb-2">$0</div>
                                    <p class="text-slate-400">3 days access</p>
                                </div>
                                <ul class="space-y-3 mb-6">
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>5 trade logs</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>1 chart analysis</span></li>
                                </ul>
                                <button disabled class="w-full py-3 bg-slate-700 text-slate-500 rounded-lg cursor-not-allowed">Current Plan</button>
                            </div>
                            <div class="glass rounded-xl p-6 border-2 border-blue-500">
                                <div class="text-center mb-6">
                                    <h2 class="text-xl font-semibold mb-2">Pro Trader</h2>
                                    <div class="text-4xl font-bold mb-2">$15<span class="text-lg text-slate-400">/month</span></div>
                                </div>
                                <ul class="space-y-3 mb-6">
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>Unlimited trades</span></li>
                                    <li class="flex items-center gap-2"><i data-lucide="check" class="w-5 h-5 text-green-400"></i><span>All courses</span></li>
                                </ul>
                                <button onclick="initiatePayment()" class="w-full btn-primary py-3 rounded-lg font-medium">Subscribe Now</button>
                            </div>
                        </div>
                    </div>
                `;
            }
        }

        async function initiatePayment() {
            try {
                const response = await apiCall('/subscription/initiate', { method: 'POST' });
                const data = await response.json();
                if (data.authorization_url) {
                    window.open(data.authorization_url, '_blank');
                    showToast('Payment window opened. Complete payment to activate subscription.', 'info');
                } else {
                    showToast('Payment initiation failed', 'error');
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function renderNotifications() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            
            try {
                const response = await apiCall('/notifications');
                const notifications = await response.json();
                
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <div class="flex justify-between items-center mb-6">
                            <h1 class="text-2xl font-bold">Notifications</h1>
                            ${notifications.some(n => !n.is_read) ? `
                            <button onclick="markAllNotificationsRead()" class="text-blue-400 hover:text-blue-300 text-sm">Mark all as read</button>
                            ` : ''}
                        </div>
                        <div class="space-y-3">
                            ${notifications.length > 0 ? notifications.map(n => `
                                <div class="glass rounded-xl p-4 ${n.is_read ? 'opacity-60' : 'border-l-4 border-blue-500'}">
                                    <div class="flex items-start justify-between">
                                        <div class="flex items-start gap-3">
                                            <div class="w-10 h-10 rounded-full ${getNotificationIconBg(n.type)} flex items-center justify-center flex-shrink-0">
                                                <i data-lucide="${getNotificationIcon(n.type)}" class="w-5 h-5 text-white"></i>
                                            </div>
                                            <div>
                                                <p class="font-medium">${n.title}</p>
                                                <p class="text-slate-400 text-sm">${n.message}</p>
                                                <p class="text-slate-500 text-xs mt-1">${formatDate(n.created_at)}</p>
                                            </div>
                                        </div>
                                        ${!n.is_read ? `
                                        <button onclick="markNotificationRead(${n.id})" class="text-blue-400 hover:text-blue-300 text-sm">Mark read</button>
                                        ` : ''}
                                    </div>
                                </div>
                            `).join('') : '<div class="text-center py-12 text-slate-400">No notifications yet</div>'}
                        </div>
                    </div>
                `;
                lucide.createIcons();
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        function getNotificationIcon(type) {
            const icons = {
                'trade': 'trending-up',
                'subscription': 'credit-card',
                'webinar': 'video',
                'course': 'graduation-cap',
                'system': 'info',
                'mentor': 'message-circle'
            };
            return icons[type] || 'bell';
        }

        function getNotificationIconBg(type) {
            const colors = {
                'trade': 'bg-green-500',
                'subscription': 'bg-blue-500',
                'webinar': 'bg-purple-500',
                'course': 'bg-yellow-500',
                'system': 'bg-slate-500',
                'mentor': 'bg-violet-500'
            };
            return colors[type] || 'bg-blue-500';
        }

        async function markNotificationRead(notificationId) {
            try {
                await apiCall(`/notifications/${notificationId}/read`, { method: 'POST' });
                renderNotifications();
                fetchNotifications();
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function markAllNotificationsRead() {
            try {
                await apiCall('/notifications/read-all', { method: 'POST' });
                renderNotifications();
                fetchNotifications();
                showToast('All notifications marked as read', 'success');
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function renderBlog() {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            
            try {
                const response = await apiCall('/blog/posts');
                const posts = await response.json();
                
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <div class="flex items-center justify-between mb-8">
                            <div>
                                <h1 class="text-3xl font-bold gradient-text mb-2">Trading Blog</h1>
                                <p class="text-slate-400">Insights, strategies, and market analysis</p>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                            ${posts.map(post => `
                                <div class="glass rounded-xl overflow-hidden cursor-pointer hover:scale-[1.02] hover:shadow-xl transition-all duration-300 group" onclick="showBlogPost('${post.slug}')">
                                    <div class="h-48 overflow-hidden relative">
                                        ${post.featured_image ? `
                                            <img src="${post.featured_image}" alt="${post.title}" class="w-full h-full object-cover group-hover:scale-110 transition-transform duration-500">
                                        ` : `
                                            <div class="w-full h-full bg-gradient-to-br from-blue-600 via-violet-600 to-purple-600 flex items-center justify-center">
                                                <i data-lucide="newspaper" class="w-16 h-16 text-white/40"></i>
                                            </div>
                                        `}
                                        <div class="absolute top-3 left-3">
                                            <span class="px-3 py-1 rounded-full text-xs font-medium bg-black/50 backdrop-blur-sm text-white border border-white/10">${post.category || 'General'}</span>
                                        </div>
                                    </div>
                                    <div class="p-5">
                                        <h3 class="text-lg font-semibold mb-2 line-clamp-2 group-hover:text-blue-400 transition-colors">${post.title}</h3>
                                        <p class="text-slate-400 text-sm mb-4 line-clamp-2">${post.excerpt || post.content.substring(0, 100) + '...'}</p>
                                        <div class="flex items-center justify-between text-xs text-slate-500">
                                            <span class="flex items-center gap-1"><i data-lucide="calendar" class="w-3 h-3"></i> ${formatDate(post.created_at)}</span>
                                            <span class="flex items-center gap-1 text-blue-400 group-hover:translate-x-1 transition-transform">Read <i data-lucide="arrow-right" class="w-3 h-3"></i></span>
                                        </div>
                                    </div>
                                </div>
                            `).join('') || '<div class="col-span-full text-center py-16"><i data-lucide="newspaper" class="w-16 h-16 mx-auto mb-4 text-slate-600"></i><p class="text-slate-400 text-lg">No blog posts yet</p><p class="text-slate-500 text-sm">Check back soon for new content!</p></div>'}
                        </div>
                    </div>
                `;
                lucide.createIcons();
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        async function showBlogPost(slug) {
            const container = document.getElementById('page-content');
            container.innerHTML = '<div class="flex justify-center py-20"><div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div></div>';
            
            try {
                const response = await apiCall(`/blog/posts/${slug}`);
                const post = await response.json();
                
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <button onclick="navigateTo('blog')" class="mb-6 text-slate-400 hover:text-white flex items-center gap-2 transition-colors">
                            <div class="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center">
                                <i data-lucide="arrow-left" class="w-4 h-4"></i>
                            </div>
                            <span>Back to Blog</span>
                        </button>
                        
                        <article class="max-w-4xl mx-auto">
                            ${post.featured_image ? `
                                <div class="rounded-2xl overflow-hidden mb-8 h-64 md:h-80">
                                    <img src="${post.featured_image}" alt="${post.title}" class="w-full h-full object-cover">
                                </div>
                            ` : ''}
                            
                            <div class="glass rounded-2xl p-6 md:p-10">
                                <div class="flex items-center gap-3 mb-6">
                                    <span class="px-3 py-1 rounded-full text-xs font-medium bg-blue-500/20 text-blue-400">${post.category || 'General'}</span>
                                    <span class="text-slate-500 text-sm flex items-center gap-1">
                                        <i data-lucide="calendar" class="w-4 h-4"></i> ${formatDate(post.created_at)}
                                    </span>
                                    ${post.view_count ? `
                                        <span class="text-slate-500 text-sm flex items-center gap-1">
                                            <i data-lucide="eye" class="w-4 h-4"></i> ${post.view_count} views
                                        </span>
                                    ` : ''}
                                </div>
                                
                                <h1 class="text-3xl md:text-4xl font-bold mb-8 leading-tight">${post.title}</h1>
                                
                                <div class="prose prose-invert prose-lg max-w-none">
                                    ${post.content.split('\n\n').map(para => `<p class="mb-4 text-slate-300 leading-relaxed">${para}</p>`).join('')}
                                </div>
                                
                                ${post.tags && post.tags.length > 0 ? `
                                    <div class="mt-8 pt-6 border-t border-white/10">
                                        <div class="flex flex-wrap gap-2">
                                            ${post.tags.map(tag => `<span class="px-3 py-1 rounded-full text-xs bg-slate-800 text-slate-400">#${tag}</span>`).join('')}
                                        </div>
                                    </div>
                                ` : ''}
                            </div>
                        </article>
                    </div>
                `;
                lucide.createIcons();
            } catch (error) {
                container.innerHTML = `<div class="text-red-400 text-center py-20">${error.message}</div>`;
            }
        }

        async function renderAdmin() {
            const container = document.getElementById('page-content');
            container.innerHTML = `
                <div class="flex justify-center py-20">
                    <div class="loading-spinner w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full"></div>
                </div>
            `;
            
            try {
                console.log('Fetching admin stats...');
                const response = await apiCall('/admin/stats');
                
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Admin access failed (${response.status})`);
                }
                
                const stats = await response.json();
                console.log('Admin stats:', stats);
                
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <div class="flex items-center justify-between mb-8">
                            <div>
                                <h1 class="text-3xl font-bold gradient-text mb-2">Admin Dashboard</h1>
                                <p class="text-slate-400">Platform overview and management</p>
                            </div>
                            <div class="flex items-center gap-2 px-4 py-2 bg-orange-500/20 rounded-lg">
                                <i data-lucide="shield" class="w-5 h-5 text-orange-400"></i>
                                <span class="text-orange-400 text-sm font-medium">Admin Access</span>
                            </div>
                        </div>
                        
                        <!-- Stats Grid -->
                        <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
                            <div class="glass rounded-xl p-5 hover:bg-white/5 transition-colors">
                                <div class="flex items-center gap-3 mb-2">
                                    <div class="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                                        <i data-lucide="users" class="w-5 h-5 text-blue-400"></i>
                                    </div>
                                    <div class="text-slate-400 text-sm">Total Users</div>
                                </div>
                                <div class="text-3xl font-bold">${stats.total_users || 0}</div>
                                <div class="text-xs text-slate-500 mt-1">+${stats.new_users_7d || 0} this week</div>
                            </div>
                            <div class="glass rounded-xl p-5 hover:bg-white/5 transition-colors">
                                <div class="flex items-center gap-3 mb-2">
                                    <div class="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center">
                                        <i data-lucide="credit-card" class="w-5 h-5 text-green-400"></i>
                                    </div>
                                    <div class="text-slate-400 text-sm">Active Subs</div>
                                </div>
                                <div class="text-3xl font-bold text-green-400">${stats.active_subscriptions || 0}</div>
                            </div>
                            <div class="glass rounded-xl p-5 hover:bg-white/5 transition-colors">
                                <div class="flex items-center gap-3 mb-2">
                                    <div class="w-10 h-10 rounded-lg bg-yellow-500/20 flex items-center justify-center">
                                        <i data-lucide="clock" class="w-5 h-5 text-yellow-400"></i>
                                    </div>
                                    <div class="text-slate-400 text-sm">Trial Users</div>
                                </div>
                                <div class="text-3xl font-bold text-yellow-400">${stats.trial_users || 0}</div>
                            </div>
                            <div class="glass rounded-xl p-5 hover:bg-white/5 transition-colors">
                                <div class="flex items-center gap-3 mb-2">
                                    <div class="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                                        <i data-lucide="dollar-sign" class="w-5 h-5 text-purple-400"></i>
                                    </div>
                                    <div class="text-slate-400 text-sm">Revenue</div>
                                </div>
                                <div class="text-3xl font-bold text-purple-400">$${stats.total_revenue || 0}</div>
                                <div class="text-xs text-slate-500 mt-1">+$${stats.revenue_30d || 0} this month</div>
                            </div>
                        </div>
                        
                        <!-- Content Stats -->
                        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                            <div class="glass rounded-xl p-4 text-center">
                                <div class="text-slate-400 text-sm mb-1">Courses</div>
                                <div class="text-xl font-bold">${stats.total_courses || 0}</div>
                            </div>
                            <div class="glass rounded-xl p-4 text-center">
                                <div class="text-slate-400 text-sm mb-1">Webinars</div>
                                <div class="text-xl font-bold">${stats.total_webinars || 0}</div>
                            </div>
                            <div class="glass rounded-xl p-4 text-center">
                                <div class="text-slate-400 text-sm mb-1">Blog Posts</div>
                                <div class="text-xl font-bold">${stats.published_blog_posts || 0}/${stats.total_blog_posts || 0}</div>
                            </div>
                            <div class="glass rounded-xl p-4 text-center">
                                <div class="text-slate-400 text-sm mb-1">Total Trades</div>
                                <div class="text-xl font-bold">${stats.total_trades || 0}</div>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
                            <div class="glass rounded-xl p-6">
                                <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
                                    <i data-lucide="users" class="w-5 h-5 text-blue-400"></i>
                                    Recent Users
                                </h2>
                                <div class="space-y-3 max-h-80 overflow-y-auto">
                                    ${stats.recent_users && stats.recent_users.length > 0 ? stats.recent_users.map(u => `
                                        <div class="flex items-center justify-between py-3 border-b border-white/5">
                                            <div>
                                                <p class="font-medium">${u.name || 'Unknown'}</p>
                                                <p class="text-slate-400 text-sm">${u.email || ''}</p>
                                            </div>
                                            <span class="px-2 py-1 rounded text-xs ${u.subscription_status === 'active' ? 'bg-green-500/20 text-green-400' : u.subscription_status === 'trial' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-slate-500/20 text-slate-400'}">${u.subscription_status || 'free'}</span>
                                        </div>
                                    `).join('') : '<p class="text-slate-500 text-center py-4">No users yet</p>'}
                                </div>
                            </div>
                            <div class="glass rounded-xl p-6">
                                <h2 class="text-lg font-semibold mb-4 flex items-center gap-2">
                                    <i data-lucide="zap" class="w-5 h-5 text-yellow-400"></i>
                                    Quick Actions
                                </h2>
                                <div class="space-y-3">
                                    <button onclick="sendAdminEmail()" class="w-full py-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors flex items-center gap-3 px-4">
                                        <i data-lucide="mail" class="w-5 h-5 text-blue-400"></i>
                                        <span>Send Email to Users</span>
                                    </button>
                                    <button onclick="createWebinar()" class="w-full py-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors flex items-center gap-3 px-4">
                                        <i data-lucide="video" class="w-5 h-5 text-red-400"></i>
                                        <span>Create Webinar</span>
                                    </button>
                                    <button onclick="createCourse()" class="w-full py-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors flex items-center gap-3 px-4">
                                        <i data-lucide="book-open" class="w-5 h-5 text-green-400"></i>
                                        <span>Create Course</span>
                                    </button>
                                    <button onclick="createBlogPost()" class="w-full py-3 bg-slate-800 rounded-lg hover:bg-slate-700 transition-colors flex items-center gap-3 px-4">
                                        <i data-lucide="newspaper" class="w-5 h-5 text-cyan-400"></i>
                                        <span>Create Blog Post</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </div>
                `;
                lucide.createIcons();
            } catch (error) {
                console.error('Admin dashboard error:', error);
                container.innerHTML = `
                    <div class="animate-fade-in">
                        <div class="text-center py-20">
                            <i data-lucide="shield-alert" class="w-16 h-16 mx-auto mb-4 text-red-400"></i>
                            <h2 class="text-xl font-bold text-red-400 mb-2">Admin Access Error</h2>
                            <p class="text-slate-400 mb-4">${error.message}</p>
                            <button onclick="checkAdminStatus()" class="btn-primary px-6 py-2 rounded-lg">Check Admin Status</button>
                        </div>
                    </div>
                `;
                lucide.createIcons();
            }
        }
        
        async function createBlogPost() {
            const title = prompt('Enter blog post title:');
            if (!title) return;
            const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
            const content = prompt('Enter blog post content:');
            if (!content) return;
            const category = prompt('Enter category (optional):') || 'General';
            
            try {
                const response = await apiCall('/admin/blog/posts', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: new URLSearchParams({ title, slug, content, category, published: 'true' })
                });
                if (response.ok) {
                    showToast('Blog post created!', 'success');
                    renderAdmin();
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function sendAdminEmail() {
            const recipient = prompt('Enter recipient email (or "all" for all users):');
            if (!recipient) return;
            const subject = prompt('Enter email subject:');
            if (!subject) return;
            const content = prompt('Enter email content:');
            if (!content) return;
            
            try {
                const response = await apiCall('/admin/send-email', {
                    method: 'POST',
                    body: JSON.stringify({ recipient, subject, content })
                });
                if (response.ok) {
                    showToast('Email sent successfully!', 'success');
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function createWebinar() {
            const title = prompt('Enter webinar title:');
            if (!title) return;
            const scheduledAt = prompt('Enter scheduled date (YYYY-MM-DD HH:MM):');
            if (!scheduledAt) return;
            
            try {
                const response = await apiCall('/webinars', {
                    method: 'POST',
                    body: JSON.stringify({ title, scheduled_at: scheduledAt })
                });
                if (response.ok) {
                    showToast('Webinar created!', 'success');
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        async function createCourse() {
            const title = prompt('Enter course title:');
            if (!title) return;
            const level = prompt('Enter level (beginner/intermediate/advanced):');
            if (!level) return;
            
            try {
                const response = await apiCall('/courses', {
                    method: 'POST',
                    body: JSON.stringify({ title, level })
                });
                if (response.ok) {
                    showToast('Course created!', 'success');
                }
            } catch (error) {
                showToast(error.message, 'error');
            }
        }

        // Health check function to verify backend connectivity
        async function checkBackendHealth() {
            try {
                const response = await fetch(`${API_URL}/health`, { method: 'GET' });
                if (response.ok) {
                    console.log('Backend is healthy');
                    return true;
                }
            } catch (error) {
                console.error('Backend health check failed:', error);
            }
            return false;
        }

        document.addEventListener('DOMContentLoaded', async () => {
            // Check backend health first
            const isHealthy = await checkBackendHealth();
            if (!isHealthy) {
                console.warn('Backend may not be accessible. API URL:', API_URL);
            }
            
            if (authToken) { 
                showApp(); 
            } else { 
                document.getElementById('auth-screen').classList.remove('hidden'); 
            }
            lucide.createIcons();
        });
    </script>
</body>
</html>
