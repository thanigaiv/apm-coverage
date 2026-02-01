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

    # Get broken traces
    pagination = BrokenTrace.query.order_by(
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
    trace = BrokenTrace.query.filter_by(trace_id=trace_id).first_or_404()

    # Get service details for missing services
    missing_services = []
    if trace.missing_services:
        for service_name in trace.missing_services:
            service = Service.query.filter_by(service_name=service_name).first()
            if service:
                missing_services.append(service)

    return render_template(
        'trace_detail.html',
        trace=trace,
        missing_services=missing_services
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
