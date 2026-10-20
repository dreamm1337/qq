from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

class Agent(db.Model):
    __tablename__ = 'agents'

    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(255), nullable=False)
    ip = db.Column(db.String(45), nullable=False)
    os = db.Column(db.String(255))
    username = db.Column(db.String(255))
    status = db.Column(db.String(20), default='offline')
    last_seen = db.Column(db.DateTime, default=datetime.utcnow)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow)

    commands = db.relationship('Command', backref='agent', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Agent {self.hostname}@{self.ip}>'

class Command(db.Model):
    __tablename__ = 'commands'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    command = db.Column(db.Text, nullable=False)
    result = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    executed_at = db.Column(db.DateTime)
    user = db.relationship("User", backref="commands")

    def __repr__(self):
        return f'<Command {self.id}: {self.command[:50]}>'

class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='operator')
    is_banned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

class BannedIP(db.Model):
    __tablename__ = 'banned_ips'

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False)
    reason = db.Column(db.String(255))
    banned_by = db.Column(db.String(80))
    banned_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<BannedIP {self.ip_address}>'

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    username = db.Column(db.String(80), nullable=True)
    action = db.Column(db.String(100), nullable=False)
    agent_id = db.Column(db.Integer, nullable=True)
    command = db.Column(db.String(255), nullable=True)
    details = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<ActivityLog {self.action} by {self.username}>'

class BlockedApp(db.Model):
    __tablename__ = 'blocked_apps'

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    app_name = db.Column(db.String(255), nullable=False)
    blocked_at = db.Column(db.DateTime, default=datetime.utcnow)
    blocked_by = db.Column(db.String(80))

    def __repr__(self):
        return f'<BlockedApp {self.app_name} on Agent {self.agent_id}>'

class AgentBuild(db.Model):
    __tablename__ = 'agent_builds'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=True)
    original_filename = db.Column(db.String(255), nullable=True)
    file_path = db.Column(db.String(512), nullable=True)
    file_size = db.Column(db.Integer)
    download_url = db.Column(db.String(512))
    status = db.Column(db.String(50), default='pending')  # pending, compiling, ready, failed
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))

    def __repr__(self):
        return f'<AgentBuild {self.filename}>'
