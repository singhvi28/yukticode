import React from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Loader } from 'lucide-react';

/**
 * AdminRoute — wraps any route that requires is_admin=true.
 * Redirects to / if not logged in or not an admin.
 */
const AdminRoute = ({ children }) => {
    const { user, loading } = useAuth();

    if (loading) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh', flexDirection: 'column', gap: '1rem', color: 'var(--text-secondary)' }}>
                <Loader size={32} className="spinner" style={{ animation: 'spin 1s linear infinite', color: 'var(--accent-primary)' }} />
                <p>Checking permissions...</p>
                <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
            </div>
        );
    }

    if (!user || !user.is_admin) {
        return <Navigate to="/" replace />;
    }

    return children;
};

export default AdminRoute;
