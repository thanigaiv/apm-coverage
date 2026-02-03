"""Dashboard routes."""

from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import func
from app import db
from app.models import Service, APMService, BrokenTrace, SyncJob
from app.services.sync_service import sync_all

bp = Blueprint('dashboard', __name__)


@bp.route('/')
def index():
    """Main dashboard page."""
    # Get filter parameters
    product_filter = request.args.get('product')
    domain_filter = request.args.get('domain')
    funnel_filter = request.args.get('funnel')
    critical_flow_filter = request.args.get('critical_flow')

    # Build base query for services
    base_query = Service.query

    # Apply tag filters in Python (database-agnostic approach)
    filtered_services = base_query.all()

    if product_filter or domain_filter or funnel_filter or critical_flow_filter:
        filtered_list = []
        for service in filtered_services:
            if not service.tags:
                continue

            # Check each filter
            if product_filter and service.tags.get('product') != product_filter:
                continue
            if domain_filter and service.tags.get('domain') != domain_filter:
                continue
            if funnel_filter and service.tags.get('funnel') != funnel_filter:
                continue
            if critical_flow_filter and service.tags.get('critical_flow') != critical_flow_filter:
                continue

            filtered_list.append(service)
        filtered_services = filtered_list

    # Get service names for APM queries
    filtered_service_names = [s.service_name for s in filtered_services]

    # Get coverage statistics
    total_services = len(filtered_services)

    if total_services > 0:
        services_with_apm = APMService.query.filter(
            APMService.service_name.in_(filtered_service_names),
            APMService.has_apm == True
        ).count()
    else:
        services_with_apm = 0

    services_without_apm = total_services - services_with_apm
    coverage_percentage = (services_with_apm / total_services * 100) if total_services > 0 else 0

    # Breakdown by infrastructure type
    infra_breakdown = []
    if total_services > 0:
        from collections import defaultdict
        infra_stats = defaultdict(lambda: {'total': 0, 'with_apm': 0})

        apm_services = {apm.service_name: apm.has_apm for apm in APMService.query.filter(
            APMService.service_name.in_(filtered_service_names)
        ).all()}

        for service in filtered_services:
            infra_type = service.infrastructure_type or 'Unknown'
            infra_stats[infra_type]['total'] += 1
            if apm_services.get(service.service_name, False):
                infra_stats[infra_type]['with_apm'] += 1

        for infra_type, stats in infra_stats.items():
            infra_breakdown.append({
                'type': infra_type,
                'total': stats['total'],
                'with_apm': stats['with_apm'],
                'without_apm': stats['total'] - stats['with_apm'],
                'percentage': (stats['with_apm'] / stats['total'] * 100) if stats['total'] > 0 else 0
            })

    # Customer-facing services without APM (critical_flow=true)
    customer_facing_no_apm = []
    if total_services > 0:
        apm_service_map = {apm.service_name: apm.has_apm for apm in APMService.query.filter(
            APMService.service_name.in_(filtered_service_names)
        ).all()}

        for service in filtered_services:
            # Customer-facing services are those with critical_flow=true
            is_customer_facing = service.tags and service.tags.get('critical_flow') == 'true'
            if is_customer_facing and not apm_service_map.get(service.service_name, False):
                customer_facing_no_apm.append(service)

    # Recent broken traces (only multi-service traces)
    recent_broken_traces = BrokenTrace.query.filter(
        BrokenTrace.total_spans > 1
    ).order_by(
        BrokenTrace.analyzed_at.desc()
    ).limit(10).all()

    # Last sync job
    last_sync = SyncJob.query.filter_by(
        job_type='catalog_sync',
        status='completed'
    ).order_by(SyncJob.completed_at.desc()).first()

    # Get unique values for filter dropdowns
    all_services = Service.query.all()
    products = sorted(set(s.tags.get('product') for s in all_services if s.tags and s.tags.get('product')))
    domains = sorted(set(s.tags.get('domain') for s in all_services if s.tags and s.tags.get('domain')))
    funnels = sorted(set(s.tags.get('funnel') for s in all_services if s.tags and s.tags.get('funnel')))
    critical_flows = sorted(set(s.tags.get('critical_flow') for s in all_services if s.tags and s.tags.get('critical_flow')))

    return render_template(
        'dashboard.html',
        total_services=total_services,
        services_with_apm=services_with_apm,
        services_without_apm=services_without_apm,
        coverage_percentage=coverage_percentage,
        infra_breakdown=infra_breakdown,
        customer_facing_no_apm=customer_facing_no_apm,
        recent_broken_traces=recent_broken_traces,
        last_sync=last_sync,
        products=products,
        domains=domains,
        funnels=funnels,
        critical_flows=critical_flows,
        filters={
            'product': product_filter,
            'domain': domain_filter,
            'funnel': funnel_filter,
            'critical_flow': critical_flow_filter
        }
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
