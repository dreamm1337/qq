import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, createTheme, CssBaseline } from '@mui/material';
import Login from './components/Login';
import AgentList from './components/AgentList';
import AgentDetail from './components/AgentDetail';
import UserManagement from './components/UserManagement';
import StreamWindow from './components/StreamWindow';
import WebcamStreamWindow from './components/WebcamStreamWindow';
import socket from './services/socket';
import './index.css';
import './techno-noir.css';

const darkTheme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#d7dadc',
    },
    secondary: {
      main: '#34d399',
    },
    background: {
      default: '#060707',
      paper: '#111314',
    },
    text: {
      primary: '#f5f7f8',
      secondary: '#8f979c',
    },
  },
  shape: {
    borderRadius: 18,
  },
  typography: {
    fontFamily: '"Bahnschrift", "Segoe UI", sans-serif',
  },
});

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" />;
}

function App() {
  // Подключаем socket синхронно до рендера компонентов
  const token = localStorage.getItem('token');
  if (token) {
    // Проверяем нужно ли переподключиться
    if (!socket.socket || !socket.socket.connected) {
      console.log('[App] Auto-connecting socket with existing token');
      socket.connect(token);
    }
  }

  return (
    <ThemeProvider theme={darkTheme}>
      <CssBaseline />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/"
            element={
              <PrivateRoute>
                <AgentList />
              </PrivateRoute>
            }
          />
          <Route
            path="/agent/:id"
            element={
              <PrivateRoute>
                <AgentDetail />
              </PrivateRoute>
            }
          />
          <Route
            path="/users"
            element={
              <PrivateRoute>
                <UserManagement />
              </PrivateRoute>
            }
          />
          <Route
            path="/stream"
            element={
              <PrivateRoute>
                <StreamWindow />
              </PrivateRoute>
            }
          />
          <Route
            path="/webcam-stream"
            element={
              <PrivateRoute>
                <WebcamStreamWindow />
              </PrivateRoute>
            }
          />
        </Routes>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
