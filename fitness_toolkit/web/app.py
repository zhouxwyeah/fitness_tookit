"""Flask web application."""

from flask import Flask, jsonify, request, render_template
import logging

from fitness_toolkit.config import Config
from fitness_toolkit.database import init_db
from fitness_toolkit.services.account import AccountService
from fitness_toolkit.services.download import DownloadService
from fitness_toolkit.services.scheduler import SchedulerService

logger = logging.getLogger(__name__)


def create_app():
    """Create and configure Flask application."""
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Initialize database
    init_db()
    
    # Initialize services
    account_service = AccountService()
    download_service = DownloadService()
    scheduler_service = SchedulerService()
    
    # Start scheduler
    scheduler_service.start()
    
    @app.route('/')
    def index():
        """Home page."""
        return render_template('index.html')
    
    # API Routes
    @app.route('/api/accounts', methods=['GET'])
    def list_accounts():
        """List all accounts."""
        accounts = account_service.list_accounts()
        return jsonify({'accounts': accounts})
    
    @app.route('/api/accounts', methods=['POST'])
    def add_account():
        """Add or update an account."""
        data = request.json
        try:
            account_service.configure(
                data['platform'],
                data['email'],
                data['password']
            )
            return jsonify({'platform': data['platform'], 'message': 'Account saved successfully'}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    
    @app.route('/api/accounts/<platform>', methods=['DELETE'])
    def delete_account(platform):
        """Delete an account."""
        if account_service.remove_account(platform):
            return jsonify({'message': 'Account deleted successfully'})
        return jsonify({'error': 'Account not found'}), 404
    
    @app.route('/api/accounts/<platform>/verify', methods=['POST'])
    def verify_account(platform):
        """Verify account credentials."""
        success = account_service.verify(platform)
        return jsonify({'verified': success})
    
    @app.route('/api/downloads', methods=['POST'])
    def download():
        """Download activities."""
        from datetime import datetime
        data = request.json
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
            result = download_service.download(
                platform=data['account_id'],
                start_date=start_date,
                end_date=end_date,
                activity_type=data.get('activity_types'),
                file_format=data.get('format', 'tcx')
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    
    @app.route('/api/tasks', methods=['GET'])
    def list_tasks():
        """List all sync tasks."""
        tasks = scheduler_service.list_tasks()
        return jsonify({'tasks': tasks})
    
    @app.route('/api/tasks', methods=['POST'])
    def create_task():
        """Create a new sync task."""
        data = request.json
        try:
            task_id = scheduler_service.create_task(
                account_id=data['account_id'],
                name=data['name'],
                cron_expression=data['cron_expression'],
                file_format=data.get('format', 'tcx'),
                activity_types=data.get('activity_types')
            )
            return jsonify({'id': task_id, 'message': 'Task created successfully'}), 201
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    
    @app.route('/api/tasks/<int:task_id>/enable', methods=['POST'])
    def enable_task(task_id):
        """Enable a sync task."""
        if scheduler_service.enable_task(task_id):
            return jsonify({'message': 'Task enabled successfully'})
        return jsonify({'error': 'Task not found'}), 404
    
    @app.route('/api/tasks/<int:task_id>/disable', methods=['POST'])
    def disable_task(task_id):
        """Disable a sync task."""
        if scheduler_service.disable_task(task_id):
            return jsonify({'message': 'Task disabled successfully'})
        return jsonify({'error': 'Task not found'}), 404
    
    @app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
    def delete_task(task_id):
        """Delete a sync task."""
        if scheduler_service.delete_task(task_id):
            return jsonify({'message': 'Task deleted successfully'})
        return jsonify({'error': 'Task not found'}), 404
    
    return app


def main():
    """Run the Flask application."""
    app = create_app()
    app.run(host=Config.WEB_HOST, port=Config.WEB_PORT, debug=False)


if __name__ == '__main__':
    main()
