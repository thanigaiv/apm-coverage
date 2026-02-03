"""Broken trace analysis routes."""

from flask import Blueprint, render_template, request, jsonify
from app import db
from app.models import BrokenTrace, Service

bp = Blueprint('traces', __name__, url_prefix='/traces')


@bp.route('/')
def list_broken_traces():
    """List broken traces with missing instrumentation."""
    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25

    # Get broken traces (only multi-service traces with total_spans > 1)
    pagination = BrokenTrace.query.filter(
        BrokenTrace.total_spans > 1
    ).order_by(
        BrokenTrace.analyzed_at.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)

    traces = pagination.items

    return render_template(
        'traces.html',
        traces=traces,
        pagination=pagination
    )


@bp.route('/<trace_id>')
def trace_detail(trace_id):
    """Show details for a specific broken trace."""
    from app.models import APMService

    trace = BrokenTrace.query.filter_by(trace_id=trace_id).first_or_404()

    # Get service details for missing services
    missing_services = []
    if trace.missing_services:
        for service_name in trace.missing_services:
            service = Service.query.filter_by(service_name=service_name).first()
            if service:
                missing_services.append(service)

    # Build dependency graph data
    # Get all services involved in this trace
    all_service_names = set([trace.root_service] + (trace.missing_services or []))

    # Get APM status for all services
    apm_services = {apm.service_name: apm.has_apm for apm in APMService.query.filter(
        APMService.service_name.in_(all_service_names)
    ).all()}

    # Build nodes for the graph
    nodes = []
    edges = []
    added_nodes = set()

    # Add root service node
    root_has_apm = apm_services.get(trace.root_service, False)
    nodes.append({
        'id': trace.root_service,
        'label': trace.root_service,
        'has_apm': root_has_apm,
        'is_root': True
    })
    added_nodes.add(trace.root_service)

    # Add missing service nodes and edges
    for service_name in (trace.missing_services or []):
        # Skip if this service is already the root (for single-service traces)
        if service_name == trace.root_service:
            continue

        # Skip if already added
        if service_name in added_nodes:
            continue

        has_apm = apm_services.get(service_name, False)
        nodes.append({
            'id': service_name,
            'label': service_name,
            'has_apm': has_apm,
            'is_root': False
        })
        added_nodes.add(service_name)

        # Create edge from root to missing service (no self-referencing edges)
        if service_name != trace.root_service:
            edges.append({
                'from': trace.root_service,
                'to': service_name
            })

    # Try to get additional dependency information from service catalog
    try:
        from app.services.datadog_client import DatadogClient
        from flask import current_app

        client = DatadogClient(
            api_key=current_app.config['DD_API_KEY'],
            app_key=current_app.config['DD_APP_KEY'],
            site=current_app.config['DD_SITE']
        )

        dependencies = client.get_service_dependencies()

        # Add upstream/downstream dependencies if available
        for service_name in all_service_names:
            if service_name in dependencies:
                for dep in dependencies[service_name]:
                    # Skip if not already in nodes
                    if dep not in added_nodes:
                        dep_has_apm = apm_services.get(dep, False)
                        nodes.append({
                            'id': dep,
                            'label': dep,
                            'has_apm': dep_has_apm,
                            'is_root': False
                        })
                        added_nodes.add(dep)

                    # Add edge if not already present and not self-referencing
                    edge = {'from': service_name, 'to': dep}
                    if edge not in edges and service_name != dep:
                        edges.append(edge)
    except Exception as e:
        print(f"Could not fetch additional dependencies: {e}")

    return render_template(
        'trace_detail.html',
        trace=trace,
        missing_services=missing_services,
        graph_nodes=nodes,
        graph_edges=edges
    )


@bp.route('/api/stats')
def get_trace_stats():
    """Get trace analysis statistics."""
    total_broken_traces = BrokenTrace.query.count()

    # Count unique services with broken traces
    services_with_issues = db.session.query(
        BrokenTrace.root_service
    ).distinct().count()

    return jsonify({
        'total_broken_traces': total_broken_traces,
        'services_with_issues': services_with_issues
    })
