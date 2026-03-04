/**
 * Pipways Main Application JavaScript
 */

// API Configuration
const API_URL = window.location.origin.includes('localhost') 
    ? 'http://localhost:8000' 
    : 'https://pipways-api-nhem.onrender.com';

// Utility Functions
function showToast(message, type = 'success') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    
    setTimeout(() => {
        toast.remove();
    }, 3000);
}

function formatCurrency(amount, currency = '₦') {
    return currency + amount.toLocaleString();
}

function formatDate(dateString) {
    return new Date(dateString).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Authentication Helpers
function getAuthToken() {
    return localStorage.getItem('pipways_token');
}

function getCurrentUser() {
    const user = localStorage.getItem('pipways_user');
    return user ? JSON.parse(user) : null;
}

function isAuthenticated() {
    return !!getAuthToken();
}

function logout() {
    localStorage.removeItem('pipways_token');
    localStorage.removeItem('pipways_user');
    window.location.href = '/';
}

// API Client
async function apiClient(endpoint, options = {}) {
    const token = getAuthToken();
    
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            ...(token && { 'Authorization': `Bearer ${token}` })
        }
    };
    
    const response = await fetch(`${API_URL}${endpoint}`, {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...options.headers
        }
    });
    
    if (response.status === 401) {
        logout();
        throw new Error('Session expired');
    }
    
    return response;
}

// Initialize Lucide Icons
document.addEventListener('DOMContentLoaded', () => {
    if (typeof lucide !== 'undefined') {
        lucide.createIcons();
    }
});

// Export for module usage
window.Pipways = {
    API_URL,
    showToast,
    formatCurrency,
    formatDate,
    getAuthToken,
    getCurrentUser,
    isAuthenticated,
    logout,
    apiClient
};
