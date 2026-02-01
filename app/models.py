"""Database models for APM Coverage Tracker."""

from datetime import datetime
from app import db


class Service(db.Model):
    """Services from Datadog Software Catalog."""

    __tablename__ = 'services'

    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(255), unique=True, nullable=False, index=True)
    tags = db.Column(db.JSON, default=dict)  # JSONB for PostgreSQL, JSON for SQLite
    team = db.Column(db.String(100))
    environment = db.Column(db.String(50))
    infrastructure_type = db.Column(db.String(50))  # EKS, ECS, EC2
    is_customer_facing = db.Column(db.Boolean, default=False)
    last_seen_catalog = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    apm_service = db.relationship('APMService', backref='service', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Service {self.service_name}>'

    def to_dict(self):
        """Convert service to dictionary."""
        return {
            'id': self.id,
            'service_name': self.service_name,
            'tags': self.tags,
            'team': self.team,
            'environment': self.environment,
            'infrastructure_type': self.infrastructure_type,
            'is_customer_facing': self.is_customer_facing,
            'last_seen_catalog': self.last_seen_catalog.isoformat() if self.last_seen_catalog else None,
            'has_apm': self.apm_service.has_apm if self.apm_service else False,
            'apm_language': self.apm_service.apm_language if self.apm_service else None,
        }


class APMService(db.Model):
    """APM instrumentation status for services."""

    __tablename__ = 'apm_services'

    id = db.Column(db.Integer, primary_key=True)
    service_name = db.Column(db.String(255), db.ForeignKey('services.service_name'), unique=True, nullable=False, index=True)
    has_apm = db.Column(db.Boolean, default=False, nullable=False)
    apm_language = db.Column(db.String(50))  # Python, Java, Go, Node.js, etc.
    last_seen_apm = db.Column(db.DateTime)
    span_count_24h = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f'<APMService {self.service_name} (APM: {self.has_apm})>'


class BrokenTrace(db.Model):
    """Traces with missing instrumentation."""

    __tablename__ = 'broken_traces'

    id = db.Column(db.Integer, primary_key=True)
    trace_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    root_service = db.Column(db.String(255), nullable=False, index=True)
    missing_services = db.Column(db.JSON, default=list)  # Array of service names
    total_spans = db.Column(db.Integer, default=0)
    missing_span_count = db.Column(db.Integer, default=0)
    analyzed_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f'<BrokenTrace {self.trace_id} ({len(self.missing_services)} missing)>'

    def to_dict(self):
        """Convert broken trace to dictionary."""
        return {
            'id': self.id,
            'trace_id': self.trace_id,
            'root_service': self.root_service,
            'missing_services': self.missing_services,
            'total_spans': self.total_spans,
            'missing_span_count': self.missing_span_count,
            'analyzed_at': self.analyzed_at.isoformat(),
        }


class SyncJob(db.Model):
    """Track synchronization jobs."""

    __tablename__ = 'sync_jobs'

    id = db.Column(db.Integer, primary_key=True)
    job_type = db.Column(db.String(50), nullable=False, index=True)  # catalog_sync, apm_sync, trace_analysis
    status = db.Column(db.String(20), nullable=False, default='running')  # running, completed, failed
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    services_synced = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)

    def __repr__(self):
        return f'<SyncJob {self.job_type} ({self.status})>'

    def to_dict(self):
        """Convert sync job to dictionary."""
        return {
            'id': self.id,
            'job_type': self.job_type,
            'status': self.status,
            'started_at': self.started_at.isoformat(),
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'services_synced': self.services_synced,
            'error_message': self.error_message,
        }
