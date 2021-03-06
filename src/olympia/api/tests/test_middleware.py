from gzip import GzipFile

from django.conf import settings

from unittest import mock
from six import BytesIO

from olympia.amo.tests import TestCase, addon_factory, reverse_ns
from olympia.api.middleware import (
    GZipMiddlewareForAPIOnly, IdentifyAPIRequestMiddleware)


class TestIdentifyAPIRequestMiddleware(TestCase):
    def test_api_identified(self):
        request = mock.Mock()
        request.path_info = '/api/v3/lol/'
        IdentifyAPIRequestMiddleware().process_request(request)
        assert request.is_api

    def test_disabled_for_the_rest(self):
        """Test that we don't tag the request as API on "regular" pages."""
        request = mock.Mock()
        request.path_info = '/'
        IdentifyAPIRequestMiddleware().process_request(request)
        assert not request.is_api

        request.path = '/en-US/firefox/'
        IdentifyAPIRequestMiddleware().process_request(request)
        assert not request.is_api


class TestGzipMiddleware(TestCase):
    @mock.patch('django.middleware.gzip.GZipMiddleware.process_response')
    def test_enabled_for_api(self, django_gzip_middleware):
        """Test that we call the gzip middleware for API pages."""
        request = mock.Mock()
        request.is_api = True
        GZipMiddlewareForAPIOnly().process_response(request, mock.Mock())
        assert django_gzip_middleware.call_count == 1

    @mock.patch('django.middleware.gzip.GZipMiddleware.process_response')
    def test_disabled_for_the_rest(self, django_gzip_middleware):
        """Test that we don't call gzip middleware for "regular" pages."""
        request = mock.Mock()
        request.is_api = False
        GZipMiddlewareForAPIOnly().process_response(request, mock.Mock())
        assert django_gzip_middleware.call_count == 0

    def test_settings(self):
        """Test that gzip middleware is near the top of the settings list."""
        # Gzip middleware should be near the top of the list, so that it runs
        # last in the process_response phase, in case the response body has
        # been modified by another middleware.
        # Sadly, raven inserts 2 middlewares before, but luckily the ones it
        # automatically inserts not modify the response.
        assert (
            settings.MIDDLEWARE[4] ==
            'olympia.api.middleware.GZipMiddlewareForAPIOnly')

    def test_api_endpoint_gzipped(self):
        """Test a simple API endpoint to make sure gzip is active there."""
        addon = addon_factory()
        url = reverse_ns('addon-detail', kwargs={'pk': addon.pk})
        response = self.client.get(url)
        assert response.status_code == 200
        assert response.content
        assert 'Content-Encoding' not in response

        response_gzipped = self.client.get(
            url, HTTP_ACCEPT_ENCODING='gzip',
            # Pretend that this happened over https, to test that this is still
            # enabled even for https.
            **{'wsgi.url_scheme': 'https'})
        assert response_gzipped.status_code == 200
        assert response_gzipped.content
        assert response_gzipped['Content-Encoding'] == 'gzip'

        assert len(response_gzipped.content) < len(response.content)
        ungzipped_content = GzipFile(
            '', 'r', 0, BytesIO(response_gzipped.content)).read()
        assert ungzipped_content == response.content
