import click
from datetime import datetime
from getpass import getpass
from pathlib import Path

from fitness_toolkit.config import Config
from fitness_toolkit.database import init_db
from fitness_toolkit.services.account import AccountService
from fitness_toolkit.services.download import DownloadService
from fitness_toolkit.services.transfer import TransferService


@click.group()
@click.pass_context
def cli(ctx):
    """Fitness data synchronization tool for Garmin and COROS."""
    ctx.ensure_object(dict)
    init_db()


@cli.group()
def config():
    """Manage platform configurations."""
    pass


@config.command()
@click.argument('platform', type=click.Choice(['garmin', 'coros']))
@click.option('--email', prompt=True, help='Account email')
def configure(platform, email):
    """Configure account for a platform."""
    password = getpass(f"Enter password for {email}: ")
    confirm = getpass("Confirm password: ")
    
    if password != confirm:
        click.echo("Error: Passwords do not match!", err=True)
        raise click.Abort()
    
    service = AccountService()
    try:
        service.configure(platform, email, password)
        click.echo(f"✓ {platform.capitalize()} account configured successfully")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@config.command('show')
def show_config():
    """Show all configured accounts."""
    service = AccountService()
    accounts = service.list_accounts()
    
    if not accounts:
        click.echo("No accounts configured.")
        return
    
    click.echo("\nConfigured Accounts:")
    click.echo("-" * 50)
    for acc in accounts:
        status = "✓" if acc.get('is_configured') else "✗"
        click.echo(f"{status} {acc['platform'].capitalize():<10} {acc['email']}")


@config.command()
@click.argument('platform', type=click.Choice(['garmin', 'coros']))
def remove(platform):
    """Remove configuration for a platform."""
    service = AccountService()
    if service.remove_account(platform):
        click.echo(f"✓ {platform.capitalize()} configuration removed")
    else:
        click.echo(f"No configuration found for {platform}")


@cli.command()
@click.argument('platform', type=click.Choice(['garmin', 'coros']))
@click.option('--start', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end', required=True, help='End date (YYYY-MM-DD)')
@click.option('--format', 'file_format', default='tcx', type=click.Choice(['tcx', 'gpx', 'fit']))
@click.option('--type', 'activity_type', help='Activity type filter')
def download(platform, start, end, file_format, activity_type):
    """Download activities from a platform."""
    try:
        start_date = datetime.strptime(start, '%Y-%m-%d').date()
        end_date = datetime.strptime(end, '%Y-%m-%d').date()
    except ValueError:
        click.echo("Error: Invalid date format. Use YYYY-MM-DD", err=True)
        raise click.Abort()
    
    service = DownloadService()
    try:
        result = service.download(
            platform=platform,
            start_date=start_date,
            end_date=end_date,
            file_format=file_format,
            activity_type=activity_type
        )
        
        click.echo(f"\nDownload Summary for {platform.capitalize()}:")
        click.echo(f"  Total: {result['total']}")
        click.echo(f"  Downloaded: {result['downloaded']}")
        click.echo(f"  Skipped: {result['skipped']}")
        click.echo(f"  Failed: {result['failed']}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.argument('platform', type=click.Choice(['garmin', 'coros']))
@click.option('--format', 'file_format', default='tcx', type=click.Choice(['tcx', 'gpx', 'fit']))
def sync(platform, file_format):
    """Sync recent activities (last 7 days) from a platform."""
    from datetime import date, timedelta
    
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    
    service = DownloadService()
    try:
        result = service.download(
            platform=platform,
            start_date=start_date,
            end_date=end_date,
            file_format=file_format
        )
        
        click.echo(f"\nSync Summary for {platform.capitalize()}:")
        click.echo(f"  Downloaded: {result['downloaded']}")
        click.echo(f"  Skipped: {result['skipped']}")
        click.echo(f"  Failed: {result['failed']}")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


@cli.command()
@click.option('--host', default='127.0.0.1', help='Host to bind to')
@click.option('--port', default=5000, help='Port to bind to')
def web(host, port):
    """Start the web UI."""
    from fitness_toolkit.web.app import create_app
    app = create_app()
    click.echo(f"Starting web server at http://{host}:{port}")
    app.run(host=host, port=port, debug=False)


@cli.command()
@click.option('--start', required=True, help='Start date (YYYY-MM-DD)')
@click.option('--end', required=True, help='End date (YYYY-MM-DD)')
@click.option('--sport-type', multiple=True, help='Sport type filter (can specify multiple)')
@click.option('--save-dir', type=click.Path(), help='Directory to save FIT files (default: current directory)')
def transfer(start, end, sport_type, save_dir):
    try:
        start_date = datetime.strptime(start, '%Y-%m-%d').date()
        end_date = datetime.strptime(end, '%Y-%m-%d').date()
    except ValueError:
        click.echo("Error: Invalid date format. Use YYYY-MM-DD", err=True)
        raise click.Abort()

    sport_types = list(sport_type) if sport_type else None
    save_directory = Path(save_dir) if save_dir else Path.cwd()

    service = TransferService()
    try:
        result = service.transfer(
            start_date=start_date,
            end_date=end_date,
            sport_types=sport_types,
            save_dir=save_directory
        )

        click.echo(f"\nTransfer Summary (COROS → Garmin):")
        click.echo(f"  Total activities found: {result['total']}")
        click.echo(f"  Successfully transferred: {result['uploaded']}")
        click.echo(f"  Skipped (already exists): {result['skipped']}")
        click.echo(f"  Failed: {len(result['failed'])}")

        if result['failed']:
            click.echo("\nFailed activities:")
            for failure in result['failed']:
                click.echo(f"  - {failure.get('name', 'Unknown')}: {failure.get('error', 'Unknown error')}")

        click.echo(f"\nFIT files saved to: {save_directory}")

    except ValueError as e:
        click.echo(f"Configuration error: {e}", err=True)
        click.echo("Please configure both COROS and Garmin accounts first:", err=True)
        click.echo("  fitness_toolkit config configure coros", err=True)
        click.echo("  fitness_toolkit config configure garmin", err=True)
        raise click.Abort()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise click.Abort()


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
