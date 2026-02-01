"""Datadog API client wrapper."""

import time
from datetime import datetime, timedelta
from datadog_api_client import ApiClient, Configuration
from datadog_api_client.v2.api.service_definition_api import ServiceDefinitionApi
from datadog_api_client.v2.api.apm_retention_filters_api import APMRetentionFiltersApi
from datadog_api_client.v1.api.service_level_objectives_api import ServiceLevelObjectivesApi
from datadog_api_client.v1.api.metrics_api import MetricsApi
from datadog_api_client.v2.api.spans_api import SpansApi
from datadog_api_client.exceptions import ApiException


class DatadogClient:
    """Wrapper for Datadog API interactions."""

    def __init__(self, api_key, app_key, site='datadoghq.com'):
        """Initialize Datadog API client."""
        self.configuration = Configuration()
        self.configuration.api_key['apiKeyAuth'] = api_key
        self.configuration.api_key['appKeyAuth'] = app_key
        self.configuration.server_variables['site'] = site
        self.api_client = ApiClient(self.configuration)

    def get_all_catalog_services(self):
        """
        Fetch all services from Datadog Software Catalog.

        Returns:
            list: List of service dictionaries with metadata
        """
        services = []
        try:
            with self.api_client as api_client:
                api_instance = ServiceDefinitionApi(api_client)

                # Get service definitions
                response = api_instance.list_service_definitions()

                if hasattr(response, 'data') and response.data:
                    for service_def in response.data:
                        service_data = {
                            'service_name': service_def.get('id', ''),
                            'tags': self._extract_tags(service_def),
                            'team': self._extract_team(service_def),
                            'environment': self._extract_environment(service_def),
                            'infrastructure_type': self._extract_infrastructure_type(service_def),
                            'is_customer_facing': self._is_customer_facing(service_def),
                            'last_seen_catalog': datetime.utcnow()
                        }
                        services.append(service_data)

        except ApiException as e:
            print(f"Error fetching catalog services: {e}")
            raise

        return services

    def get_apm_services(self, start_time=None, end_time=None):
        """
        Fetch services with APM instrumentation from Datadog.

        Args:
            start_time: Start time for query (default: 24 hours ago)
            end_time: End time for query (default: now)

        Returns:
            list: List of APM service dictionaries
        """
        if not start_time:
            start_time = datetime.utcnow() - timedelta(hours=24)
        if not end_time:
            end_time = datetime.utcnow()

        apm_services = []

        try:
            with self.api_client as api_client:
                metrics_api = MetricsApi(api_client)

                # Query for active APM services using trace metrics
                # Using trace.* metrics to identify services with APM
                query = 'trace.* by {service}.as_count()'

                response = metrics_api.query_metrics(
                    _from=int(start_time.timestamp()),
                    to=int(end_time.timestamp()),
                    query=query
                )

                if hasattr(response, 'series') and response.series:
                    for series in response.series:
                        # Extract service name from series tags
                        service_name = None
                        if hasattr(series, 'tag_set'):
                            for tag in series.tag_set:
                                if tag.startswith('service:'):
                                    service_name = tag.split(':', 1)[1]
                                    break

                        if service_name:
                            # Extract language from runtime tags if available
                            language = self._extract_language_from_tags(series.tag_set if hasattr(series, 'tag_set') else [])

                            # Count spans
                            span_count = 0
                            if hasattr(series, 'pointlist') and series.pointlist:
                                span_count = sum(point[1] for point in series.pointlist if len(point) > 1 and point[1])

                            apm_services.append({
                                'service_name': service_name,
                                'has_apm': True,
                                'apm_language': language,
                                'last_seen_apm': datetime.utcnow(),
                                'span_count_24h': int(span_count)
                            })

        except ApiException as e:
            print(f"Error fetching APM services: {e}")
            # Don't raise, return empty list to allow partial sync

        return apm_services

    def get_trace_spans(self, trace_id):
        """
        Fetch spans for a specific trace.

        Args:
            trace_id: Datadog trace ID

        Returns:
            list: List of span dictionaries
        """
        spans = []

        try:
            with self.api_client as api_client:
                spans_api = SpansApi(api_client)

                # Search for spans by trace ID
                response = spans_api.list_spans(
                    filter_query=f'trace_id:{trace_id}'
                )

                if hasattr(response, 'data') and response.data:
                    for span in response.data:
                        spans.append({
                            'trace_id': trace_id,
                            'span_id': span.get('id', ''),
                            'service': span.get('attributes', {}).get('service', ''),
                            'resource': span.get('attributes', {}).get('resource', ''),
                            'operation': span.get('attributes', {}).get('operation_name', ''),
                        })

        except ApiException as e:
            print(f"Error fetching trace {trace_id}: {e}")

        return spans

    def _extract_tags(self, service_def):
        """Extract tags from service definition."""
        tags = {}
        if hasattr(service_def, 'attributes'):
            attrs = service_def.attributes
            if hasattr(attrs, 'tags') and attrs.tags:
                for tag in attrs.tags:
                    if ':' in tag:
                        key, value = tag.split(':', 1)
                        tags[key] = value
                    else:
                        tags[tag] = ''
        return tags

    def _extract_team(self, service_def):
        """Extract team from service definition."""
        if hasattr(service_def, 'attributes'):
            attrs = service_def.attributes
            if hasattr(attrs, 'team'):
                return attrs.team
            # Fallback to tags
            if hasattr(attrs, 'tags') and attrs.tags:
                for tag in attrs.tags:
                    if tag.startswith('team:'):
                        return tag.split(':', 1)[1]
        return None

    def _extract_environment(self, service_def):
        """Extract environment from service definition."""
        if hasattr(service_def, 'attributes'):
            attrs = service_def.attributes
            if hasattr(attrs, 'tags') and attrs.tags:
                for tag in attrs.tags:
                    if tag.startswith('env:'):
                        return tag.split(':', 1)[1]
        return None

    def _extract_infrastructure_type(self, service_def):
        """Extract infrastructure type from service definition."""
        if hasattr(service_def, 'attributes'):
            attrs = service_def.attributes
            if hasattr(attrs, 'tags') and attrs.tags:
                for tag in attrs.tags:
                    if tag.startswith('infrastructure:'):
                        return tag.split(':', 1)[1]
                    # Check for specific infra tags
                    if 'eks' in tag.lower():
                        return 'EKS'
                    elif 'ecs' in tag.lower():
                        return 'ECS'
                    elif 'ec2' in tag.lower():
                        return 'EC2'
        return None

    def _is_customer_facing(self, service_def):
        """Determine if service is customer-facing."""
        if hasattr(service_def, 'attributes'):
            attrs = service_def.attributes
            if hasattr(attrs, 'tags') and attrs.tags:
                for tag in attrs.tags:
                    if 'customer-facing' in tag.lower() or 'public' in tag.lower():
                        return True
        return False

    def _extract_language_from_tags(self, tags):
        """Extract programming language from trace tags."""
        language_map = {
            'python': 'Python',
            'java': 'Java',
            'go': 'Go',
            'node': 'Node.js',
            'ruby': 'Ruby',
            'php': 'PHP',
            'dotnet': '.NET',
            'cpp': 'C++'
        }

        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower.startswith('language:'):
                lang = tag_lower.split(':', 1)[1]
                return language_map.get(lang, lang.capitalize())

            # Check for runtime tags
            for key, value in language_map.items():
                if key in tag_lower or f'runtime:{key}' in tag_lower:
                    return value

        return None
