import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  TextField,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Snackbar
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Add as AddIcon,
  Edit as EditIcon,
  Delete as DeleteIcon,
  People as PeopleIcon
} from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import BackgroundFx from './BackgroundFx';

export default function UserManagement() {
  const navigate = useNavigate();
  const [users, setUsers] = useState([]);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);

  useEffect(() => {
    if (success) {
      const timer = setTimeout(() => setSuccess(''), 3000);
      return () => clearTimeout(timer);
    }
  }, [success]);

  // Modal states
  const [createModal, setCreateModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [deleteModal, setDeleteModal] = useState(false);

  // Form states
  const [newUsername, setNewUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [newRole, setNewRole] = useState('user');

  const [editUser, setEditUser] = useState(null);
  const [editPassword, setEditPassword] = useState('');
  const [editRole, setEditRole] = useState('user');

  const [deleteUser, setDeleteUser] = useState(null);

  useEffect(() => {
    const userRole = localStorage.getItem('role');
    if (userRole !== 'admin') {
      navigate('/');
      return;
    }
    loadUsers();
  }, [navigate]);

  const loadUsers = async () => {
    try {
      const response = await api.get('/api/users');
      setUsers(response.data);
    } catch (err) {
      setError('Failed to load users');
    }
  };

  const handleCreateUser = async () => {
    if (!newUsername || !newPassword) {
      setError('Username and password are required');
      return;
    }

    try {
      setError('');
      await api.post('/api/users', {
        username: newUsername,
        password: newPassword,
        role: newRole
      });
      setSuccess('User created successfully');
      setCreateModal(false);
      setNewUsername('');
      setNewPassword('');
      setNewRole('user');
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to create user');
    }
  };

  const handleEditUser = async () => {
    if (!editUser) return;

    try {
      setError('');
      const data = { role: editRole };
      if (editPassword) {
        data.password = editPassword;
      }

      await api.put(`/api/users/${editUser.id}`, data);
      setSuccess('User updated successfully');
      setEditModal(false);
      setEditUser(null);
      setEditPassword('');
      setEditRole('user');
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to update user');
    }
  };

  const handleDeleteUser = async () => {
    if (!deleteUser) return;

    try {
      setError('');
      await api.delete(`/api/users/${deleteUser.id}`);
      setSuccess('User deleted successfully');
      setDeleteModal(false);
      setDeleteUser(null);
      loadUsers();
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to delete user');
    }
  };

  const openEditModal = (user) => {
    setEditUser(user);
    setEditRole(user.role);
    setEditPassword('');
    setEditModal(true);
  };

  const openDeleteModal = (user) => {
    setDeleteUser(user);
    setDeleteModal(true);
  };

  return (
    <Box className="dashboard-shell">
      <BackgroundFx />
      <Box className="dashboard-noise" />
      <Box className="dashboard-orbit dashboard-orbit-left" />
      <Box className="dashboard-orbit dashboard-orbit-right" />

      <Box className="dashboard-page">
        <Box className="dashboard-panel dashboard-header reveal reveal-1">
          <Box>
            <Button
              startIcon={<ArrowBackIcon />}
              onClick={() => navigate('/')}
              sx={{
                color: 'var(--text-secondary)',
                mb: 2,
                '&:hover': { color: 'var(--accent)' }
              }}
            >
              Back to agents
            </Button>
            <Typography className="eyebrow">
              administration / access control
            </Typography>
            <Box className="dashboard-title-row">
              <Box className="dashboard-logo">
                <PeopleIcon fontSize="small" />
              </Box>
              <Box>
                <Typography variant="h3" className="dashboard-title">
                  USER MANAGEMENT
                </Typography>
                <Typography className="dashboard-subtitle">
                  manage user accounts and permissions
                </Typography>
              </Box>
            </Box>
          </Box>

          <Box className="dashboard-header-meta">
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={() => setCreateModal(true)}
              className="action-btn"
            >
              Create User
            </Button>
          </Box>
        </Box>

        <Snackbar
          open={!!error}
          autoHideDuration={5000}
          onClose={() => setError('')}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert severity="error" onClose={() => setError('')} sx={{ width: '100%' }}>
            {error}
          </Alert>
        </Snackbar>

        <Snackbar
          open={!!success}
          autoHideDuration={3000}
          onClose={() => setSuccess('')}
          anchorOrigin={{ vertical: 'top', horizontal: 'center' }}
        >
          <Alert
            severity="success"
            onClose={() => setSuccess('')}
            sx={{
              width: '100%',
              bgcolor: 'rgba(76, 175, 80, 0.15) !important',
              color: '#4caf50 !important',
              border: '1px solid rgba(76, 175, 80, 0.3)',
              backdropFilter: 'blur(10px)',
              '& .MuiAlert-icon': {
                color: '#4caf50 !important'
              },
              '& .MuiAlert-message': {
                color: '#4caf50 !important'
              }
            }}
          >
            {success}
          </Alert>
        </Snackbar>

        <Box className="section-head reveal reveal-2">
          <Typography className="section-title">User Accounts</Typography>
          <Typography className="section-note">
            {users.length} registered users
          </Typography>
        </Box>

        <TableContainer className="dashboard-panel table-shell reveal reveal-3">
          <Table>
            <TableBody>
              <TableRow className="table-header-row">
                <TableCell>ID</TableCell>
                <TableCell>Username</TableCell>
                <TableCell>Role</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
              {users.map((user, index) => (
                <TableRow
                  key={user.id}
                  hover
                  className="agent-row"
                  sx={{ animationDelay: `${index * 45}ms` }}
                >
                  <TableCell>#{String(user.id).padStart(3, '0')}</TableCell>
                  <TableCell>
                    <Typography className="host-name">{user.username}</Typography>
                  </TableCell>
                  <TableCell>
                    <Box
                      className="status-badge"
                      sx={{
                        background: user.role === 'admin'
                          ? 'rgba(255, 152, 0, 0.08)'
                          : 'rgba(49, 211, 139, 0.08)',
                        borderColor: user.role === 'admin'
                          ? 'rgba(255, 152, 0, 0.16)'
                          : 'rgba(49, 211, 139, 0.16)',
                        color: user.role === 'admin' ? '#ffb74d' : '#ddf8ea'
                      }}
                    >
                      {user.role}
                    </Box>
                  </TableCell>
                  <TableCell>
                    {user.created_at
                      ? new Date(user.created_at).toLocaleDateString()
                      : 'Unknown'}
                  </TableCell>
                  <TableCell align="right">
                    <Box className="action-group">
                      <IconButton
                        size="small"
                        className="action-button"
                        onClick={() => openEditModal(user)}
                      >
                        <EditIcon />
                      </IconButton>
                      <IconButton
                        size="small"
                        className="action-button"
                        onClick={() => openDeleteModal(user)}
                        disabled={user.username === localStorage.getItem('username')}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </Box>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>

        {users.length === 0 && (
          <Box className="dashboard-panel empty-state reveal reveal-3">
            <Typography variant="h6" color="text.secondary">
              No users found
            </Typography>
            <Typography className="empty-state-note">
              Create your first user account to get started.
            </Typography>
          </Box>
        )}
      </Box>

      {/* Create User Modal */}
      <Dialog
        open={createModal}
        onClose={() => setCreateModal(false)}
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Create New User</Typography>
        </DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Username"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            className="input-field"
            sx={{ mt: 2, mb: 2 }}
          />
          <TextField
            fullWidth
            type="password"
            label="Password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="input-field"
            sx={{ mb: 2 }}
          />
          <FormControl fullWidth>
            <InputLabel>Role</InputLabel>
            <Select
              value={newRole}
              onChange={(e) => setNewRole(e.target.value)}
              label="Role"
            >
              <MenuItem value="admin">Admin</MenuItem>
              <MenuItem value="user">User</MenuItem>
              <MenuItem value="viewer">Viewer</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCreateModal(false)}>Cancel</Button>
          <Button onClick={handleCreateUser} variant="contained" className="action-btn">
            Create
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit User Modal */}
      <Dialog
        open={editModal}
        onClose={() => setEditModal(false)}
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">
            Edit User: {editUser?.username}
          </Typography>
        </DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            type="password"
            label="New Password (leave empty to keep current)"
            value={editPassword}
            onChange={(e) => setEditPassword(e.target.value)}
            className="input-field"
            sx={{ mt: 2, mb: 2 }}
          />
          <FormControl fullWidth>
            <InputLabel>Role</InputLabel>
            <Select
              value={editRole}
              onChange={(e) => setEditRole(e.target.value)}
              label="Role"
            >
              <MenuItem value="admin">Admin</MenuItem>
              <MenuItem value="user">User</MenuItem>
              <MenuItem value="viewer">Viewer</MenuItem>
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditModal(false)}>Cancel</Button>
          <Button onClick={handleEditUser} variant="contained" className="action-btn">
            Save
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete User Modal */}
      <Dialog
        open={deleteModal}
        onClose={() => setDeleteModal(false)}
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Delete User</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete user <strong>{deleteUser?.username}</strong>?
            This action cannot be undone.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteModal(false)}>Cancel</Button>
          <Button
            onClick={handleDeleteUser}
            variant="contained"
            className="action-btn danger"
            sx={{
              background: 'linear-gradient(135deg, var(--danger) 0%, #cc0000 100%) !important'
            }}
          >
            Delete
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
