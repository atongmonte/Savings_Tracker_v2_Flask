"""Main entry point for the Savings Tracker Flask application."""

import os

from app import create_app


class PrefixMiddleware:
    """Apply URL path prefix when the upstream server does not set SCRIPT_NAME."""

    def __init__(self, app, prefix):
        self.app = app
        self.prefix = prefix.rstrip('/')

    def __call__(self, environ, start_response):
        if not self.prefix:
            return self.app(environ, start_response)

        script_name = environ.get('SCRIPT_NAME', '')
        path_info = environ.get('PATH_INFO', '')

        # Respect an upstream SCRIPT_NAME if already provided (e.g., IIS app alias).
        if script_name:
            return self.app(environ, start_response)

        if not path_info.startswith(self.prefix):
            location = f"{self.prefix}{path_info if path_info.startswith('/') else '/' + path_info}"
            query_string = environ.get('QUERY_STRING', '')
            if query_string:
                location = f"{location}?{query_string}"
            start_response('308 Permanent Redirect', [('Location', location)])
            return [b'']

        if path_info.startswith(self.prefix):
            environ['SCRIPT_NAME'] = self.prefix
            new_path = path_info[len(self.prefix):]
            environ['PATH_INFO'] = new_path or '/'

        return self.app(environ, start_response)


ENV = os.getenv('ENVIRONMENT', os.getenv('FLASK_ENV', 'development')).lower()
URL_PREFIX = os.getenv('URL_PREFIX', '/savingstracker')

app = create_app(ENV)

if URL_PREFIX:
    app.config['APPLICATION_ROOT'] = URL_PREFIX
    app.wsgi_app = PrefixMiddleware(app.wsgi_app, URL_PREFIX)


if __name__ == '__main__':
    print(f"Starting Flask development server (ENV={ENV}, URL_PREFIX={URL_PREFIX or '(none)'})")
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '5000')), debug=(ENV != 'production'))
