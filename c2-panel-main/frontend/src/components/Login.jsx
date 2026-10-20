import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import socket from '../services/socket';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');

    try {
      const response = await api.post('/api/auth/login', {
        username,
        password
      });

      localStorage.setItem('token', response.data.token);
      localStorage.setItem('username', response.data.username);
      localStorage.setItem('role', response.data.role);

      socket.connect(response.data.token);
      navigate('/');
    } catch (err) {
      setError(err.response?.data?.error || 'Login failed');
    }
  };

  return (
    <div className="login-shell">
      <aside className="login-aside">
        <div className="brand-mark">
          <span className="brand-dot"></span>
          <span>C2 / Control</span>
        </div>

        <div className="login-hero">
          <h2>Quiet, precise control over every connected agent.</h2>
          <p>Monitor sessions, stream desktops, manage operators — all from one calm, monochrome surface designed to stay out of the way.</p>
        </div>

        <div className="login-meta">
          <span><i></i> Secure session</span>
          <span>v2.0</span>
          <span>Build · stable</span>
        </div>
      </aside>

      <main className="login-main">
        <div className="login-container">
          <p className="login-eyebrow">control panel access</p>
          <h1 className="login-title">Sign in</h1>
          <p className="login-subtitle">Enter your operator credentials to continue.</p>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <form onSubmit={handleLogin}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input
                type="text"
                className="form-input"
                placeholder="Enter username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="form-group">
              <label className="form-label">Password</label>
              <input
                type="password"
                className="form-input"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </div>

            <button type="submit" className="login-button">
              Sign In
            </button>
          </form>

          <div className="login-footer">
            Authorized access only
          </div>
        </div>
      </main>
    </div>
  );
}
