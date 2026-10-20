import React, { useState, useEffect } from 'react';
import {
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  IconButton,
  Typography,
  TextField,
  InputAdornment,
  Button
} from '@mui/material';
import {
  Language as LanguageIcon,
  Search as SearchIcon,
  Terminal as TerminalIcon,
  Folder as FolderIcon,
  Screenshot as ScreenshotIcon,
  Sensors as SensorsIcon,
  Shield as ShieldIcon,
  Hub as HubIcon,
  WifiTethering as WifiTetheringIcon,
  People as PeopleIcon
} from '@mui/icons-material';
import { formatDistanceToNow } from 'date-fns';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import socket from '../services/socket';
import BackgroundFx from './BackgroundFx';

export default function AgentList() {
  const [agents, setAgents] = useState([]);
  const [search, setSearch] = useState('');
  const navigate = useNavigate();
  const userRole = localStorage.getItem('role');

  useEffect(() => {
    loadAgents();

    socket.on('agent_online', handleAgentOnline);
    socket.on('agent_offline', handleAgentOffline);
    socket.on('agent_updated', handleAgentUpdated);

    // Update timestamps every minute
    const interval = setInterval(() => {
      setAgents((prev) => [...prev]);
    }, 60000);

    return () => {
      socket.off('agent_online', handleAgentOnline);
      socket.off('agent_offline', handleAgentOffline);
      socket.off('agent_updated', handleAgentUpdated);
      clearInterval(interval);
    };
  }, []);

  const loadAgents = async () => {
    try {
      const response = await api.get('/api/agents');
      setAgents(response.data);
    } catch (error) {
      console.error('Failed to load agents:', error);
    }
  };

  const handleAgentOnline = (data) => {
    console.log('[AgentList] agent_online event:', data);
    setAgents((prev) => {
      const existing = prev.find((agent) => agent.id === data.id);
      if (existing) {
        return prev.map((agent) => (
          agent.id === data.id ? { ...agent, status: 'online', last_seen: data.last_seen } : agent
        ));
      }
      return [...prev, { ...data, status: 'online' }];
    });
  };

  const handleAgentOffline = (data) => {
    console.log('[AgentList] agent_offline event:', data);
    setAgents((prev) => prev.map((agent) => (
      agent.id === data.id ? { ...agent, status: 'offline', last_seen: data.last_seen } : agent
    )));
  };

  const handleAgentUpdated = (data) => {
    console.log('[AgentList] agent_updated event:', data);
    setAgents((prev) => prev.map((agent) => (
      agent.id === data.id ? { ...agent, last_seen: data.last_seen, status: data.status } : agent
    )));
  };

  const filteredAgents = agents.filter((agent) => (
    agent.hostname.toLowerCase().includes(search.toLowerCase()) ||
    agent.ip.includes(search) ||
    agent.username?.toLowerCase().includes(search.toLowerCase())
  ));

  const onlineAgents = agents.filter((agent) => agent.status === 'online');
  const offlineAgents = agents.filter((agent) => agent.status !== 'online');
  const recentAgent = [...agents]
    .filter((agent) => agent.last_seen)
    .sort((a, b) => new Date(b.last_seen) - new Date(a.last_seen))[0];

  const heroStats = [
    {
      label: 'Online',
      value: onlineAgents.length,
      note: `${agents.length} total nodes`,
      icon: <WifiTetheringIcon />,
    },
    {
      label: 'Offline',
      value: offlineAgents.length,
      note: offlineAgents.length ? 'needs attention' : 'all clear',
      icon: <ShieldIcon />,
    },
    {
      label: 'Operators',
      value: new Set(agents.map((agent) => agent.username).filter(Boolean)).size,
      note: 'active identities',
      icon: <HubIcon />,
    },
    {
      label: 'Freshest beacon',
      value: recentAgent ? recentAgent.hostname : 'No data',
      note: recentAgent?.last_seen
        ? formatDistanceToNow(new Date(recentAgent.last_seen), { addSuffix: true })
        : 'awaiting contact',
      icon: <SensorsIcon />,
    },
  ];

  return (
    <Box className="dashboard-shell">
      <BackgroundFx />
      <Box className="dashboard-noise" />
      <Box className="dashboard-orbit dashboard-orbit-left" />
      <Box className="dashboard-orbit dashboard-orbit-right" />

      <Box className="dashboard-page">
        <Box className="dashboard-panel dashboard-header reveal reveal-1">
          <Box>
            <Typography className="eyebrow">
              command monitoring / control room
            </Typography>
            <Box className="dashboard-title-row">
              <Box className="dashboard-logo">
                <LanguageIcon fontSize="small" />
              </Box>
              <Box>
                <Typography variant="h3" className="dashboard-title">
                  CONTROL PANEL
                </Typography>
              </Box>
            </Box>
          </Box>

          <Box className="dashboard-header-meta">
            <Box className="status-pill">
              <span className="status-dot" />
              system online
            </Box>
            <Button
              variant="outlined"
              onClick={() => {
                localStorage.clear();
                socket.disconnect();
                navigate('/login');
              }}
              className="btn-outlined btn-danger"
            >
              Logout
            </Button>
            <Typography className="dashboard-timestamp">
              Updated {new Date().toLocaleString()}
            </Typography>
          </Box>
        </Box>

        <Box className="dashboard-toolbar reveal reveal-2">
          <div className="command-search">
            <SearchIcon />
            <input
              type="text"
              placeholder="Search hostname, IP, username..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <Typography className="toolbar-caption">
            {filteredAgents.length} entries in current view
          </Typography>
        </Box>

        <Box className="hero-grid reveal reveal-3">
          {heroStats.map((stat, index) => (
            <Box
              key={stat.label}
              className="dashboard-panel hero-card"
            >
              <Box className="hero-card-top">
                <Box className="hero-card-icon">{stat.icon}</Box>
                <Typography className="hero-card-label">{stat.label}</Typography>
              </Box>
              <Typography className="hero-card-value">{stat.value}</Typography>
              <Typography className="hero-card-note">{stat.note}</Typography>
            </Box>
          ))}
        </Box>

        <Box className="section-head reveal reveal-4">
          <Typography className="section-title">Agent matrix</Typography>
          <Typography className="section-note">
            live registry of connected and dormant endpoints
          </Typography>
        </Box>

        <TableContainer className="dashboard-panel table-shell reveal reveal-5">
          <Table>
            <TableBody>
              <TableRow className="table-header-row">
                <TableCell>Status</TableCell>
                <TableCell>Host</TableCell>
                <TableCell>IP</TableCell>
                <TableCell>OS</TableCell>
                <TableCell>Operator</TableCell>
                <TableCell>Last seen</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
              {filteredAgents.map((agent, index) => (
                <TableRow
                  key={agent.id}
                  hover
                  className="agent-row"
                  onClick={() => navigate(`/agent/${agent.id}`)}
                >
                  <TableCell>
                    <Box className={`status-badge ${agent.status === 'online' ? 'is-online' : 'is-offline'}`}>
                      <span className="status-badge-dot" />
                      {agent.status}
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Box className="host-cell">
                      <Box className="host-mark">
                        <SensorsIcon fontSize="small" />
                      </Box>
                      <Box>
                        <Typography className="host-name">{agent.hostname}</Typography>
                        <Typography className="host-meta">node #{String(agent.id).padStart(3, '0')}</Typography>
                      </Box>
                    </Box>
                  </TableCell>
                  <TableCell>{agent.ip}</TableCell>
                  <TableCell>{agent.os || 'Unknown'}</TableCell>
                  <TableCell>{agent.username || 'Unknown'}</TableCell>
                  <TableCell>
                    {agent.last_seen
                      ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })
                      : 'Never'}
                  </TableCell>
                  <TableCell align="right">
                    <Box className="action-group" onClick={(e) => e.stopPropagation()}>
                      <IconButton
                        size="small"
                        className="action-button"
                        onClick={() => navigate(`/agent/${agent.id}`)}
                      >
                        <TerminalIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        className="action-button"
                        onClick={() => navigate(`/agent/${agent.id}`)}
                      >
                        <FolderIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        className="action-button"
                        onClick={() => navigate(`/agent/${agent.id}`)}
                      >
                        <ScreenshotIcon />
                      </IconButton>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {filteredAgents.length === 0 && (
          <Box className="dashboard-panel empty-state reveal reveal-5">
            <Typography variant="h6" color="text.secondary">
              No agents match the current filter
            </Typography>
            <Typography className="empty-state-note">
              Try another hostname, IP, or operator name.
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
