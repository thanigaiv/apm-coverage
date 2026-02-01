"""Dashboard routes."""

from flask import Blueprint, render_template, jsonify
from sqlalchemy import func
from app import db
from app.models import Service, APMService, BrokenTrace, SyncJob
from app.services.sync_service import sync_all

bp = Blueprint('dashboard', __name__)


@bp.route('/')
def index():
    """Main dashboard page."""
    # Get coverage statistics
    total_services = Service.query.count()
    services_with_apm = APMService.query.filter_by(has_apm=True).count()
    services_without_apm = total_services - services_with_apm
    coverage_percentage = (services_with_apm / total_services * 100) if total_services > 0 else 0

    # Breakdown by infrastructure type
    infra_stats = db.session.query(
        Service.infrastructure_type,
        func.count(Service.id).label('total'),
        func.sum(func.cast(APMService.has_apm, db.Integer)).label('with_apm')
    ).outerjoin(APMService, Service.service_name == APMService.service_name)\
     .group_by(Service.infrastructure_type).all()

    infra_breakdown = []
    for infra_type, total, with_apm in infra_stats:
        with_apm = with_apm or 0
        infra_breakdown.append({
            'type': infra_type or 'Unknown',
            'total': total,
            'with_apm': int(with_apm),
            'without_apm': total - int(with_apm),
            'percentage': (int(with_apm) / total * 100) if total > 0 else 0
        })

    # Customer-facing services without APM
    customer_facing_no_apm = db.session.query(Service).join(
        APMService, Service.service_name == APMService.service_name
    ).filter(
        Service.is_customer_facing == True,
        APMService.has_apm == False
    ).all()

    # Recent broken traces
    recent_broken_traces = BrokenTrace.query.order_by(
        BrokenTrace.analyzed_at.desc()
    ).limit(10).all()

    # Last sync job
    last_sync = SyncJob.query.filter_by(
        job_type='catalog_sync',
        status='completed'
    ).order_by(SyncJob.completed_at.desc()).first()

    return render_template(
        'dashboard.html',
        total_services=total_services,
        services_with_apm=services_with_apm,
        services_without_apm=services_without_apm,
        coverage_percentage=coverage_percentage,
        infra_breakdown=infra_breakdown,
        customer_facing_no_apm=customer_facing_no_apm,
        recent_broken_traces=recent_broken_traces,
        last_sync=last_sync
    )


@bp.route('/api/sync', methods=['POST'])
def trigger_sync():
    """Manually trigger a sync with Datadog."""
    try:
        sync_all()
        return jsonify({'success': True, 'message': 'Sync completed successfully'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@bp.route('/api/stats')
def get_stats():
    """Get dashboard statistics as JSON."""
    total_services = Service.query.count()
    services_with_apm = APMService.query.filter_by(has_apm=True).count()

    return jsonify({
        'total_services': total_services,
        'services_with_apm': services_with_apm,
        'services_without_apm': total_services - services_with_apm,
        'coverage_percentage': (services_with_apm / total_services * 100) if total_services > 0 else 0
    })
