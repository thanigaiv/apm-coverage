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

                # Get service definitions with pagination
                page_size = 100
                page_number = 0

                while True:
                    response = api_instance.list_service_definitions(
                        page_size=page_size,
                        page_number=page_number
                    )

                    if hasattr(response, 'data') and response.data:
                        for service_def in response.data:
                            # Convert to dict to access nested attributes easily
                            svc_dict = service_def.to_dict() if hasattr(service_def, 'to_dict') else service_def
                            schema = svc_dict.get('attributes', {}).get('schema', {})

                            service_data = {
                                'service_name': schema.get('dd_service', svc_dict.get('id', '')),
                                'tags': self._extract_tags(schema),
                                'team': self._extract_team(schema),
                                'environment': self._extract_environment(schema),
                                'infrastructure_type': self._extract_infrastructure_type(schema),
                                'is_customer_facing': self._is_customer_facing(schema),
                                'last_seen_catalog': datetime.utcnow()
                            }
                            services.append(service_data)

                        # Check if there are more pages
                        if len(response.data) < page_size:
                            # Last page reached
                            break

                        page_number += 1
                    else:
                        # No data returned
                        break

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
        seen_services = set()

        try:
            with self.api_client as api_client:
                metrics_api = MetricsApi(api_client)

                # Query for active APM services using trace metrics
                # Using a specific trace metric that captures all services
                query = 'sum:trace.servlet.request.hits{*} by {service}.as_count()'

                response = metrics_api.query_metrics(
                    _from=int(start_time.timestamp()),
                    to=int(end_time.timestamp()),
                    query=query
                )

                if hasattr(response, 'series') and response.series:
                    for series in response.series:
                        # Extract service name from scope
                        service_name = None
                        if hasattr(series, 'scope'):
                            scope = series.scope
                            # Scope can be like "service:my-service" or "service:a,service:b"
                            for part in scope.split(','):
                                part = part.strip()
                                if part.startswith('service:'):
                                    service_name = part.split(':', 1)[1]
                                    break

                        # Also check tag_set as fallback
                        if not service_name and hasattr(series, 'tag_set'):
                            for tag in series.tag_set:
                                if tag.startswith('service:'):
                                    service_name = tag.split(':', 1)[1]
                                    break

                        if service_name and service_name not in seen_services:
                            seen_services.add(service_name)

                            # Extract language from runtime tags if available
                            language = self._extract_language_from_tags(series.tag_set if hasattr(series, 'tag_set') else [])

                            # Count spans
                            span_count = 0
                            if hasattr(series, 'pointlist') and series.pointlist:
                                for point in series.pointlist:
                                    try:
                                        # Point can be a list/tuple or a Point object
                                        if hasattr(point, '__getitem__') and len(point) > 1:
                                            val = point[1]
                                        elif hasattr(point, 'value'):
                                            val = point.value
                                        else:
                                            val = None

                                        if val is not None:
                                            span_count += val
                                    except (IndexError, AttributeError, TypeError):
                                        continue

                            apm_services.append({
                                'service_name': service_name,
                                'has_apm': True,
                                'apm_language': language,
                                'last_seen_apm': datetime.utcnow(),
                                'span_count_24h': int(span_count)
                            })

                print(f"Found {len(apm_services)} services with APM instrumentation")

        except ApiException as e:
            print(f"Error fetching APM services: {e}")
            # Don't raise, return empty list to allow partial sync

        return apm_services

    def get_service_dependencies(self):
        """
        Identify service dependencies from service definitions.

        Returns:
            dict: Map of service_name -> list of dependent services
        """
        dependencies = {}

        try:
            with self.api_client as api_client:
                api_instance = ServiceDefinitionApi(api_client)

                page_size = 100
                page_number = 0

                while True:
                    response = api_instance.list_service_definitions(
                        page_size=page_size,
                        page_number=page_number
                    )

                    if hasattr(response, 'data') and response.data:
                        for service_def in response.data:
                            svc_dict = service_def.to_dict() if hasattr(service_def, 'to_dict') else service_def
                            schema = svc_dict.get('attributes', {}).get('schema', {})
                            service_name = schema.get('dd_service', '')

                            if service_name:
                                # Look for dependencies in links or integrations
                                deps = []

                                # Check integrations for service dependencies
                                integrations = schema.get('integrations', {})
                                if integrations:
                                    for key, value in integrations.items():
                                        if isinstance(value, str) and value:
                                            deps.append(value)

                                # Check tags for dependency hints
                                tags = schema.get('tags', [])
                                for tag in tags:
                                    if tag.startswith('depends_on:') or tag.startswith('calls:'):
                                        dep_service = tag.split(':', 1)[1]
                                        deps.append(dep_service)

                                if deps:
                                    dependencies[service_name] = deps

                        if len(response.data) < page_size:
                            break

                        page_number += 1
                    else:
                        break

        except ApiException as e:
            print(f"Error fetching service dependencies: {e}")

        return dependencies

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

    def _extract_tags(self, schema):
        """Extract tags from service schema."""
        tags = {}
        schema_tags = schema.get('tags', [])
        if schema_tags:
            for tag in schema_tags:
                if ':' in tag:
                    key, value = tag.split(':', 1)
                    tags[key] = value
                else:
                    tags[tag] = ''
        return tags

    def _extract_team(self, schema):
        """Extract team from service schema."""
        # First check for explicit team field
        if 'team' in schema:
            return schema['team']

        # Fallback to tags
        schema_tags = schema.get('tags', [])
        for tag in schema_tags:
            if tag.startswith('team:'):
                return tag.split(':', 1)[1]
        return None

    def _extract_environment(self, schema):
        """Extract environment from service schema."""
        schema_tags = schema.get('tags', [])
        for tag in schema_tags:
            if tag.startswith('env:') or tag.startswith('environment:'):
                return tag.split(':', 1)[1]
        return None

    def _extract_infrastructure_type(self, schema):
        """Extract infrastructure type from service schema."""
        schema_tags = schema.get('tags', [])
        for tag in schema_tags:
            if tag.startswith('infrastructure:'):
                return tag.split(':', 1)[1]
            # Check for specific infra tags
            tag_lower = tag.lower()
            if 'eks' in tag_lower:
                return 'EKS'
            elif 'ecs' in tag_lower:
                return 'ECS'
            elif 'ec2' in tag_lower:
                return 'EC2'
        return None

    def _is_customer_facing(self, schema):
        """Determine if service is customer-facing."""
        schema_tags = schema.get('tags', [])
        for tag in schema_tags:
            tag_lower = tag.lower()
            if 'customer-facing' in tag_lower or 'public' in tag_lower:
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
