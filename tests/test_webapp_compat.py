import pytest
from webapp_compat import RequestAdapter, ResponseAdapter, WSGIApplication, jinja2_slice

# 1. Custom Jinja2 slice filter tests
def test_jinja2_slice_filter():
    items = [0, 1, 2, 3, 4, 5]
    assert jinja2_slice(items, ":2") == [0, 1]
    assert jinja2_slice(items, "1:4") == [1, 2, 3]
    assert jinja2_slice(items, "::2") == [0, 2, 4]
    assert jinja2_slice(items, "1:") == [1, 2, 3, 4, 5]
    assert jinja2_slice("hello", "1:4") == "ell"

# 2. RequestAdapter tests
def test_request_adapter():
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    builder = EnvironBuilder(
        path='/testpath',
        method='POST',
        query_string='q=search&tags=python&tags=gae',
        data='username=alice',
        content_type='application/x-www-form-urlencoded',
        environ_base={'REMOTE_ADDR': '127.0.0.1'}
    )
    environ = builder.get_environ()
    wz_req = Request(environ)

    req = RequestAdapter(wz_req)
    assert req.get('q') == 'search'
    assert req.get('username') == 'alice'
    assert req.get('nonexistent', 'default') == 'default'
    assert req.get_all('tags') == ['python', 'gae']
    assert set(req.arguments()) == {'q', 'tags', 'username'}
    assert req.remote_addr == '127.0.0.1'
    assert req.body == b"username=alice"
    assert req.path == '/testpath'

# 3. ResponseAdapter tests
def test_response_adapter():
    resp = ResponseAdapter()
    resp.out.write("hello")
    resp.out.write(" world")
    assert resp.out.getvalue() == "hello world"
    
    resp.headers['Content-Type'] = 'text/html'
    assert resp.headers['Content-Type'] == 'text/html'
    
    resp.set_status(404)
    assert resp.status == 404
    
    resp.redirect("/new-url", permanent=True)
    assert resp.status == 301
    assert resp.headers['Location'] == '/new-url'

# 4. WSGIApplication and regex routing tests
def test_wsgi_application_routing():
    calls = []
    
    from webapp_compat import RequestHandler
    
    class HomeHandler(RequestHandler):
        def get(self):
            calls.append(('home', self.request.path))
            self.response.out.write("home page")
            
    class UserHandler(RequestHandler):
        def get(self, user_id):
            calls.append(('user', user_id))
            self.response.out.write(f"user {user_id}")
            
    class ItemHandler(RequestHandler):
        def post(self, category, item_id):
            calls.append(('item', category, item_id))
            self.response.out.write(f"item {category}/{item_id}")

    # Set up WSGIApplication routing
    app = WSGIApplication([
        (r'/', HomeHandler),
        (r'/user/([^/]+)/?', UserHandler),
        (r'/item/([^/]+)/([^/]+)/?', ItemHandler),
    ], debug=True)

    # Let's mock the WSGI environment call to test WSGIApplication
    def start_response(status, headers):
        pass

    # WSGI call for HomeHandler
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/',
        'wsgi.input': None
    }
    # Mocking standard request environment
    # In WSGI, the application is called with (environ, start_response)
    response_body = app(environ, start_response)
    assert calls == [('home', '/')]
    assert b"home page" in b"".join(response_body)

    # WSGI call for UserHandler
    calls.clear()
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/user/bob/',
        'wsgi.input': None
    }
    response_body = app(environ, start_response)
    assert calls == [('user', 'bob')]
    assert b"user bob" in b"".join(response_body)

    # WSGI call for ItemHandler
    calls.clear()
    environ = {
        'REQUEST_METHOD': 'POST',
        'PATH_INFO': '/item/books/42',
        'wsgi.input': None
    }
    response_body = app(environ, start_response)
    assert calls == [('item', 'books', '42')]
    assert b"item books/42" in b"".join(response_body)


def test_flask_integration():
    from flask import Flask, request, Response
    from webapp_compat import RequestHandler, WSGIApplication
    
    calls = []
    
    class HomeHandler(RequestHandler):
        def get(self):
            calls.append('home')
            self.response.out.write("home page")
            self.response.headers['X-Test-Header'] = 'Home'
            
    class UserHandler(RequestHandler):
        def get(self, user_id):
            calls.append(('user', user_id))
            self.response.out.write(f"user {user_id}")
            
    class ItemHandler(RequestHandler):
        def post(self, category, item_id):
            calls.append(('item', category, item_id))
            self.response.out.write(f"item {category}/{item_id}")
            
    wsgi_app = WSGIApplication([
        (r'/', HomeHandler),
        (r'/user/([^/]+)/?', UserHandler),
        (r'/item/([^/]+)/([^/]+)/?', ItemHandler),
    ], debug=True)
    
    flask_app = Flask(__name__)
    
    @flask_app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH'])
    @flask_app.route('/<path:path>', methods=['GET', 'POST', 'PUT', 'DELETE', 'HEAD', 'OPTIONS', 'PATCH'])
    def catch_all(path):
        status_headers = []
        
        def start_response(status, headers, exc_info=None):
            status_headers.append((status, headers))
            return lambda body_data: None

        environ = request.environ
        response_body_iterable = wsgi_app(environ, start_response)
        
        if not status_headers:
            return Response("Internal Server Error", status=500)
            
        status_str, headers_list = status_headers[0]
        status_code = int(status_str.split()[0])
        response_body = b"".join(response_body_iterable)
        
        return Response(response_body, status=status_code, headers=headers_list)

    client = flask_app.test_client()
    
    # Test HomeHandler (GET /)
    calls.clear()
    resp = client.get('/')
    assert resp.status_code == 200
    assert resp.data == b"home page"
    assert resp.headers.get('X-Test-Header') == 'Home'
    assert calls == ['home']
    
    # Test UserHandler (GET /user/bob/)
    calls.clear()
    resp = client.get('/user/bob/')
    assert resp.status_code == 200
    assert resp.data == b"user bob"
    assert calls == [('user', 'bob')]
    
    # Test ItemHandler (POST /item/books/42)
    calls.clear()
    resp = client.post('/item/books/42')
    assert resp.status_code == 200
    assert resp.data == b"item books/42"
    assert calls == [('item', 'books', '42')]


def test_route_object_routing():
    from webapp_compat import Route, RequestHandler
    
    calls = []
    
    class CourseHandler(RequestHandler):
        def get(self, course_id):
            calls.append(('course', course_id))
            self.response.out.write(f"course {course_id}")
            
    class ModuleHandler(RequestHandler):
        def get(self, course_id, module_id):
            calls.append(('module', course_id, module_id))
            self.response.out.write(f"module {course_id}/{module_id}")

    app = WSGIApplication([
        Route(r'/content/<course_id>', CourseHandler),
        Route(r'/content/<course_id>/<module_id>', handler=ModuleHandler),
    ], debug=True)

    def start_response(status, headers):
        pass

    # Test CourseHandler
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/content/cs101',
        'wsgi.input': None
    }
    response_body = app(environ, start_response)
    assert calls == [('course', 'cs101')]
    assert b"course cs101" in b"".join(response_body)

    # Test ModuleHandler
    calls.clear()
    environ = {
        'REQUEST_METHOD': 'GET',
        'PATH_INFO': '/content/cs101/intro',
        'wsgi.input': None
    }
    response_body = app(environ, start_response)
    assert calls == [('module', 'cs101', 'intro')]
    assert b"module cs101/intro" in b"".join(response_body)


def test_admin_import_courses_handler_optimization():
    from unittest.mock import MagicMock, patch
    from app_controller import AdminImportCoursesHandler
    from webapp_compat import RequestAdapter, ResponseAdapter
    from werkzeug.test import EnvironBuilder
    from werkzeug.wrappers import Request

    # Create mock course data for deleting
    mock_course = MagicMock()
    mock_course.key.id.return_value = 123
    mock_course.key = MagicMock()
    
    mock_module = MagicMock()
    mock_module.key.id.return_value = 456
    mock_module.key = MagicMock()
    
    mock_content = MagicMock()
    mock_content.key = MagicMock()

    # Data to import
    # Format of serialized courses:
    # course_Title
    # course_Description
    # course_Icon
    # course_Index
    # course_Identifier
    # module_Title
    # module_Description
    # module_Icon
    # module_Index
    # module_Identifier
    # content_Title
    # content_Description
    # content_Type
    # content_URL
    # content_Index
    # content_Identifier
    # content_oldurls
    # *****
    # **********
    import_data = (
        "Test Course\n"
        "Description of Test Course\n"
        "icon.png\n"
        "None\n"  # Testing 'None' mapping to 0
        "test-course\n"
        "Test Module\n"
        "Description of Test Module\n"
        "mod-icon.png\n"
        "1\n"
        "test-module\n"
        "Test Content\n"
        "Description of Test Content\n"
        "video\n"
        "http://example.com/video\n"
        "1\n"
        "test-content\n"
        "['http://example.com/old']\n"
        "*****\n"
        "**********\n"
    )

    builder = EnvironBuilder(
        path='/admin/importcourses',
        method='POST',
        data={'s_File_Contents': import_data}
    )
    environ = builder.get_environ()
    wz_req = Request(environ)
    req = RequestAdapter(wz_req)
    resp = ResponseAdapter()

    handler = AdminImportCoursesHandler()
    handler.initialize(req, resp)

    # Patch dependency functions and classes
    with patch('app_controller.getCourses') as mock_get_courses, \
         patch('app_controller.ndb') as mock_ndb, \
         patch('app_controller.Course') as mock_Course_cls, \
         patch('app_controller.Module') as mock_Module_cls, \
         patch('app_controller.Content') as mock_Content_cls:
         
        # Set up mock queries for deleting
        mock_get_courses.return_value = [mock_course]
        
        # Module query
        mock_module_query = MagicMock()
        mock_module_query.order.return_value.fetch.return_value = [mock_module]
        # Content query
        mock_content_query = MagicMock()
        mock_content_query.order.return_value.fetch.return_value = [mock_content]
        
        mock_ndb.Key = MagicMock()
        mock_ndb.Key.return_value = MagicMock()
        
        # Query mock mapping
        mock_Module_cls.query.return_value = mock_module_query
        mock_Content_cls.query.return_value = mock_content_query
        
        # Set up constructor returns
        mock_new_course = MagicMock()
        mock_new_course.key.id.return_value = 999
        mock_Course_cls.return_value = mock_new_course
        
        mock_new_module = MagicMock()
        mock_new_module.key.id.return_value = 888
        mock_Module_cls.return_value = mock_new_module
        
        mock_new_content = MagicMock()
        mock_Content_cls.return_value = mock_new_content

        # Run post handler
        handler.post()

        # Assertions
        # 1. It deletes existing entities using delete_multi
        mock_ndb.delete_multi.assert_called_once()
        deleted_keys = mock_ndb.delete_multi.call_args[0][0]
        assert mock_content.key in deleted_keys
        assert mock_module.key in deleted_keys
        assert mock_course.key in deleted_keys
        
        # 2. It creates new entities
        mock_Course_cls.assert_called_once_with(
            parent=mock_ndb.Key(),
            c_title="Test Course",
            c_description="Description of Test Course",
            c_icon="icon.png",
            c_index=0,  # "None" converted to 0
            c_identifier="test-course"
        )
        mock_new_course.put.assert_called_once()

        mock_Module_cls.assert_called_once_with(
            parent=mock_ndb.Key(),
            m_title="Test Module",
            m_description="Description of Test Module",
            m_icon="mod-icon.png",
            m_index=1,
            m_identifier="test-module"
        )
        mock_new_module.put.assert_called_once()

        mock_Content_cls.assert_called_once_with(
            parent=mock_ndb.Key(),
            c_title="Test Content",
            c_description="Description of Test Content",
            c_type="video",
            c_url="http://example.com/video",
            c_index=1,
            c_identifier="test-content"
        )
        assert mock_new_content.c_oldurls == ['http://example.com/old']
        
        # 3. Content put should NOT be called directly, but batched in put_multi
        mock_new_content.put.assert_not_called()
        mock_ndb.put_multi.assert_called_once_with([mock_new_content])


def test_course_module_properties():
    from datastore import Course, Module
    # Verifying that Course and Module accept string values for icons in Python 3 ndb (replacing BlobProperty with StringProperty)
    course = Course(c_icon="icon.png")
    assert course.c_icon == "icon.png"

    module = Module(m_icon="mod-icon.png")
    assert module.m_icon == "mod-icon.png"


def test_request_handler_redirect():
    from webapp_compat import RequestHandler, ResponseAdapter
    handler = RequestHandler()
    response = ResponseAdapter()
    handler.initialize(None, response)
    handler.redirect("/target-url")
    assert response.status == 302
    assert response.headers['Location'] == "/target-url"
def test_django_compat_template_rendering(tmp_path):
    from webapp_compat import template
    import os
    
    # Create a temporary template file with Django-style template code
    template_content = (
        "{% for item in items %}"
        "{{ forloop.counter }}:{{ item }}"
        "{% if not forloop.last %},{% endif %}"
        "{% endfor %}"
        "|add: {{ items|slice:':2'|length|add:3 }}"
        "|div: {% if 8|divisibleby:4 %}yes{% else %}no{% endif %}"
    )
    
    template_dir = tmp_path
    template_file = template_dir / "test_template.html"
    template_file.write_text(template_content, encoding='utf-8')
    
    values = {
        'items': ['a', 'b', 'c']
    }
    
    rendered = template.render(str(template_file), values)
    # Expected output:
    # 1:a,2:b,3:c
    # |add: 5 (length of items[:2] is 2, plus 3 is 5)
    # |div: yes
    assert rendered == "1:a,2:b,3:c|add: 5|div: yes"


