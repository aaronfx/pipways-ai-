<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipways Live Webinars - Zoom Powered</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <!-- Zoom Meeting SDK -->
    <script src="https://source.zoom.us/zoom-meeting-3.1.6.min.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        * { font-family: 'Inter', sans-serif; }
        
        .glass {
            background: rgba(30, 41, 59, 0.7);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        
        .gradient-text {
            background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        #zoom-root {
            width: 100%;
            height: 100vh;
            background: #0f172a;
        }
        
        .webinar-card {
            transition: all 0.3s ease;
        }
        .webinar-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 20px 40px -5px rgba(0, 0, 0, 0.4);
        }
        
        .live-badge {
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }
        
        .loading-spinner {
            border: 3px solid rgba(255, 255, 255, 0.1);
            border-top-color: #3b82f6;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
    </style>
</head>
<body class="bg-slate-950 text-slate-200 antialiased">
    
    <!-- Navigation -->
    <nav class="glass sticky top-0 z-50 border-b border-slate-800">
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div class="flex items-center justify-between h-16">
                <div class="flex items-center gap-3">
                    <div class="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-violet-600 flex items-center justify-center">
                        <i data-lucide="video" class="w-5 h-5 text-white"></i>
                    </div>
                    <div>
                        <h1 class="text-xl font-bold text-white">Pipways</h1>
                        <p class="text-xs text-slate-500">Live Webinars</p>
                    </div>
                </div>
                <div class="flex items-center gap-4">
                    <button onclick="showPage('browse')" class="text-slate-300 hover:text-white transition-colors">Browse</button>
                    <button onclick="showPage('host')" class="text-slate-300 hover:text-white transition-colors">Host</button>
                    <button onclick="backToApp()" class="px-4 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg text-white text-sm font-medium transition-colors">
                        Back to App
                    </button>
                </div>
            </div>
        </div>
    </nav>

    <!-- Main Content -->
    <main id="content" class="min-h-screen">
        <!-- Content injected by JavaScript -->
    </main>

<script>
const API_URL = 'https://pipways-api-nhem.onrender.com/api/webinars';
let authToken = localStorage.getItem('pipways_token');
let currentUser = JSON.parse(localStorage.getItem('pipways_user') || '{}');

// Check auth
if (!authToken) {
    window.location.href = '/';
}

// Initialize Zoom SDK
const ZoomMtg = window.ZoomMtg;
ZoomMtg.preLoadWasm();
ZoomMtg.prepareWebSDK();

// Navigation
function backToApp() {
    window.location.href = '/';
}

function showPage(page, params = {}) {
    const content = document.getElementById('content');
    
    switch(page) {
        case 'browse':
            renderBrowsePage(content);
            break;
        case 'detail':
            renderDetailPage(content, params.id);
            break;
        case 'host':
            renderHostDashboard(content);
            break;
        case 'create':
            renderCreateForm(content);
            break;
        case 'zoom':
            renderZoomMeeting(content, params);
            break;
        default:
            renderBrowsePage(content);
    }
}

// ==================== BROWSE PAGE ====================

async function renderBrowsePage(container) {
    container.innerHTML = `
        <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div class="text-center mb-12">
                <h2 class="text-4xl font-bold text-white mb-4">Live Trading Webinars</h2>
                <p class="text-slate-400 text-lg">Learn from professional traders in interactive Zoom sessions</p>
            </div>
            
            <div class="flex justify-center mb-8">
                <div class="inline-flex bg-slate-800 rounded-lg p-1">
                    <button onclick="filterWebinars('all')" class="px-6 py-2 rounded-md bg-blue-500 text-white text-sm font-medium transition-all" id="filter-all">All</button>
                    <button onclick="filterWebinars('upcoming')" class="px-6 py-2 rounded-md text-slate-400 hover:text-white text-sm font-medium transition-all" id="filter-upcoming">Upcoming</button>
                    <button onclick="filterWebinars('past')" class="px-6 py-2 rounded-md text-slate-400 hover:text-white text-sm font-medium transition-all" id="filter-past">Past</button>
                </div>
            </div>
            
            <div id="webinars-grid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <div class="col-span-full flex justify-center py-20">
                    <div class="loading-spinner"></div>
                </div>
            </div>
        </div>
    `;
    
    lucide.createIcons();
    await loadWebinars('all');
}

async function loadWebinars(filter) {
    const grid = document.getElementById('webinars-grid');
    
    try {
        const response = await fetch(API_URL + (filter === 'upcoming' ? '?upcoming=true' : ''), {
            headers: {'Authorization': 'Bearer ' + authToken}
        });
        
        if (!response.ok) throw new Error('Failed to load webinars');
        
        const webinars = await response.json();
        
        if (webinars.length === 0) {
            grid.innerHTML = `
                <div class="col-span-full text-center py-20">
                    <i data-lucide="calendar-x" class="w-16 h-16 text-slate-600 mx-auto mb-4"></i>
                    <p class="text-slate-500 text-lg">No webinars found</p>
                    <button onclick="showPage('create')" class="mt-4 text-blue-400 hover:text-blue-300">Create your first webinar</button>
                </div>
            `;
            lucide.createIcons();
            return;
        }
        
        let html = '';
        webinars.forEach(w => {
            const date = new Date(w.start_time);
            const isLive = w.status === 'started';
            const isPast = new Date(w.start_time) < new Date() && w.status !== 'started';
            
            html += `
                <div class="webinar-card glass rounded-xl overflow-hidden cursor-pointer" onclick="showPage('detail', {id: '${w.id}'})">
                    <div class="h-48 bg-gradient-to-br from-blue-500/20 to-violet-500/20 flex items-center justify-center relative">
                        ${isLive ? '<div class="absolute top-4 left-4 px-3 py-1 bg-red-500 text-white text-xs font-bold rounded-full live-badge flex items-center gap-2"><span class="w-2 h-2 bg-white rounded-full"></span>LIVE</div>' : ''}
                        <i data-lucide="${isPast ? 'play-circle' : 'video'}" class="w-16 h-16 ${isPast ? 'text-emerald-400' : 'text-blue-400'}"></i>
                    </div>
                    <div class="p-6">
                        <div class="flex items-center justify-between mb-3">
                            <span class="text-xs text-slate-500">${date.toLocaleDateString()} • ${date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                            <span class="text-xs px-2 py-1 ${isLive ? 'bg-red-500/20 text-red-400' : isPast ? 'bg-slate-700 text-slate-400' : 'bg-emerald-500/20 text-emerald-400'} rounded-full">${isLive ? 'Live Now' : isPast ? 'Ended' : 'Upcoming'}</span>
                        </div>
                        <h3 class="text-lg font-bold text-white mb-2 line-clamp-2">${w.topic}</h3>
                        <p class="text-sm text-slate-400 mb-4">${w.duration} minutes</p>
                        <div class="flex items-center justify-between">
                            <span class="text-xs text-slate-500">Zoom Meeting</span>
                            <span class="text-blue-400 text-sm font-medium">View Details →</span>
                        </div>
                    </div>
                </div>
            `;
        });
        
        grid.innerHTML = html;
        lucide.createIcons();
        
    } catch (err) {
        grid.innerHTML = `
            <div class="col-span-full text-center py-20">
                <i data-lucide="alert-circle" class="w-16 h-16 text-red-500 mx-auto mb-4"></i>
                <p class="text-red-400">Error loading webinars: ${err.message}</p>
                <button onclick="loadWebinars('${filter}')" class="mt-4 text-blue-400 hover:text-blue-300">Retry</button>
            </div>
        `;
        lucide.createIcons();
    }
}

function filterWebinars(type) {
    // Update button styles
    ['all', 'upcoming', 'past'].forEach(t => {
        const btn = document.getElementById('filter-' + t);
        if (t === type) {
            btn.classList.remove('text-slate-400');
            btn.classList.add('bg-blue-500', 'text-white');
        } else {
            btn.classList.remove('bg-blue-500', 'text-white');
            btn.classList.add('text-slate-400');
        }
    });
    
    loadWebinars(type);
}

// ==================== DETAIL PAGE ====================

async function renderDetailPage(container, id) {
    try {
        const response = await fetch(API_URL + '/' + id, {
            headers: {'Authorization': 'Bearer ' + authToken}
        });
        
        if (!response.ok) throw new Error('Webinar not found');
        
        const w = await response.json();
        const date = new Date(w.start_time);
        const isLive = w.status === 'started';
        const isHost = w.created_by === currentUser.email;
        
        container.innerHTML = `
            <div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                <button onclick="showPage('browse')" class="mb-6 flex items-center gap-2 text-slate-400 hover:text-white transition-colors">
                    <i data-lucide="arrow-left" class="w-4 h-4"></i> Back to webinars
                </button>
                
                <div class="glass rounded-2xl overflow-hidden">
                    <div class="h-64 bg-gradient-to-br from-blue-500/20 to-violet-500/20 flex items-center justify-center relative">
                        ${isLive ? '<div class="absolute top-6 left-6 px-4 py-2 bg-red-500 text-white font-bold rounded-full live-badge flex items-center gap-2"><span class="w-2 h-2 bg-white rounded-full animate-pulse"></span>LIVE NOW</div>' : ''}
                        <i data-lucide="video" class="w-24 h-24 text-blue-400"></i>
                    </div>
                    
                    <div class="p-8">
                        <div class="flex items-start justify-between mb-6">
                            <div>
                                <h1 class="text-3xl font-bold text-white mb-2">${w.topic}</h1>
                                <p class="text-slate-400">Hosted by ${w.created_by}</p>
                            </div>
                            <div class="text-right">
                                <div class="text-sm text-slate-500 mb-1">Webinar ID</div>
                                <div class="font-mono text-lg text-white">${w.id}</div>
                            </div>
                        </div>
                        
                        <div class="grid grid-cols-3 gap-4 mb-8">
                            <div class="p-4 bg-slate-800/50 rounded-xl text-center">
                                <i data-lucide="calendar" class="w-6 h-6 text-blue-400 mx-auto mb-2"></i>
                                <div class="text-sm text-slate-400">${date.toLocaleDateString()}</div>
                            </div>
                            <div class="p-4 bg-slate-800/50 rounded-xl text-center">
                                <i data-lucide="clock" class="w-6 h-6 text-blue-400 mx-auto mb-2"></i>
                                <div class="text-sm text-slate-400">${date.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</div>
                            </div>
                            <div class="p-4 bg-slate-800/50 rounded-xl text-center">
                                <i data-lucide="hourglass" class="w-6 h-6 text-blue-400 mx-auto mb-2"></i>
                                <div class="text-sm text-slate-400">${w.duration} minutes</div>
                            </div>
                        </div>
                        
                        ${w.description ? `<p class="text-slate-300 mb-8 leading-relaxed">${w.description}</p>` : ''}
                        
                        <div class="flex gap-4">
                            ${isLive ? `
                                <button onclick="joinWebinar('${w.id}')" class="flex-1 bg-red-500 hover:bg-red-600 rounded-xl py-4 font-bold text-white text-lg transition-colors flex items-center justify-center gap-2">
                                    <i data-lucide="play" class="w-5 h-5"></i> Join Live Webinar
                                </button>
                            ` : isHost ? `
                                <button onclick="startWebinar('${w.id}')" class="flex-1 bg-emerald-500 hover:bg-emerald-600 rounded-xl py-4 font-bold text-white text-lg transition-colors flex items-center justify-center gap-2">
                                    <i data-lucide="play" class="w-5 h-5"></i> Start Webinar
                                </button>
                            ` : `
                                <button onclick="addToCalendar('${w.topic}', '${w.start_time}')" class="flex-1 bg-blue-500 hover:bg-blue-600 rounded-xl py-4 font-bold text-white text-lg transition-colors flex items-center justify-center gap-2">
                                    <i data-lucide="calendar-plus" class="w-5 h-5"></i> Add to Calendar
                                </button>
                            `}
                            
                            ${isHost ? `
                                <button onclick="deleteWebinar('${w.id}')" class="px-6 py-4 bg-slate-700 hover:bg-red-500/20 hover:text-red-400 rounded-xl text-slate-300 transition-colors">
                                    <i data-lucide="trash-2" class="w-5 h-5"></i>
                                </button>
                            ` : ''}
                        </div>
                        
                        ${w.password ? `
                            <div class="mt-6 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                                <div class="flex items-center gap-2 text-yellow-400 mb-1">
                                    <i data-lucide="lock" class="w-4 h-4"></i>
                                    <span class="font-medium">Password Required</span>
                                </div>
                                <p class="text-sm text-slate-400">Passcode: <span class="font-mono text-white">${w.password}</span></p>
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
        
        lucide.createIcons();
        
    } catch (err) {
        container.innerHTML = `
            <div class="max-w-4xl mx-auto px-4 py-20 text-center">
                <i data-lucide="alert-circle" class="w-16 h-16 text-red-500 mx-auto mb-4"></i>
                <h2 class="text-2xl font-bold text-white mb-2">Error Loading Webinar</h2>
                <p class="text-slate-400">${err.message}</p>
                <button onclick="showPage('browse')" class="mt-6 text-blue-400 hover:text-blue-300">Back to Browse</button>
            </div>
        `;
        lucide.createIcons();
    }
}

// ==================== ZOOM INTEGRATION ====================

async function joinWebinar(webinarId) {
    try {
        // Get join credentials from our API
        const response = await fetch(API_URL + '/' + webinarId + '/join', {
            method: 'POST',
            headers: {'Authorization': 'Bearer ' + authToken}
        });
        
        if (!response.ok) throw new Error('Failed to get join credentials');
        
        const creds = await response.json();
        
        // Show Zoom meeting UI
        showPage('zoom', creds);
        
    } catch (err) {
        alert('Error joining webinar: ' + err.message);
    }
}

function renderZoomMeeting(container, creds) {
    container.innerHTML = `
        <div class="fixed inset-0 bg-slate-950 z-50">
            <div class="h-full flex flex-col">
                <div class="h-14 bg-slate-900 border-b border-slate-800 flex items-center justify-between px-4">
                    <div class="flex items-center gap-3">
                        <div class="w-8 h-8 rounded bg-blue-500 flex items-center justify-center">
                            <i data-lucide="video" class="w-4 h-4 text-white"></i>
                        </div>
                        <span class="text-white font-medium">Pipways Live Webinar</span>
                    </div>
                    <button onclick="leaveMeeting()" class="px-4 py-2 bg-red-500 hover:bg-red-600 rounded-lg text-white text-sm font-medium">
                        Leave
                    </button>
                </div>
                <div id="zoom-meeting-container" class="flex-1"></div>
            </div>
        </div>
    `;
    
    lucide.createIcons();
    
    // Initialize Zoom Meeting SDK
    const meetingConfig = {
        sdkKey: creds.sdk_key,
        meetingNumber: creds.meeting_number,
        userName: creds.user_name || 'Guest',
        passWord: creds.password || '',
        leaveUrl: window.location.href,
        role: creds.role, // 0 = attendee, 1 = host
        userEmail: creds.user_email || '',
        lang: 'en-US',
        signature: creds.signature,
        china: false,
        disablePreview: false
    };
    
    // Join meeting
    ZoomMtg.init({
        leaveUrl: meetingConfig.leaveUrl,
        isSupportAV: true,
        disableJoinAudio: false,
        screenShare: true,
        videoHeader: [
            {type: 'host', show: true},
            {type: 'active', show: true}
        ]
    });
    
    ZoomMtg.join({
        meetingNumber: meetingConfig.meetingNumber,
        userName: meetingConfig.userName,
        signature: meetingConfig.signature,
        sdkKey: meetingConfig.sdkKey,
        userEmail: meetingConfig.userEmail,
        passWord: meetingConfig.passWord,
        success: (success) => {
            console.log('Join success', success);
        },
        error: (error) => {
            console.error('Join error', error);
            alert('Failed to join meeting: ' + error.errorMessage);
            showPage('browse');
        }
    });
}

function leaveMeeting() {
    ZoomMtg.leaveMeeting({
        success: () => {
            showPage('browse');
        }
    });
}

// ==================== HOST DASHBOARD ====================

async function renderHostDashboard(container) {
    container.innerHTML = `
        <div class="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div class="flex items-center justify-between mb-8">
                <div>
                    <h2 class="text-3xl font-bold text-white mb-2">Host Dashboard</h2>
                    <p class="text-slate-400">Manage your trading webinars</p>
                </div>
                <button onclick="showPage('create')" class="px-6 py-3 bg-blue-500 hover:bg-blue-600 rounded-lg text-white font-medium flex items-center gap-2">
                    <i data-lucide="plus" class="w-4 h-4"></i> New Webinar
                </button>
            </div>
            
            <div class="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
                <div class="glass rounded-xl p-6">
                    <div class="text-3xl font-bold text-white mb-1" id="stat-total">-</div>
                    <div class="text-sm text-slate-400">Total Webinars</div>
                </div>
                <div class="glass rounded-xl p-6">
                    <div class="text-3xl font-bold text-emerald-400 mb-1" id="stat-upcoming">-</div>
                    <div class="text-sm text-slate-400">Upcoming</div>
                </div>
                <div class="glass rounded-xl p-6">
                    <div class="text-3xl font-bold text-blue-400 mb-1" id="stat-past">-</div>
                    <div class="text-sm text-slate-400">Past</div>
                </div>
            </div>
            
            <div class="glass rounded-xl overflow-hidden">
                <div class="p-6 border-b border-slate-800">
                    <h3 class="text-lg font-semibold text-white">Your Webinars</h3>
                </div>
                <div id="host-webinars-list" class="divide-y divide-slate-800">
                    <div class="p-8 text-center">
                        <div class="loading-spinner mx-auto"></div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    lucide.createIcons();
    await loadHostStats();
    await loadHostWebinars();
}

async function loadHostStats() {
    try {
        const response = await fetch(API_URL + '/host/stats', {
            headers: {'Authorization': 'Bearer ' + authToken}
        });
        
        if (!response.ok) return;
        
        const stats = await response.json();
        document.getElementById('stat-total').textContent = stats.total_webinars;
        document.getElementById('stat-upcoming').textContent = stats.upcoming;
        document.getElementById('stat-past').textContent = stats.past;
        
    } catch (err) {
        console.error('Failed to load stats:', err);
    }
}

async function loadHostWebinars() {
    const list = document.getElementById('host-webinars-list');
    
    try {
        const response = await fetch(API_URL, {
            headers: {'Authorization': 'Bearer ' + authToken}
        });
        
        const webinars = await response.json();
        // Filter to only show webinars created by current user
        const myWebinars = webinars.filter(w => w.created_by === currentUser.email);
        
        if (myWebinars.length === 0) {
            list.innerHTML = `
                <div class="p-8 text-center text-slate-500">
                    <i data-lucide="video-off" class="w-12 h-12 mx-auto mb-3"></i>
                    <p>You haven't created any webinars yet</p>
                    <button onclick="showPage('create')" class="mt-4 text-blue-400 hover:text-blue-300">Create your first webinar</button>
                </div>
            `;
            lucide.createIcons();
            return;
        }
        
        let html = '';
        myWebinars.forEach(w => {
            const date = new Date(w.start_time);
            html += `
                <div class="p-6 flex items-center justify-between hover:bg-slate-800/50 transition-colors">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 rounded-lg bg-blue-500/20 flex items-center justify-center">
                            <i data-lucide="video" class="w-6 h-6 text-blue-400"></i>
                        </div>
                        <div>
                            <h4 class="font-semibold text-white">${w.topic}</h4>
                            <p class="text-sm text-slate-400">${date.toLocaleString()} • ${w.status}</p>
                        </div>
                    </div>
                    <div class="flex items-center gap-2">
                        ${w.status === 'started' ? `
                            <button onclick="joinWebinar('${w.id}')" class="px-4 py-2 bg-red-500 hover:bg-red-600 rounded-lg text-white text-sm font-medium">
                                Join Live
                            </button>
                        ` : `
                            <button onclick="showPage('detail', {id: '${w.id}'})" class="px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-white text-sm font-medium">
                                Manage
                            </button>
                        `}
                    </div>
                </div>
            `;
        });
        
        list.innerHTML = html;
        lucide.createIcons();
        
    } catch (err) {
        list.innerHTML = `<div class="p-8 text-center text-red-400">Error loading webinars</div>`;
    }
}

// ==================== CREATE WEBINAR ====================

function renderCreateForm(container) {
    const now = new Date();
    now.setMinutes(now.getMinutes() - now.getTimezoneOffset() + 60);
    
    container.innerHTML = `
        <div class="max-w-2xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <button onclick="showPage('host')" class="mb-6 flex items-center gap-2 text-slate-400 hover:text-white transition-colors">
                <i data-lucide="arrow-left" class="w-4 h-4"></i> Back to dashboard
            </button>
            
            <div class="glass rounded-2xl p-8">
                <h2 class="text-2xl font-bold text-white mb-6">Create New Webinar</h2>
                
                <form onsubmit="createWebinar(event)" class="space-y-6">
                    <div>
                        <label class="block text-sm font-medium text-slate-400 mb-2">Webinar Title</label>
                        <input type="text" name="topic" required 
                            class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none"
                            placeholder="e.g., Advanced Forex Scalping Masterclass">
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-slate-400 mb-2">Description</label>
                        <textarea name="description" rows="4" required
                            class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none"
                            placeholder="What will attendees learn in this session?"></textarea>
                    </div>
                    
                    <div class="grid grid-cols-2 gap-4">
                        <div>
                            <label class="block text-sm font-medium text-slate-400 mb-2">Date & Time</label>
                            <input type="datetime-local" name="scheduled_at" required
                                class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none"
                                value="${now.toISOString().slice(0, 16)}">
                        </div>
                        <div>
                            <label class="block text-sm font-medium text-slate-400 mb-2">Duration (minutes)</label>
                            <select name="duration" class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none">
                                <option value="30">30 minutes</option>
                                <option value="60" selected>1 hour</option>
                                <option value="90">1.5 hours</option>
                                <option value="120">2 hours</option>
                            </select>
                        </div>
                    </div>
                    
                    <div>
                        <label class="block text-sm font-medium text-slate-400 mb-2">Password (optional)</label>
                        <input type="text" name="password"
                            class="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white focus:border-blue-500 focus:outline-none"
                            placeholder="Leave empty for no password">
                    </div>
                    
                    <div class="flex gap-4 pt-4">
                        <button type="submit" class="flex-1 bg-blue-500 hover:bg-blue-600 rounded-lg py-3 font-bold text-white transition-colors">
                            Create Webinar
                        </button>
                        <button type="button" onclick="showPage('host')" class="px-6 py-3 bg-slate-700 hover:bg-slate-600 rounded-lg text-white font-medium">
                            Cancel
                        </button>
                    </div>
                </form>
            </div>
        </div>
    `;
    
    lucide.createIcons();
}

async function createWebinar(e) {
    e.preventDefault();
    const form = e.target;
    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.innerHTML = '<div class="loading-spinner w-5 h-5 border-2 inline-block mr-2"></div>Creating...';
    
    try {
        const formData = new FormData(form);
        
        const response = await fetch(API_URL, {
            method: 'POST',
            headers: {'Authorization': 'Bearer ' + authToken},
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.detail || 'Failed to create webinar');
        }
        
        // Show success with start URL for host
        alert(`Webinar created successfully!\\n\\nJoin URL: ${data.webinar.join_url}\\nStart URL: ${data.webinar.start_url}`);
        showPage('host');
        
    } catch (err) {
        alert('Error: ' + err.message);
        btn.disabled = false;
        btn.textContent = 'Create Webinar';
    }
}

async function deleteWebinar(id) {
    if (!confirm('Are you sure you want to cancel this webinar?')) return;
    
    try {
        const response = await fetch(API_URL + '/' + id, {
            method: 'DELETE',
            headers: {'Authorization': 'Bearer ' + authToken}
        });
        
        if (response.ok) {
            alert('Webinar cancelled');
            showPage('host');
        } else {
            throw new Error('Failed to delete');
        }
        
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

function addToCalendar(topic, startTime) {
    const date = new Date(startTime);
    const endDate = new Date(date.getTime() + 60 * 60 * 1000);
    
    const googleCalendarUrl = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(topic)}&dates=${date.toISOString().replace(/[-:]/g, '').split('.')[0]}/${endDate.toISOString().replace(/[-:]/g, '').split('.')[0]}`;
    
    window.open(googleCalendarUrl, '_blank');
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    showPage('browse');
});
</script>

</body>
</html>
