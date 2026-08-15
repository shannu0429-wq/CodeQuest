// Detection of local vs production API URL
const API_BASE_URL = localStorage.getItem('api_base_url') || 
  (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' 
    ? 'http://127.0.0.1:5000' 
    : 'https://codequest-sozs.onrender.com');

// Auth Helper
function getAuthHeaders() {
    return {
        'Content-Type': 'application/json',
        'X-User-Id': localStorage.getItem('user_id') || '',
        'X-User-Role': localStorage.getItem('role') || ''
    };
}

function checkAuth(requiredRole = 'user') {
    const userId = localStorage.getItem('user_id');
    const role = localStorage.getItem('role');
    
    if (!userId) {
        window.location.href = 'login.html';
        return false;
    }
    
    if (requiredRole === 'admin' && role !== 'admin') {
        window.location.href = 'dashboard.html';
        return false;
    }
    
    if (requiredRole === 'user' && role === 'admin') {
        window.location.href = 'admin.html';
        return false;
    }
    
    return true;
}

function logout() {
    localStorage.removeItem('user_id');
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    window.location.href = 'index.html';
}
