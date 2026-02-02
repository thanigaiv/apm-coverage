"""Service for synchronizing data with Datadog."""

from datetime import datetime, timedelta
from flask import current_app
from apscheduler.schedulers.background import BackgroundScheduler
from app import db
from app.models import Service, APMService, BrokenTrace, SyncJob
from app.services.datadog_client import DatadogClient


def get_datadog_client():
    """Get initialized Datadog client from app config."""
    return DatadogClient(
        api_key=current_app.config['DD_API_KEY'],
        app_key=current_app.config['DD_APP_KEY'],
        site=current_app.config['DD_SITE']
    )


def sync_catalog_services():
    """Sync services from Datadog Software Catalog."""
    job = SyncJob(job_type='catalog_sync', status='running', started_at=datetime.utcnow())
    db.session.add(job)
    db.session.commit()

    try:
        client = get_datadog_client()
        catalog_services = client.get_all_catalog_services()

        services_synced = 0
        for service_data in catalog_services:
            # Upsert service
            service = Service.query.filter_by(service_name=service_data['service_name']).first()

            if service:
                # Update existing service
                service.tags = service_data['tags']
                service.team = service_data['team']
                service.environment = service_data['environment']
                service.infrastructure_type = service_data['infrastructure_type']
                service.is_customer_facing = service_data['is_customer_facing']
                service.last_seen_catalog = service_data['last_seen_catalog']
                service.updated_at = datetime.utcnow()
            else:
                # Create new service
                service = Service(**service_data)
                db.session.add(service)

            services_synced += 1

        db.session.commit()

        # Mark job as completed
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        job.services_synced = services_synced
        db.session.commit()

        print(f"Catalog sync completed: {services_synced} services synced")
        return services_synced

    except Exception as e:
        db.session.rollback()
        job.status = 'failed'
        job.completed_at = datetime.utcnow()
        job.error_message = str(e)
        db.session.commit()
        print(f"Catalog sync failed: {e}")
        raise


def sync_apm_coverage():
    """Sync APM instrumentation status for services."""
    job = SyncJob(job_type='apm_sync', status='running', started_at=datetime.utcnow())
    db.session.add(job)
    db.session.commit()

    try:
        client = get_datadog_client()
        apm_services = client.get_apm_services()

        # Create a set of service names with APM
        apm_service_names = {svc['service_name'] for svc in apm_services}

        # Get all services from catalog
        all_services = Service.query.all()
        services_synced = 0

        for service in all_services:
            # Check if service has APM data
            apm_data = next(
                (svc for svc in apm_services if svc['service_name'] == service.service_name),
                None
            )

            # Upsert APM service record
            apm_service = APMService.query.filter_by(service_name=service.service_name).first()

            if apm_data:
                # Service has APM
                if apm_service:
                    apm_service.has_apm = True
                    apm_service.apm_language = apm_data['apm_language']
                    apm_service.last_seen_apm = apm_data['last_seen_apm']
                    apm_service.span_count_24h = apm_data['span_count_24h']
                    apm_service.updated_at = datetime.utcnow()
                else:
                    apm_service = APMService(
                        service_name=service.service_name,
                        has_apm=True,
                        apm_language=apm_data['apm_language'],
                        last_seen_apm=apm_data['last_seen_apm'],
                        span_count_24h=apm_data['span_count_24h']
                    )
                    db.session.add(apm_service)
            else:
                # Service does not have APM
                if apm_service:
                    apm_service.has_apm = False
                    apm_service.updated_at = datetime.utcnow()
                else:
                    apm_service = APMService(
                        service_name=service.service_name,
                        has_apm=False
                    )
                    db.session.add(apm_service)

            services_synced += 1

        db.session.commit()

        # Mark job as completed
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        job.services_synced = services_synced
        db.session.commit()

        print(f"APM sync completed: {services_synced} services synced")
        return services_synced

    except Exception as e:
        db.session.rollback()
        job.status = 'failed'
        job.completed_at = datetime.utcnow()
        job.error_message = str(e)
        db.session.commit()
        print(f"APM sync failed: {e}")
        raise


def analyze_broken_traces(sample_size=100):
    """
    Analyze service dependencies to identify potential broken traces.

    This identifies services without APM that are dependencies of services with APM,
    which would result in incomplete/broken distributed traces.

    Args:
        sample_size: Maximum number of broken traces to store
    """
    job = SyncJob(job_type='trace_analysis', status='running', started_at=datetime.utcnow())
    db.session.add(job)
    db.session.commit()

    try:
        client = get_datadog_client()

        # Get services with and without APM
        services_with_apm = {apm.service_name for apm in APMService.query.filter_by(has_apm=True).all()}
        services_without_apm = {apm.service_name for apm in APMService.query.filter_by(has_apm=False).all()}

        print(f"Analyzing traces: {len(services_with_apm)} with APM, {len(services_without_apm)} without APM")

        # Clear old broken traces
        BrokenTrace.query.delete()
        db.session.commit()

        traces_created = 0

        # Strategy 1: Identify high-priority services without APM
        # These are services that should have APM based on their characteristics
        priority_services = Service.query.filter(
            Service.service_name.in_(services_without_apm)
        ).all()

        for service in priority_services:
            # Skip if we've hit the limit
            if traces_created >= sample_size:
                break

            # Identify why this is a potential broken trace
            reasons = []

            if service.is_customer_facing:
                reasons.append("customer-facing service")

            if service.tags.get('critical_flow') == 'true':
                reasons.append("critical flow service")

            # High-value domains/products
            high_value_domains = ['experiences', 'platform', 'payments', 'booking']
            if service.tags.get('domain', '').lower() in high_value_domains:
                reasons.append(f"high-value domain: {service.tags.get('domain')}")

            # If this service has reasons to have APM, create a broken trace record
            if reasons:
                # Generate a synthetic trace ID based on service name
                import hashlib
                trace_id = hashlib.md5(f"{service.service_name}-{datetime.utcnow().date()}".encode()).hexdigest()

                broken_trace = BrokenTrace(
                    trace_id=trace_id,
                    root_service=service.service_name,
                    missing_services=[service.service_name],
                    total_spans=1,
                    missing_span_count=1,
                    analyzed_at=datetime.utcnow()
                )

                db.session.add(broken_trace)
                traces_created += 1

        # Strategy 2: Use service dependencies if available
        # (This would require dependency information in service definitions)
        try:
            dependencies = client.get_service_dependencies()

            if dependencies:
                print(f"Found {len(dependencies)} services with dependencies")

                for service_name, deps in dependencies.items():
                    if traces_created >= sample_size:
                        break

                    # If service has APM but depends on services without APM
                    if service_name in services_with_apm:
                        missing_deps = [dep for dep in deps if dep in services_without_apm]

                        if missing_deps:
                            # Generate trace ID
                            trace_id = hashlib.md5(f"dep-{service_name}-{datetime.utcnow().date()}".encode()).hexdigest()

                            broken_trace = BrokenTrace(
                                trace_id=trace_id,
                                root_service=service_name,
                                missing_services=missing_deps,
                                total_spans=len(deps) + 1,
                                missing_span_count=len(missing_deps),
                                analyzed_at=datetime.utcnow()
                            )

                            db.session.add(broken_trace)
                            traces_created += 1

        except Exception as e:
            print(f"Could not analyze dependencies: {e}")

        db.session.commit()

        # Mark job as completed
        job.status = 'completed'
        job.completed_at = datetime.utcnow()
        job.services_synced = traces_created
        db.session.commit()

        print(f"Trace analysis completed: {traces_created} potential broken traces identified")
        return traces_created

    except Exception as e:
        db.session.rollback()
        job.status = 'failed'
        job.completed_at = datetime.utcnow()
        job.error_message = str(e)
        db.session.commit()
        print(f"Trace analysis failed: {e}")
        raise


def sync_all():
    """Run all sync operations in sequence."""
    try:
        print("Starting full sync...")
        catalog_count = sync_catalog_services()
        print(f"Catalog sync: {catalog_count} services")

        apm_count = sync_apm_coverage()
        print(f"APM sync: {apm_count} services")

        trace_count = analyze_broken_traces()
        print(f"Trace analysis: {trace_count} traces")

        print("Full sync completed successfully")
    except Exception as e:
        print(f"Full sync failed: {e}")
        raise


# Scheduler instance
scheduler = None


def start_scheduler(app):
    """Start the APScheduler for periodic syncs."""
    global scheduler

    if scheduler is not None:
        return  # Already started

    scheduler = BackgroundScheduler()

    # Schedule sync_all to run periodically
    interval_minutes = app.config.get('SYNC_INTERVAL_MINUTES', 15)

    def scheduled_sync():
        with app.app_context():
            sync_all()

    scheduler.add_job(
        func=scheduled_sync,
        trigger='interval',
        minutes=interval_minutes,
        id='datadog_sync',
        name='Sync Datadog data',
        replace_existing=True
    )

    scheduler.start()
    print(f"Scheduler started: syncing every {interval_minutes} minutes")


def stop_scheduler():
    """Stop the scheduler."""
    global scheduler
    if scheduler is not None:
        scheduler.shutdown()
        scheduler = None
        print("Scheduler stopped")
