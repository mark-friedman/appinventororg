from flask import Flask, request, Response
from google.appengine.api import wrap_wsgi_app
from app_controller import application

app = Flask(__name__)

# Increase request size limits to handle course data imports up to 16/32MB
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024    # 32 MB
app.config['MAX_FORM_MEMORY_SIZE'] = 16 * 1024 * 1024  # 16 MB

# Catch-all route to delegate routing to the compatibility WSGIApplication
@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH'])
@app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH'])
def catch_all(path):
    status_headers = []
    
    def start_response(status, headers, exc_info=None):
        status_headers.append((status, headers))
        return lambda body_data: None

    environ = request.environ
    response_body_iterable = application(environ, start_response)
    
    if not status_headers:
        # Default fallback if start_response was not called
        return Response("Internal Server Error", status=500)
        
    status_str, headers_list = status_headers[0]
    status_code = int(status_str.split()[0])
    response_body = b"".join(response_body_iterable)
    
    return Response(response_body, status=status_code, headers=headers_list)

# Wrap Flask's WSGI app with GAE legacy bundled services
app.wsgi_app = wrap_wsgi_app(app.wsgi_app)
