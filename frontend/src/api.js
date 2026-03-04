import axios from 'axios';

// Base URL points to the FastAPI server running on localhost:9000
// Note: As per the README, the server runs on 9000
const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:9000';

const api = axios.create({
    baseURL: API_URL,
    headers: {
        'Content-Type': 'application/json',
    },
});

// Add a request interceptor to inject the JWT token if present
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem('access_token');
        if (token) {
            config.headers['Authorization'] = `Bearer ${token}`;
        }
        return config;
    },
    (error) => {
        return Promise.reject(error);
    }
);

// Response interceptor for handling 401s (token expiration)
api.interceptors.response.use(
    (response) => response,
    (error) => {
        // If the server returns 401 Unauthorized, we clear the token and force logout (if applicable)
        if (error.response && error.response.status === 401) {
            localStorage.removeItem('access_token');
            // Optionally trigger a custom event that auth context can listen to
            window.dispatchEvent(new Event('auth:unauthorized'));
        }
        return Promise.reject(error);
    }
);

export default api;
