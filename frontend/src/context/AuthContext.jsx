import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import api from '../api';

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);

    const fetchCurrentUser = useCallback(async () => {
        const token = localStorage.getItem('access_token');
        if (!token) {
            setUser(null);
            setLoading(false);
            return;
        }

        try {
            // Endpoint we will add to the backend to verify token and fetch user details
            const response = await api.get('/auth/me');
            setUser(response.data);
        } catch (err) {
            console.error("Failed to fetch user context", err);
            setUser(null);
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchCurrentUser();

        // Listen for unauthorized events emitted by the axios interceptor
        const handleUnauthorized = () => {
            setUser(null);
        };

        window.addEventListener('auth:unauthorized', handleUnauthorized);
        return () => window.removeEventListener('auth:unauthorized', handleUnauthorized);
    }, [fetchCurrentUser]);

    const login = async (username, password) => {
        // The backend uses a JSON payload for login based on the models in the current code
        // However standard OAuth2 style login uses form data. Assuming we'll support JSON.
        const response = await api.post('/auth/login', { username, password });

        // We expect the backend to return { access_token: "..." }
        const { access_token } = response.data;
        if (access_token) {
            localStorage.setItem('access_token', access_token);
            await fetchCurrentUser();
        }
        return response.data;
    };

    const register = async (username, email, password) => {
        const response = await api.post('/auth/register', { username, email, password });
        return response.data;
    };

    const logout = () => {
        localStorage.removeItem('access_token');
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ user, loading, login, register, logout, fetchCurrentUser }}>
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => useContext(AuthContext);
