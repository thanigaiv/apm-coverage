# APM Coverage Tracker

A Flask web application that integrates with Datadog APIs to track APM (Application Performance Monitoring) coverage across services and identify broken traces.

## Features

- **Dashboard**: Overview of APM coverage with key metrics and charts
- **Service Management**: List and filter services by team, environment, infrastructure type, and APM status
- **Broken Trace Analysis**: Identify traces with missing instrumentation
- **Automatic Synchronization**: Periodic syncing with Datadog APIs (configurable interval)
- **CSV Export**: Export service data for reporting

## Architecture

### Technology Stack
- **Backend**: Flask with SQLAlchemy ORM
- **Frontend**: Server-side Jinja2 templates with Bootstrap 5
- **Database**: PostgreSQL (with SQLite support for local development)
- **API Client**: datadog-api-client Python library
- **Background Jobs**: APScheduler for periodic Datadog syncing

### Key Components
- **Datadog Client**: Wrapper for Datadog API interactions
- **Sync Service**: Handles data synchronization with Datadog
- **Database Models**: Services, APM Services, Broken Traces, Sync Jobs
- **Web Routes**: Dashboard, Services, and Traces views

## Setup

### Prerequisites
- Python 3.9+
- PostgreSQL (or SQLite for local development)
- Datadog API Key and Application Key

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd apm-coverage
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   ```bash
   cp .env.example .env
   # Edit .env with your Datadog credentials and database URL
   ```

5. **Initialize the database**
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

6. **Run initial data sync**
   ```bash
   python -c "from app import create_app; from app.services.sync_service import sync_all; app = create_app(); app.app_context().push(); sync_all()"
   ```

7. **Start the application**
   ```bash
   python run.py
   ```

   The application will be available at `http://localhost:5000`

## Configuration

### Environment Variables

Required variables in `.env`:

```bash
# Datadog API Credentials
DD_API_KEY=your_datadog_api_key_here
DD_APP_KEY=your_datadog_app_key_here
DD_SITE=datadoghq.com  # Or datadoghq.eu, etc.

# Database Configuration
DATABASE_URL=postgresql://user:password@localhost:5432/apm_coverage
# For SQLite: sqlite:///apm_coverage.db

# Flask Configuration
FLASK_ENV=development  # or production
SECRET_KEY=your-secret-key-here
FLASK_APP=run.py

# Sync Configuration
SYNC_INTERVAL_MINUTES=15  # How often to sync with Datadog
```

### Database Setup

#### PostgreSQL (Recommended for Production)
```bash
# Create database
createdb apm_coverage

# Update DATABASE_URL in .env
DATABASE_URL=postgresql://username:password@localhost:5432/apm_coverage
```

#### SQLite (Quick Start)
```bash
# Update DATABASE_URL in .env
DATABASE_URL=sqlite:///apm_coverage.db
```

## Usage

### Web Interface

1. **Dashboard** (`/`)
   - View overall APM coverage metrics
   - See coverage by infrastructure type
   - Identify customer-facing services without APM
   - View recent broken traces

2. **Services** (`/services`)
   - List all services with filtering options
   - Filter by team, environment, infrastructure, APM status
   - Search by service name
   - Export to CSV

3. **Broken Traces** (`/traces`)
   - View traces with missing instrumentation
   - See which services are missing from trace paths
   - Analyze trace completeness

### Manual Sync

Trigger a manual sync from the web interface:
- Click "Sync Now" button in the navigation bar

Or run from command line:
```bash
python -c "from app import create_app; from app.services.sync_service import sync_all; app = create_app(); app.app_context().push(); sync_all()"
```

### Automatic Syncing

The application automatically syncs with Datadog every 15 minutes (configurable via `SYNC_INTERVAL_MINUTES`).

## Database Schema

### Services
- Service metadata from Datadog Software Catalog
- Tags, team, environment, infrastructure type
- Customer-facing flag

### APM Services
- APM instrumentation status
- Language, span counts, last seen timestamps

### Broken Traces
- Traces with missing instrumentation
- Missing service list, span counts

### Sync Jobs
- Track synchronization history
- Monitor sync status and errors

## Development

### Project Structure
```
apm-coverage/
├── app/
│   ├── __init__.py           # Flask app factory
│   ├── models.py             # Database models
│   ├── routes/               # Route blueprints
│   │   ├── dashboard.py
│   │   ├── services.py
│   │   └── traces.py
│   ├── services/             # Business logic
│   │   ├── datadog_client.py
│   │   └── sync_service.py
│   ├── templates/            # Jinja2 templates
│   └── static/               # CSS, JS files
├── migrations/               # Database migrations
├── config.py                 # Configuration
├── requirements.txt          # Dependencies
├── run.py                    # Application entry point
└── README.md
```

### Running Tests
```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
pytest

# With coverage
pytest --cov=app
```

### Database Migrations
```bash
# Create a new migration
flask db migrate -m "Description of changes"

# Apply migrations
flask db upgrade

# Rollback
flask db downgrade
```

## Deployment

### Using Docker (Recommended)

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Using Gunicorn

```bash
# Install gunicorn (already in requirements.txt)
pip install gunicorn

# Run with gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app()'
```

### Environment-Specific Deployment

For production:
```bash
export FLASK_ENV=production
gunicorn -w 4 -b 0.0.0.0:5000 'app:create_app("production")'
```

## Troubleshooting

### Common Issues

1. **Database connection errors**
   - Check DATABASE_URL in .env
   - Ensure PostgreSQL is running
   - Verify credentials

2. **Datadog API errors**
   - Verify DD_API_KEY and DD_APP_KEY
   - Check DD_SITE is correct for your region
   - Ensure API keys have proper permissions

3. **No services showing**
   - Run manual sync first
   - Check sync job status in database
   - Review application logs

4. **Scheduler not running**
   - Check SYNC_INTERVAL_MINUTES is set
   - Ensure only one Flask process is running (or set WERKZEUG_RUN_MAIN)

## API Endpoints

- `GET /` - Dashboard
- `GET /services` - List services with filters
- `GET /services/<service_name>` - Service details
- `GET /services/export` - Export services to CSV
- `GET /traces` - List broken traces
- `GET /traces/<trace_id>` - Trace details
- `POST /api/sync` - Trigger manual sync
- `GET /api/stats` - Dashboard statistics (JSON)

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License

## Support

For issues and questions, please open an issue on GitHub.
