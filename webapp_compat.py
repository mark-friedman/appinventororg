import os
import re
import urllib.parse
from werkzeug.wrappers import Request as WZRequest, Response as WZResponse

# Override Werkzeug's default size limits for the compatibility Request wrapper
WZRequest.max_content_length = 32 * 1024 * 1024    # 32 MB
WZRequest.max_form_memory_size = 16 * 1024 * 1024  # 16 MB

from jinja2 import Environment, FileSystemLoader

# Custom Jinja2 Django-style slice filter
def jinja2_slice(value, slice_spec):
    if value is None:
        return []
    if not slice_spec or not isinstance(slice_spec, str) or ':' not in slice_spec:
        return value
    try:
        parts = slice_spec.split(':')
        start = int(parts[0]) if parts[0] else None
        stop = int(parts[1]) if (len(parts) > 1 and parts[1]) else None
        step = int(parts[2]) if (len(parts) > 2 and parts[2]) else None
        return value[slice(start, stop, step)]
    except Exception:
        return value

# OutputWriter for ResponseAdapter
class OutputWriter:
    def __init__(self):
        self.buffer = []
    
    def write(self, content):
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        elif not isinstance(content, str):
            content = str(content)
        self.buffer.append(content)
        
    def getvalue(self):
        return "".join(self.buffer)

# ResponseAdapter emulating GAE webapp Response
class ResponseAdapter:
    def __init__(self):
        self.out = OutputWriter()
        self.headers = {'Content-Type': 'text/html; charset=utf-8'}
        self.status = 200

    def set_status(self, code, message=None):
        self.status = code

    def redirect(self, url, permanent=False):
        self.status = 301 if permanent else 302
        self.headers['Location'] = url

# RequestAdapter emulating GAE webapp Request
class RequestAdapter:
    def __init__(self, wz_req):
        self._req = wz_req
        # Read and cache body before values/form are accessed to prevent input stream consumption
        self._body = wz_req.get_data(cache=True)
        self.headers = wz_req.headers
        self.cookies = wz_req.cookies
        self.remote_addr = wz_req.remote_addr
        self.url = wz_req.url
        self.uri = wz_req.url
        self.path = wz_req.path
        self.query_string = wz_req.query_string.decode('utf-8') if isinstance(wz_req.query_string, bytes) else wz_req.query_string
        self.method = wz_req.method
        self.host = wz_req.host
        self.scheme = wz_req.scheme
        
    @property
    def body(self):
        return self._body

    def get(self, name, default_value=''):
        val = self._req.values.get(name)
        return val if val is not None else default_value

    def get_all(self, name):
        return self._req.values.getlist(name)

    def arguments(self):
        return list(self._req.values.keys())

    def get_range(self, name, min_value=None, max_value=None, default=None):
        val = self.get(name)
        if not val:
            return default
        try:
            val = int(val)
            if min_value is not None and val < min_value:
                val = min_value
            if max_value is not None and val > max_value:
                val = max_value
            return val
        except ValueError:
            return default

# RequestHandler base class emulating GAE RequestHandler
class RequestHandler:
    def __init__(self):
        self.request = None
        self.response = None

    def initialize(self, request, response):
        self.request = request
        self.response = response

    def redirect(self, url, permanent=False):
        if self.response:
            self.response.redirect(url, permanent=permanent)


    def get(self, *args, **kwargs):
        pass

    def post(self, *args, **kwargs):
        pass

    def put(self, *args, **kwargs):
        pass

    def delete(self, *args, **kwargs):
        pass

    def head(self, *args, **kwargs):
        pass

    def options(self, *args, **kwargs):
        pass

    def trace(self, *args, **kwargs):
        pass

# Route class emulating webapp2 Route
class Route:
    def __init__(self, template, handler=None, **kwargs):
        self.template = template
        self.handler = handler or kwargs.get('handler')

# WSGIApplication emulating GAE WSGIApplication
class WSGIApplication:
    def __init__(self, routes, debug=False):
        self.routes = []
        for route in routes:
            if isinstance(route, Route):
                pattern = route.template
                handler = route.handler
            else:
                pattern = route[0]
                handler = route[1]
            
            # Translate GAE webapp2 route <param_name> syntax to standard regex
            # e.g., /content/<course_ID> -> /content/([^/]+)
            pattern = re.sub(r'<[^>]+>', r'([^/]+)', pattern)
            
            if not pattern.startswith('^'):
                pattern = '^' + pattern
            if not pattern.endswith('$'):
                pattern = pattern + '$'
            self.routes.append((re.compile(pattern), handler))
        self.debug = debug

    def __call__(self, environ, start_response):
        wz_req = WZRequest(environ)
        path = wz_req.path

        handler_class = None
        args = []
        for pattern, handler in self.routes:
            match = pattern.match(path)
            if match:
                handler_class = handler
                args = match.groups()
                # URL decode capture groups
                args = [urllib.parse.unquote(arg) for arg in args]
                break

        if not handler_class:
            response = WZResponse("Not Found", status=404)
            return response(environ, start_response)

        req_adapter = RequestAdapter(wz_req)
        resp_adapter = ResponseAdapter()

        handler = handler_class()
        handler.initialize(req_adapter, resp_adapter)

        method = wz_req.method.lower()
        handler_method = getattr(handler, method, None)
        if not handler_method:
            response = WZResponse("Method Not Allowed", status=405)
            return response(environ, start_response)

        try:
            handler_method(*args)
            body = resp_adapter.out.getvalue().encode('utf-8')
            headers = list(resp_adapter.headers.items())
            response = WZResponse(body, status=resp_adapter.status, headers=headers)
            return response(environ, start_response)
        except Exception as e:
            if self.debug:
                raise
            response = WZResponse("Internal Server Error", status=500)
            return response(environ, start_response)

class DjangoCompatFileSystemLoader(FileSystemLoader):
    def get_source(self, environment, template):
        source, filename, uptodate = super().get_source(environment, template)
        
        # 1. Translate forloop to loop
        source = source.replace('forloop.counter0', 'loop.index0')
        source = source.replace('forloop.counter', 'loop.index')
        source = source.replace('forloop.revcounter0', 'loop.revindex0')
        source = source.replace('forloop.revcounter', 'loop.revindex')
        source = source.replace('forloop.parentloop', 'loop.parent')
        source = source.replace('forloop.', 'loop.')
        
        # 2. Translate Django filter syntax (e.g. |slice:":1", |divisibleby:4) to Jinja2 filter syntax (e.g. |slice(":1"), |divisibleby(4))
        # Pattern A (quoted arguments): |filterName:"arg"
        source = re.sub(r'\|([a-zA-Z0-9_]+):("[^"]*"|\'[^\']*\')', r'|\1(\2)', source)
        # Pattern B (unquoted arguments): |filterName:arg
        source = re.sub(r'\|([a-zA-Z0-9_]+):([a-zA-Z0-9_\-]+)', r'|\1(\2)', source)
        
        return source, filename, uptodate

def jinja2_add(value, arg):
    try:
        return int(value) + int(arg)
    except (ValueError, TypeError):
        try:
            return value + arg
        except Exception:
            return value

def jinja2_divisibleby(value, arg):
    try:
        return int(value) % int(arg) == 0
    except (ValueError, TypeError, ZeroDivisionError):
        return False

# GAE webapp template emulator using Jinja2
_environments = {}

class template:
    @staticmethod
    def render(path, values):
        dir_name, file_name = os.path.split(path)
        if dir_name not in _environments:
            loader = DjangoCompatFileSystemLoader(dir_name or '.')
            env = Environment(loader=loader)
            env.filters['slice'] = jinja2_slice
            env.filters['add'] = jinja2_add
            env.filters['divisibleby'] = jinja2_divisibleby
            _environments[dir_name] = env
        
        template_obj = _environments[dir_name].get_template(file_name)
        return template_obj.render(values)

def run_wsgi_app(application):
    pass

