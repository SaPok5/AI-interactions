/**
 * Authentication Module
 * Handles user authentication with the backend auth service
 */

class AuthManager {
    constructor() {
        this.baseUrl = 'http://localhost:8080/auth';
        this.token = localStorage.getItem('auth_token');
        this.user = JSON.parse(localStorage.getItem('user_data') || 'null');
        this.refreshTimer = null;
    }

    /**
     * Initialize authentication
     */
    async init() {
        if (this.token) {
            try {
                const isValid = await this.validateToken();
                if (isValid) {
                    return { authenticated: true, user: this.user };
                }
            } catch (error) {
                console.warn('Token validation failed:', error);
                this.clearAuth();
            }
        }
        return { authenticated: false };
    }

    /**
     * Login user
     */
    async login(email, password) {
        try {
            const response = await fetch(`${this.baseUrl}/signin`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email, password })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Login failed');
            }

            // Store auth data
            this.token = data.token;
            this.user = data.user;
            
            localStorage.setItem('auth_token', this.token);
            localStorage.setItem('user_data', JSON.stringify(this.user));

            // Set up token refresh
            this.setupTokenRefresh();

            return { success: true, user: this.user };
        } catch (error) {
            console.error('Login error:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Register new user
     */
    async register(name, email, password) {
        try {
            const response = await fetch(`${this.baseUrl}/signup`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ 
                    name, 
                    email, 
                    password 
                })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || 'Registration failed');
            }

            // Store auth data directly from signup response
            this.token = data.token;
            this.user = data.user;
            
            localStorage.setItem('auth_token', this.token);
            localStorage.setItem('user_data', JSON.stringify(this.user));

            // Set up token refresh
            this.setupTokenRefresh();

            return { success: true, user: this.user };
        } catch (error) {
            console.error('Registration error:', error);
            return { success: false, error: error.message };
        }
    }

    /**
     * Logout user
     */
    async logout() {
        try {
            if (this.token) {
                await fetch(`${this.baseUrl}/logout`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.token}`,
                        'Content-Type': 'application/json',
                    }
                });
            }
        } catch (error) {
            console.warn('Logout request failed:', error);
        } finally {
            this.clearAuth();
        }
    }

    /**
     * Validate current token
     */
    async validateToken() {
        if (!this.token) return false;

        try {
            const response = await fetch(`${this.baseUrl}/me`, {
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                }
            });

            if (response.ok) {
                const userData = await response.json();
                this.user = userData;
                localStorage.setItem('user_data', JSON.stringify(this.user));
                return true;
            }
            return false;
        } catch (error) {
            console.error('Token validation error:', error);
            return false;
        }
    }

    /**
     * Refresh authentication token
     */
    async refreshToken() {
        try {
            const response = await fetch(`${this.baseUrl}/refresh`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.token}`,
                    'Content-Type': 'application/json',
                }
            });

            if (response.ok) {
                const data = await response.json();
                this.token = data.access_token;
                localStorage.setItem('auth_token', this.token);
                return true;
            }
            return false;
        } catch (error) {
            console.error('Token refresh error:', error);
            return false;
        }
    }

    /**
     * Setup automatic token refresh
     */
    setupTokenRefresh() {
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
        }

        // Refresh token every 50 minutes (tokens expire in 60 minutes)
        this.refreshTimer = setInterval(async () => {
            const success = await this.refreshToken();
            if (!success) {
                console.warn('Token refresh failed, logging out');
                this.clearAuth();
                window.location.reload();
            }
        }, 50 * 60 * 1000);
    }

    /**
     * Clear authentication data
     */
    clearAuth() {
        this.token = null;
        this.user = null;
        localStorage.removeItem('auth_token');
        localStorage.removeItem('user_data');
        
        if (this.refreshTimer) {
            clearInterval(this.refreshTimer);
            this.refreshTimer = null;
        }
    }

    /**
     * Get authorization header
     */
    getAuthHeader() {
        return this.token ? { 'Authorization': `Bearer ${this.token}` } : {};
    }

    /**
     * Check if user is authenticated
     */
    isAuthenticated() {
        return !!this.token && !!this.user;
    }

    /**
     * Get current user
     */
    getCurrentUser() {
        return this.user;
    }

    /**
     * Get auth token
     */
    getToken() {
        return this.token;
    }
}

// Export for use in other modules
window.AuthManager = AuthManager;
