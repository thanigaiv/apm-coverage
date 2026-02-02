"""Service listing and filtering routes."""

from flask import Blueprint, render_template, request, jsonify, Response
from sqlalchemy import or_, and_
from app import db
from app.models import Service, APMService
import csv
import io

bp = Blueprint('services', __name__, url_prefix='/services')


@bp.route('/')
def list_services():
    """List all services with filtering options."""
    # Get filter parameters
    team_filter = request.args.get('team')
    env_filter = request.args.get('environment')
    infra_filter = request.args.get('infrastructure')
    apm_filter = request.args.get('apm_status')
    customer_facing_filter = request.args.get('customer_facing')
    search_query = request.args.get('search', '').strip()
    tag_filter = request.args.get('tag', '').strip()

    # Build query
    query = db.session.query(Service).outerjoin(
        APMService, Service.service_name == APMService.service_name
    )

    # Apply filters
    if team_filter:
        query = query.filter(Service.team == team_filter)

    if env_filter:
        query = query.filter(Service.environment == env_filter)

    if infra_filter:
        query = query.filter(Service.infrastructure_type == infra_filter)

    if apm_filter:
        if apm_filter == 'enabled':
            query = query.filter(APMService.has_apm == True)
        elif apm_filter == 'disabled':
            query = query.filter(or_(APMService.has_apm == False, APMService.has_apm == None))

    if search_query:
        query = query.filter(Service.service_name.ilike(f'%{search_query}%'))

    # Get services (before filtering)
    services = query.all()

    # Apply customer_facing filter (critical_flow=true) in Python
    if customer_facing_filter:
        filtered_list = []
        for service in services:
            # Customer-facing services are those with critical_flow=true
            is_customer_facing = service.tags and service.tags.get('critical_flow') == 'true'

            if customer_facing_filter == 'yes' and is_customer_facing:
                filtered_list.append(service)
            elif customer_facing_filter == 'no' and not is_customer_facing:
                filtered_list.append(service)

        services = filtered_list

    # Apply tag filter in Python (database-agnostic approach)
    if tag_filter:
        # Parse tag filter (format: "key:value" or "key=value")
        if ':' in tag_filter:
            tag_key, tag_value = tag_filter.split(':', 1)
        elif '=' in tag_filter:
            tag_key, tag_value = tag_filter.split('=', 1)
        else:
            tag_key = tag_filter
            tag_value = None

        # Filter services by tag
        filtered_services = []
        for service in services:
            if service.tags:
                if tag_value:
                    # Check for exact key-value match
                    if service.tags.get(tag_key) == tag_value:
                        filtered_services.append(service)
                else:
                    # Check for key existence
                    if tag_key in service.tags:
                        filtered_services.append(service)
        services = filtered_services

    # Get filter options for dropdowns
    teams = db.session.query(Service.team).distinct().filter(Service.team.isnot(None)).all()
    teams = sorted([t[0] for t in teams])

    environments = db.session.query(Service.environment).distinct().filter(Service.environment.isnot(None)).all()
    environments = sorted([e[0] for e in environments])

    infrastructure_types = db.session.query(Service.infrastructure_type).distinct().filter(Service.infrastructure_type.isnot(None)).all()
    infrastructure_types = sorted([i[0] for i in infrastructure_types])

    return render_template(
        'services.html',
        services=services,
        teams=teams,
        environments=environments,
        infrastructure_types=infrastructure_types,
        filters={
            'team': team_filter,
            'environment': env_filter,
            'infrastructure': infra_filter,
            'apm_status': apm_filter,
            'customer_facing': customer_facing_filter,
            'search': search_query,
            'tag': tag_filter
        }
    )


@bp.route('/export')
def export_services():
    """Export services to CSV."""
    # Get all services with APM status
    services = db.session.query(Service).outerjoin(
        APMService, Service.service_name == APMService.service_name
    ).all()

    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        'Service Name',
        'Team',
        'Environment',
        'Infrastructure Type',
        'Customer Facing',
        'APM Enabled',
        'APM Language',
        'Last Seen Catalog',
        'Last Seen APM'
    ])

    # Write data
    for service in services:
        # Customer-facing services are those with critical_flow=true
        is_customer_facing = service.tags and service.tags.get('critical_flow') == 'true'

        writer.writerow([
            service.service_name,
            service.team or '',
            service.environment or '',
            service.infrastructure_type or '',
            'Yes' if is_customer_facing else 'No',
            'Yes' if service.apm_service and service.apm_service.has_apm else 'No',
            service.apm_service.apm_language if service.apm_service else '',
            service.last_seen_catalog.isoformat() if service.last_seen_catalog else '',
            service.apm_service.last_seen_apm.isoformat() if service.apm_service and service.apm_service.last_seen_apm else ''
        ])

    # Create response
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=apm_services.csv'}
    )


@bp.route('/<service_name>')
def service_detail(service_name):
    """Show details for a specific service."""
    service = Service.query.filter_by(service_name=service_name).first_or_404()

    return render_template(
        'service_detail.html',
        service=service
    )
