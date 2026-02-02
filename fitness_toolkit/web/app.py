import logging
import os

from flask import Flask, jsonify, request, render_template

from fitness_toolkit.config import Config
from fitness_toolkit.database import init_db, save_operation_history, get_operation_history, delete_operation_history
from fitness_toolkit.services.account import AccountService
from fitness_toolkit.services.download import DownloadService
try:
    from fitness_toolkit.services.scheduler import SchedulerService
except Exception:  # pragma: no cover
    SchedulerService = None
from fitness_toolkit.services.transfer import TransferService
from fitness_toolkit.services.transfer_settings import TransferSettingsService
from fitness_toolkit.services.transfer_queue import TransferQueueService
from fitness_toolkit.services.transfer_worker import get_worker, reset_worker

logger = logging.getLogger(__name__)


def create_app(testing: "bool | None" = None):
    """Create and configure Flask application.
    
    Args:
        testing: If True, skip starting background scheduler. If None, auto-detect
                 from TESTING environment variable.
    """
    app = Flask(__name__, 
                template_folder='templates',
                static_folder='static')
    
    # Determine testing mode
    if testing is None:
        testing = os.environ.get("TESTING", "").lower() in ("1", "true", "yes")
    app.config["TESTING"] = testing
    
    # Initialize database
    init_db()
    
    # Initialize services
    account_service = AccountService()
    download_service = DownloadService()
    if SchedulerService is None:
        scheduler_service = None
    else:
        try:
            scheduler_service = SchedulerService()
        except Exception:
            scheduler_service = None
    transfer_settings_service = TransferSettingsService()
    transfer_queue_service = TransferQueueService()
    
    # Start scheduler only if not testing
    if not testing and scheduler_service is not None:
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
            save_operation_history(
                operation_type='download',
                platform=data['account_id'],
                start_date=data['start_date'],
                end_date=data['end_date'],
                total=result.get('total', 0),
                success=result.get('downloaded', 0),
                skipped=result.get('skipped', 0),
                failed=result.get('failed', 0),
                details=result.get('details')
            )
            return jsonify(result)
        except Exception as e:
            return jsonify({'error': str(e)}), 400
    
    @app.route('/api/tasks', methods=['GET'])
    def list_tasks():
        """List all sync tasks."""
        if scheduler_service is None:
            return jsonify({'tasks': [], 'warning': 'scheduler_unavailable'}), 200
        tasks = scheduler_service.list_tasks()
        return jsonify({'tasks': tasks})
    
    @app.route('/api/tasks', methods=['POST'])
    def create_task():
        """Create a new sync task."""
        if scheduler_service is None:
            return jsonify({'error': 'scheduler_unavailable'}), 503
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
        if scheduler_service is None:
            return jsonify({'error': 'scheduler_unavailable'}), 503
        if scheduler_service.enable_task(task_id):
            return jsonify({'message': 'Task enabled successfully'})
        return jsonify({'error': 'Task not found'}), 404
    
    @app.route('/api/tasks/<int:task_id>/disable', methods=['POST'])
    def disable_task(task_id):
        """Disable a sync task."""
        if scheduler_service is None:
            return jsonify({'error': 'scheduler_unavailable'}), 503
        if scheduler_service.disable_task(task_id):
            return jsonify({'message': 'Task disabled successfully'})
        return jsonify({'error': 'Task not found'}), 404
    
    @app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
    def delete_task(task_id):
        """Delete a sync task."""
        if scheduler_service is None:
            return jsonify({'error': 'scheduler_unavailable'}), 503
        if scheduler_service.delete_task(task_id):
            return jsonify({'message': 'Task deleted successfully'})
        return jsonify({'error': 'Task not found'}), 404

    @app.route('/api/transfer', methods=['POST'])
    def transfer():
        from datetime import datetime
        data = request.json
        
        # Validate required fields
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        if 'start_date' not in data or 'end_date' not in data:
            return jsonify({'error': 'start_date and end_date are required'}), 400
        
        # Validate date format
        try:
            start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        # Validate date range
        if start_date > end_date:
            return jsonify({'error': 'start_date must be before or equal to end_date'}), 400
        
        # Validate sport_types
        sport_types = data.get('sport_types')
        if sport_types is not None and not isinstance(sport_types, list):
            return jsonify({'error': 'sport_types must be a list'}), 400
        
        transfer_service = TransferService()
        try:
            result = transfer_service.transfer(
                start_date=start_date,
                end_date=end_date,
                sport_types=sport_types
            )
            save_operation_history(
                operation_type='transfer',
                platform='coros->garmin',
                start_date=data['start_date'],
                end_date=data['end_date'],
                total=result.get('total', 0),
                success=result.get('uploaded', 0),
                skipped=result.get('skipped', 0),
                failed=len(result.get('failed', [])),
                details=result
            )
            return jsonify(result)
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    @app.route('/api/history/<operation_type>', methods=['GET'])
    def get_history(operation_type):
        """Get operation history by type (download or transfer)."""
        if operation_type not in ('download', 'transfer'):
            return jsonify({'error': 'Invalid operation type'}), 400
        limit = request.args.get('limit', 50, type=int)
        history = get_operation_history(operation_type=operation_type, limit=limit)
        return jsonify({'history': history})

    @app.route('/api/history/<operation_type>/<int:record_id>', methods=['DELETE'])
    def delete_history_record(operation_type, record_id):
        """Delete a single history record."""
        if operation_type not in ('download', 'transfer'):
            return jsonify({'error': 'Invalid operation type'}), 400
        if delete_operation_history(record_id):
            return jsonify({'message': 'Deleted successfully'})
        return jsonify({'error': 'Record not found'}), 404

    # Transfer settings API
    @app.route('/api/settings/transfer', methods=['GET'])
    def get_transfer_settings():
        """Get current transfer settings."""
        settings = transfer_settings_service.get_settings()
        return jsonify({'settings': settings, 'version': settings.get('version', 1)})

    @app.route('/api/settings/transfer', methods=['PUT'])
    def update_transfer_settings():
        """Update transfer settings."""
        data = request.json
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        settings = data.get('settings')
        if not settings or not isinstance(settings, dict):
            return jsonify({'error': 'settings object is required'}), 400
        
        normalized, errors = transfer_settings_service.save_settings(settings)
        if errors:
            return jsonify({
                'error': 'validation_error',
                'fields': errors
            }), 400
        
        return jsonify({'settings': normalized, 'version': normalized.get('version', 1)})

    @app.route('/api/settings/transfer/preview', methods=['POST'])
    def preview_transfer_settings():
        """Preview rendered metadata for an activity."""
        data = request.json
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        activity = data.get('activity')
        if not activity or not isinstance(activity, dict):
            return jsonify({'error': 'activity object is required'}), 400
        
        # Optional settings override
        settings = data.get('settings')
        
        result = transfer_settings_service.preview(activity, settings)
        return jsonify(result)

    @app.route('/api/garmin/gear', methods=['GET'])
    def get_garmin_gear():
        """Get Garmin gear list (best-effort)."""
        try:
            garmin_client = account_service.get_client('garmin')
            if not garmin_client:
                return jsonify({
                    'gear': [],
                    'warning': 'Garmin account not configured or authentication failed'
                })
            
            # Try to fetch gear from Garmin
            # Note: garmin API for gear is /gear-service/gear/filterGear
            try:
                import garth
                gear_data = garth.connectapi('/gear-service/gear/filterGear', params={'start': 0, 'limit': 100})
                if gear_data and isinstance(gear_data, list):
                    gear_list = [
                        {
                            'id': str(g.get('uuid', g.get('gearPk', ''))),
                            'name': g.get('displayName', g.get('customMakeModel', 'Unknown')),
                            'type': g.get('gearTypeName', ''),
                        }
                        for g in gear_data
                    ]
                    return jsonify({'gear': gear_list})
                return jsonify({'gear': [], 'warning': 'No gear found'})
            except Exception as e:
                logger.warning(f"Failed to fetch Garmin gear: {e}")
                return jsonify({'gear': [], 'warning': f'Failed to fetch gear: {str(e)}'})
        except Exception as e:
            logger.error(f"Failed to get Garmin gear: {e}")
            return jsonify({'gear': [], 'warning': str(e)})

    # Transfer job queue APIs
    @app.route('/api/transfer/jobs', methods=['POST'])
    def create_transfer_job():
        """Create a new transfer job.
        
        Fetches activities from COROS for the date range and creates a job with items.
        """
        from datetime import datetime as dt
        data = request.json
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        # Validate dates
        if 'start_date' not in data or 'end_date' not in data:
            return jsonify({'error': 'start_date and end_date are required'}), 400
        
        try:
            start_date = dt.strptime(data['start_date'], '%Y-%m-%d').date()
            end_date = dt.strptime(data['end_date'], '%Y-%m-%d').date()
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        
        if start_date > end_date:
            return jsonify({'error': 'start_date must be before or equal to end_date'}), 400
        
        sport_types = data.get('sport_types')
        if sport_types is not None and not isinstance(sport_types, list):
            return jsonify({'error': 'sport_types must be a list'}), 400
        
        # Get COROS client
        coros_client = account_service.get_client('coros')
        if not coros_client:
            return jsonify({'error': 'COROS account not configured or authentication failed'}), 400
        
        # Verify Garmin is also configured (needed later for actual transfer)
        garmin_client = account_service.get_client('garmin')
        if not garmin_client:
            return jsonify({'error': 'Garmin account not configured or authentication failed'}), 400
        
        try:
            # Fetch activities from COROS
            activities = coros_client.get_activities(start_date, end_date, sport_types)
            
            if not activities:
                return jsonify({
                    'job_id': None,
                    'message': 'No activities found for the specified date range',
                    'total_items': 0
                })
            
            # Create job with items
            job_id = transfer_queue_service.create_job(
                start_date=data['start_date'],
                end_date=data['end_date'],
                activities=activities,
                sport_types=sport_types,
            )
            
            return jsonify({
                'job_id': job_id,
                'message': f'Created transfer job with {len(activities)} activities',
                'total_items': len(activities)
            }), 201
            
        except Exception as e:
            logger.error(f"Failed to create transfer job: {e}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/transfer/jobs', methods=['GET'])
    def list_transfer_jobs():
        """List recent transfer jobs."""
        limit = request.args.get('limit', 20, type=int)
        if limit < 1 or limit > 100:
            limit = 20
        
        jobs = transfer_queue_service.list_jobs(limit=limit)
        return jsonify({'jobs': jobs})

    @app.route('/api/transfer/jobs/<int:job_id>', methods=['GET'])
    def get_transfer_job(job_id):
        """Get a transfer job with its items."""
        job = transfer_queue_service.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404
        
        # Get items (optionally filtered by status)
        status_filter = request.args.get('status')
        items_limit = request.args.get('items_limit', 100, type=int)
        
        items = transfer_queue_service.get_job_items(
            job_id,
            status=status_filter,
            limit=items_limit
        )
        
        return jsonify({
            'job': job,
            'items': items
        })

    @app.route('/api/transfer/jobs/<int:job_id>', methods=['DELETE'])
    def delete_transfer_job(job_id):
        """Delete a transfer job and all its items."""
        if transfer_queue_service.delete_job(job_id):
            return jsonify({'message': 'Job deleted successfully'})
        return jsonify({'error': 'Job not found'}), 404

    @app.route('/api/transfer/jobs/<int:job_id>/cancel', methods=['POST'])
    def cancel_transfer_job(job_id):
        """Cancel a transfer job."""
        if transfer_queue_service.cancel_job(job_id):
            # Refresh job data
            job = transfer_queue_service.get_job(job_id)
            return jsonify({
                'message': 'Job cancelled successfully',
                'job': job
            })
        return jsonify({'error': 'Job not found or cannot be cancelled'}), 400

    @app.route('/api/transfer/jobs/<int:job_id>/start', methods=['POST'])
    def start_transfer_job(job_id):
        """Start processing a transfer job."""
        job = transfer_queue_service.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        worker = get_worker()
        if worker.process_job(job_id):
            return jsonify({
                'message': 'Job started',
                'job_id': job_id,
                'worker_running': worker.is_running
            })
        return jsonify({'error': 'Job cannot be started (check status)'}), 400

    # Worker control APIs
    @app.route('/api/transfer/worker/status', methods=['GET'])
    def get_worker_status():
        """Get worker status."""
        worker = get_worker()
        return jsonify({
            'running': worker.is_running,
            'paused': worker.is_paused,
            'current_job_id': worker.current_job_id
        })

    @app.route('/api/transfer/worker/pause', methods=['POST'])
    def pause_worker():
        """Pause the worker."""
        worker = get_worker()
        if worker.pause():
            return jsonify({
                'message': 'Worker paused',
                'paused': True,
                'current_job_id': worker.current_job_id
            })
        return jsonify({'error': 'Worker is not running'}), 400

    @app.route('/api/transfer/worker/resume', methods=['POST'])
    def resume_worker():
        """Resume the worker."""
        worker = get_worker()
        if worker.resume():
            return jsonify({
                'message': 'Worker resumed',
                'paused': False,
                'current_job_id': worker.current_job_id
            })
        return jsonify({'error': 'Worker is not running'}), 400

    @app.route('/api/transfer/worker/stop', methods=['POST'])
    def stop_worker():
        """Stop the worker."""
        worker = get_worker()
        if worker.stop(wait=False):
            return jsonify({'message': 'Worker stopped', 'running': False})
        return jsonify({'error': 'Failed to stop worker'}), 500

    # Rerun metadata for failed items
    @app.route('/api/transfer/jobs/<int:job_id>/rerun-metadata', methods=['POST'])
    def rerun_metadata(job_id):
        """Rerun metadata application for items with metadata_status='failed'."""
        from fitness_toolkit.services.transfer_queue import METADATA_STATUS_FAILED
        from fitness_toolkit.services.transfer_worker import TransferWorker

        job = transfer_queue_service.get_job(job_id)
        if not job:
            return jsonify({'error': 'Job not found'}), 404

        # Get items with failed metadata
        items = transfer_queue_service.get_job_items(job_id, limit=1000)
        failed_items = [i for i in items if i.get('metadata_status') == METADATA_STATUS_FAILED]

        if not failed_items:
            return jsonify({
                'message': 'No items with failed metadata',
                'rerun_count': 0
            })

        # Get Garmin client
        garmin_client = account_service.get_client('garmin')
        if not garmin_client:
            return jsonify({'error': 'Garmin account not configured'}), 400

        # Create a temporary worker to rerun metadata
        temp_worker = TransferWorker(
            queue_service=transfer_queue_service,
            account_service=account_service,
            settings_service=transfer_settings_service,
        )

        settings = job.get('settings_snapshot', {})
        rerun_count = 0
        errors = []

        for item in failed_items:
            garmin_id = item.get('garmin_id')
            if not garmin_id or garmin_id == 'duplicate':
                continue

            try:
                metadata_status, metadata_error = temp_worker._apply_metadata(
                    garmin_client, garmin_id, item, settings
                )
                transfer_queue_service.update_item_status(
                    item['id'],
                    item['status'],  # Keep original status
                    metadata_status=metadata_status,
                    metadata_error=metadata_error,
                )
                if metadata_status != METADATA_STATUS_FAILED:
                    rerun_count += 1
                else:
                    errors.append(f"Item {item['id']}: {metadata_error}")
            except Exception as e:
                errors.append(f"Item {item['id']}: {str(e)}")

        return jsonify({
            'message': f'Reran metadata for {rerun_count} items',
            'rerun_count': rerun_count,
            'total_failed': len(failed_items),
            'errors': errors[:10] if errors else []  # Limit errors returned
        })

    return app


def main():
    """Run the Flask application."""
    app = create_app()
    app.run(host=Config.WEB_HOST, port=Config.WEB_PORT, debug=False)


if __name__ == '__main__':
    main()
