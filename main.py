<script>
const API_URL = 'https://pipways-api-nhem.onrender.com';
let authToken = localStorage.getItem('pipways_token');
let currentUser = JSON.parse(localStorage.getItem('pipways_user') || '{}');

if (authToken) {
    showApp();
} else {
    showAuth();
}

function showAuth() {
    document.getElementById('auth-screen').classList.remove('hidden');
    document.getElementById('app').classList.add('hidden');
}

function showApp() {
    document.getElementById('auth-screen').classList.add('hidden');
    document.getElementById('app').classList.remove('hidden');
    showPage('dashboard');
}

function showAuthTab(tab) {
    const loginBtn = document.getElementById('tab-login');
    const registerBtn = document.getElementById('tab-register');
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    
    if (tab === 'login') {
        loginBtn.classList.add('bg-blue-500', 'text-white');
        loginBtn.classList.remove('bg-slate-800', 'text-slate-400');
        registerBtn.classList.remove('bg-blue-500', 'text-white');
        registerBtn.classList.add('bg-slate-800', 'text-slate-400');
        loginForm.classList.remove('hidden');
        registerForm.classList.add('hidden');
    } else {
        registerBtn.classList.add('bg-blue-500', 'text-white');
        registerBtn.classList.remove('bg-slate-800', 'text-slate-400');
        loginBtn.classList.remove('bg-blue-500', 'text-white');
        loginBtn.classList.add('bg-slate-800', 'text-slate-400');
        registerForm.classList.remove('hidden');
        loginForm.classList.add('hidden');
    }
    document.getElementById('auth-error').classList.add('hidden');
}

// Helper function to extract error message from various error formats
function getErrorMessage(data) {
    if (typeof data === 'string') return data;
    if (data.detail) {
        if (typeof data.detail === 'string') return data.detail;
        if (Array.isArray(data.detail)) {
            return data.detail.map(err => {
                if (typeof err === 'string') return err;
                if (err.msg) return err.msg;
                if (err.message) return err.message;
                return JSON.stringify(err);
            }).join(', ');
        }
        return JSON.stringify(data.detail);
    }
    if (data.message) return data.message;
    if (data.error) return data.error;
    return JSON.stringify(data);
}

async function handleLogin(e) {
    e.preventDefault();
    const form = e.target;
    const errorEl = document.getElementById('auth-error');
    
    try {
        const formData = new URLSearchParams();
        formData.append('email', form.email.value);
        formData.append('password', form.password.value);
        
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: formData.toString()
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(getErrorMessage(data));
        }
        
        authToken = data.access_token;
        localStorage.setItem('pipways_token', authToken);
        localStorage.setItem('pipways_user', JSON.stringify(data));
        showApp();
        
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const form = e.target;
    const errorEl = document.getElementById('auth-error');
    
    try {
        const formData = new URLSearchParams();
        formData.append('email', form.email.value);
        formData.append('password', form.password.value);
        formData.append('name', form.name.value);
        
        const response = await fetch(`${API_URL}/auth/register`, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: formData.toString()
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(getErrorMessage(data));
        }
        
        authToken = data.access_token;
        localStorage.setItem('pipways_token', authToken);
        localStorage.setItem('pipways_user', JSON.stringify(data));
        showApp();
        
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.remove('hidden');
    }
}

function logout() {
    localStorage.removeItem('pipways_token');
    localStorage.removeItem('pipways_user');
    authToken = null;
    currentUser = {};
    showAuth();
}

async function apiCall(endpoint, options = {}) {
    const headers = {
        'Authorization': `Bearer ${authToken}`,
        ...options.headers
    };
    
    const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        logout();
        throw new Error('Session expired. Please login again.');
    }
    
    return response;
}

async function showPage(page) {
    const content = document.getElementById('content');
    
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.remove('bg-blue-500/10', 'text-blue-400', 'border-r-2', 'border-blue-500');
        btn.classList.add('text-slate-400');
    });
    
    if (event && event.target) {
        event.target.closest('.nav-btn').classList.add('bg-blue-500/10', 'text-blue-400', 'border-r-2', 'border-blue-500');
        event.target.closest('.nav-btn').classList.remove('text-slate-400');
    }

    if (page === 'dashboard') {
        await renderDashboard(content);
    } else if (page === 'journal') {
        renderJournal(content);
    } else if (page === 'discipline') {
        renderDiscipline(content);
    } else if (page === 'mentor') {
        renderMentor(content);
    }
    lucide.createIcons();
}

async function renderDashboard(content) {
    try {
        const response = await apiCall('/trades');
        const trades = await response.json();
        
        if (!response.ok) {
            throw new Error(getErrorMessage(trades));
        }
        
        const totalPips = trades.reduce((a, b) => a + (b.pips || 0), 0);
        const wins = trades.filter(t => t.pips > 0).length;
        const winRate = trades.length ? (wins / trades.length * 100).toFixed(0) : 0;
        
        content.innerHTML = `
            <h2 class="text-3xl font-bold mb-6">Dashboard</h2>
            <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
                <div class="glass rounded-xl p-6">
                    <div class="text-slate-400 text-sm mb-1">Discipline Score</div>
                    <div class="text-3xl font-bold text-blue-400">87</div>
                </div>
                <div class="glass rounded-xl p-6">
                    <div class="text-slate-400 text-sm mb-1">Win Rate</div>
                    <div class="text-3xl font-bold text-violet-400">${winRate}%</div>
                </div>
                <div class="glass rounded-xl p-6">
                    <div class="text-slate-400 text-sm mb-1">Total Pips</div>
                    <div class="text-3xl font-bold ${totalPips>=0?'text-emerald-400':'text-red-400'}">${totalPips>0?'+':''}${totalPips}</div>
                </div>
                <div class="glass rounded-xl p-6">
                    <div class="text-slate-400 text-sm mb-1">Trades</div>
                    <div class="text-3xl font-bold text-orange-400">${trades.length}</div>
                </div>
            </div>
            <div class="glass rounded-xl p-6">
                <h3 class="font-semibold mb-4">Recent Trades</h3>
                <div class="space-y-3">
                    ${trades.slice(0, 5).map(t => `
                        <div class="flex items-center justify-between p-4 bg-slate-800/50 rounded-lg">
                            <div class="flex items-center gap-4">
                                <span class="text-slate-400 text-sm">${new Date(t.created_at).toLocaleDateString()}</span>
                                <span class="font-bold">${t.pair}</span>
                                <span class="px-2 py-1 rounded text-xs ${t.direction==='LONG'?'bg-emerald-500/20 text-emerald-400':'bg-red-500/20 text-red-400'}">${t.direction}</span>
                                <span class="font-mono ${t.pips>=0?'text-emerald-400':'text-red-400'}">${t.pips>0?'+':''}${t.pips}</span>
                            </div>
                            <span class="px-2 py-1 rounded bg-slate-700 text-xs font-bold">${t.grade}</span>
                        </div>
                    `).join('') || '<p class="text-slate-500">No trades yet.</p>'}
                </div>
            </div>
        `;
    } catch (err) {
        content.innerHTML = `<p class="text-red-400">Error: ${err.message}</p>`;
    }
}

function renderJournal(content) {
    content.innerHTML = `
        <h2 class="text-3xl font-bold mb-6">Trade Journal</h2>
        
        <div class="glass rounded-xl p-8 mb-6 border-2 border-dashed border-slate-700 hover:border-blue-500/50 transition-colors text-center">
            <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-blue-500/20 flex items-center justify-center">
                <i data-lucide="upload-cloud" class="w-8 h-8 text-blue-400"></i>
            </div>
            <p class="text-lg mb-4">Upload Chart for AI Analysis</p>
            <input type="file" id="chartUpload" accept="image/*" class="hidden" onchange="analyzeChart(this)">
            <button onclick="document.getElementById('chartUpload').click()" class="px-6 py-3 bg-blue-500 hover:bg-blue-600 rounded-lg font-medium">Select Chart Image</button>
            <div id="analysisResult" class="hidden mt-6 text-left"></div>
        </div>
        
        <div class="glass rounded-xl p-6">
            <h3 class="font-semibold mb-4">Manual Entry</h3>
            <form onsubmit="addTrade(event)" class="grid grid-cols-2 gap-4">
                <input name="pair" placeholder="Pair (EURUSD)" class="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white" required>
                <select name="direction" class="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white">
                    <option>LONG</option><option>SHORT</option>
                </select>
                <input name="pips" type="number" placeholder="Pips (+/-)" class="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white" required>
                <select name="grade" class="bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white">
                    <option>A</option><option>B</option><option>C</option>
                </select>
                <button type="submit" class="col-span-2 bg-emerald-500 hover:bg-emerald-600 rounded-lg py-2 font-medium">Add Trade</button>
            </form>
        </div>
    `;
}

async function analyzeChart(input) {
    const file = input.files[0];
    if (!file) return;
    
    const resultDiv = document.getElementById('analysisResult');
    resultDiv.classList.remove('hidden');
    resultDiv.innerHTML = '<p class="text-center text-blue-400">Analyzing with AI...</p>';
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await apiCall('/analyze-chart', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(getErrorMessage(data));
        }
        
        resultDiv.innerHTML = `
            <div class="bg-slate-800/50 rounded-lg p-4">
                <h4 class="font-semibold mb-2">AI Analysis</h4>
                <pre class="text-sm text-slate-300 whitespace-pre-wrap">${data.analysis}</pre>
            </div>
        `;
    } catch (err) {
        resultDiv.innerHTML = `<p class="text-red-400">Error: ${err.message}</p>`;
    }
    lucide.createIcons();
}

async function addTrade(e) {
    e.preventDefault();
    const f = e.target;
    
    try {
        const formData = new URLSearchParams();
        formData.append('pair', f.pair.value);
        formData.append('direction', f.direction.value);
        formData.append('pips', f.pips.value);
        formData.append('grade', f.grade.value);
        
        const response = await apiCall('/trades', {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: formData.toString()
        });
        
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(getErrorMessage(data));
        }
        
        showPage('dashboard');
    } catch (err) {
        alert('Error: ' + err.message);
    }
}

function renderDiscipline(content) {
    content.innerHTML = `
        <h2 class="text-3xl font-bold mb-6">Discipline Score</h2>
        <div class="glass rounded-xl p-12 text-center">
            <div class="text-5xl font-bold mb-4">87</div>
            <p class="text-xl text-slate-300">Disciplined Trader</p>
        </div>
    `;
}

function renderMentor(content) {
    content.innerHTML = `
        <h2 class="text-3xl font-bold mb-6">AI Mentor</h2>
        <div class="glass rounded-xl p-6 h-[calc(100vh-200px)] flex flex-col">
            <div id="chatHistory" class="flex-1 overflow-y-auto space-y-4 mb-4">
                <div class="flex gap-3">
                    <div class="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center">
                        <i data-lucide="bot" class="w-4 h-4 text-blue-400"></i>
                    </div>
                    <div class="bg-slate-800 rounded-lg px-4 py-2 max-w-[80%]">
                        <p class="text-sm">Hello! I'm your AI trading mentor. Ask me anything about trading psychology and risk management.</p>
                    </div>
                </div>
            </div>
            <div class="flex gap-2">
                <input type="text" id="mentorInput" placeholder="Ask your mentor..." class="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2 text-white" onkeypress="if(event.key==='Enter') askMentor()">
                <button onclick="askMentor()" class="px-6 py-2 bg-blue-500 hover:bg-blue-600 rounded-lg"><i data-lucide="send" class="w-5 h-5"></i></button>
            </div>
        </div>
    `;
}

async function askMentor() {
    const input = document.getElementById('mentorInput');
    const message = input.value;
    if (!message) return;
    
    const chat = document.getElementById('chatHistory');
    
    chat.innerHTML += `
        <div class="flex gap-3 flex-row-reverse">
            <div class="w-8 h-8 rounded-full bg-slate-700 flex items-center justify-center"><i data-lucide="user" class="w-4 h-4"></i></div>
            <div class="bg-blue-600 rounded-lg px-4 py-2 max-w-[80%]"><p class="text-sm">${message}</p></div>
        </div>
    `;
    
    input.value = '';
    chat.scrollTop = chat.scrollHeight;
    
    try {
        const response = await apiCall(`/mentor-chat?message=${encodeURIComponent(message)}`);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(getErrorMessage(data));
        }
        
        chat.innerHTML += `
            <div class="flex gap-3">
                <div class="w-8 h-8 rounded-full bg-blue-500/20 flex items-center justify-center"><i data-lucide="bot" class="w-4 h-4 text-blue-400"></i></div>
                <div class="bg-slate-800 rounded-lg px-4 py-2 max-w-[80%]"><p class="text-sm">${data.response}</p></div>
            </div>
        `;
        
    } catch (err) {
        chat.innerHTML += `<div class="text-red-400 text-sm">Error: ${err.message}</div>`;
    }
    
    lucide.createIcons();
    chat.scrollTop = chat.scrollHeight;
}

lucide.createIcons();
</script>
