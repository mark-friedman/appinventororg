# Google App Engine Python 3 Migration Plan

This plan details the process for upgrading the legacy Python 2.7 App Engine codebase to Python 3.11 and modern Google Cloud APIs.

## Goal Description

The codebase currently uses Python 2.7 and relies heavily on legacy App Engine APIs, including the deprecated `google.appengine.ext.db` datastore API, `google.appengine.ext.webapp` web framework (with over 400 registered request handlers), and standard GAE APIs (Users, Images, Mail, Memcache). 

To ensure the application can run on modern Google Cloud infrastructure, we must:
1. Upgrade the Python runtime from 2.7 to 3.11.
2. Upgrade the web framework to a modern WSGI-compliant framework (Flask).
3. Handle legacy APIs using either a lift-and-shift approach (Legacy Bundled Services SDK) or a full rewrite to modern GCP client libraries.
4. Clean up vendored dependencies in favor of `requirements.txt`.

---

## User Review Required

> [!IMPORTANT]
> **Migration Approach: Lift-and-Shift (Approved)**
> We will proceed with the **Lift-and-Shift** approach to get Python 3 up and running quickly:
> - Use the Google App Engine Legacy Bundled Services SDK (`appengine-python-standard` library).
> - Enable GAE APIs in Python 3 by adding `app_engine_apis: true` to `app.yaml` and wrapping our Flask application using `google.appengine.api.wrap_wsgi_app`.
> - Implement a lightweight compatibility shim `webapp_compat.py` to route all existing `webapp.RequestHandler` classes with zero modifications to the 400+ handlers.

> [!NOTE]
> **Image Storage (Verified)**
> We checked the codebase and verified that user avatar images are stored as `db.BlobProperty` directly in the Datastore. The application uses the GAE Images API (`google.appengine.api.images`) to crop and resize these avatars in-memory before persisting them. Since legacy bundled services will be active, we can keep this GAE Images API logic intact without needing to migrate to Pillow or GCS.

---

## Resolved Questions

* **Python Version**: Target Python 3.11 runtime.
* **Authentication**: Keep using the legacy GAE Users API (`google.appengine.api.users`).
* **Image Manipulation**: Keep legacy GAE Images API since avatars are stored directly as Datastore Blobs.

---

## Proposed Changes

### 1. Configuration & Deployment

#### [MODIFY] [app.yaml](file:///Users/mark/code/democratizecomputing/appinventororg/app.yaml)
* Upgrade runtime: Change `runtime: python27` to `runtime: python311`.
* Remove legacy options: Remove `api_version: 1`, `threadsafe: no`.
* Enable App Engine APIs: Add `app_engine_apis: true` to enable Legacy Bundled Services.
* Add entrypoint: Add `entrypoint: gunicorn -b :$PORT main:app`.
* Simplify handlers: Keep static file directory handlers, but change the script handlers (`script: app_controller.py`) to route all non-static traffic to our Flask app.

#### [NEW] [requirements.txt](file:///Users/mark/code/democratizecomputing/appinventororg/requirements.txt)
* Specify all Python 3 dependencies:
  - `Flask>=3.0.0` (core web framework)
  - `Jinja2>=3.0.0` (template engine)
  - `gunicorn>=21.0.0` (WSGI server for GAE)
  - `appengine-python-standard>=1.0.0` (for legacy bundled APIs)
  - `geopy>=2.4.0` (modern version to replace vendored copy)
  - `feedparser>=6.0.0` (modern version to replace vendored copy)

#### [DELETE] [atom/](file:///Users/mark/code/democratizecomputing/appinventororg/atom/) [NEW] [DELETE] [gdata/](file:///Users/mark/code/democratizecomputing/appinventororg/gdata/) [NEW] [DELETE] [geopy/](file:///Users/mark/code/democratizecomputing/appinventororg/geopy/) [NEW] [DELETE] [feedparser.py](file:///Users/mark/code/democratizecomputing/appinventororg/feedparser.py)
* Remove these vendored directories and files once Pip packages are configured.

---

### 2. Web Application Framework Shim

#### [NEW] [webapp_compat.py](file:///Users/mark/code/democratizecomputing/appinventororg/webapp_compat.py)
Create a compatibility module that emulates the legacy GAE `webapp` framework:
* **`RequestHandler`**: A class wrapping Flask's `request` and `response` objects, providing methods like `self.request.get()`, `self.request.get_all()`, `self.response.out.write()`, and `self.response.redirect()`.
* **`WSGIApplication`**: A dispatcher that matches incoming request paths against regex patterns and routes them to their respective `RequestHandler` classes. It will support path variable capture groups (e.g., `<course_ID>`) and pass them to the handler methods.
* **`template` shim**: Emulates `google.appengine.ext.webapp.template.render(path, values)` using Jinja2, including a custom `slice` filter to support Django-style slices.

#### [NEW] [main.py](file:///Users/mark/code/democratizecomputing/appinventororg/main.py)
Create the main entry point:
* Initialize Flask application.
* Wrap the app with `google.appengine.api.wrap_wsgi_app(app)` to enable Legacy Bundled Services.
* Register a catch-all route `/` and `/<path:path>` that delegates routing to `webapp_compat.WSGIApplication` using the routing table imported from `app_controller.py`.

---

### 3. Application Code Refactoring

#### [MODIFY] [app_controller.py](file:///Users/mark/code/democratizecomputing/appinventororg/app_controller.py)
* Replace webapp imports: Change imports of `google.appengine.ext.webapp` to `webapp_compat`.
* Python 3 syntax changes:
  - Fix any `print` statements to functions.
  - Update dict iterations (e.g., `.iteritems()` -> `.items()`).
  - Convert division expressions where integer division is expected (e.g., `x / y` -> `x // y`).
  - Remove `long` conversions (change `long(...)` to `int(...)`) and remove `L` suffixes from integer literals.
  - Standardize import statements for third-party libraries (e.g., import standard `feedparser` and `geopy`).

#### [MODIFY] [datastore.py](file:///Users/mark/code/democratizecomputing/appinventororg/datastore.py)
* Keep existing `db.Model` and `ndb.Model` definitions since legacy bundled APIs are active.
* Resolve any Python 3 syntax issues (e.g. print statements or class definitions).

---

## Verification Plan

### Local Environment Setup
To run the migrated application locally, you will need the following tools:
1. **gcloud App Engine components**:
   Install Python standard environment support and local development tools:
   ```bash
   gcloud components install app-engine-python app-engine-python-extras
   ```
2. **Python 3.11 Environment**:
   Initialize a Python 3.11 virtual environment and install dependencies:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
3. **Run Locally**:
   Run the local development server using `dev_appserver.py` pointing to Python 3.11:
   ```bash
   dev_appserver.py --runtime_python_path=python3=$(which python3) app.yaml
   ```

### Verification Steps
* **Test-Driven Development (TDD) Workflow (Required)**:
  We will follow a strict TDD process for each shim component:
  1. Write tests in `tests/test_webapp_compat.py` for a feature (e.g. regex routing or custom `slice` filter).
  2. Run `pytest` (asserting failure/no implementation).
  3. Write the implementation code in `webapp_compat.py`.
  4. Run `pytest` again to verify implementation correctness.
* **Browser Verification**:
  Once the local server is running (normally on `http://localhost:8080`), we will use the `chrome-devtools-mcp` browser tool to load and verify key entry pages:
  - `/` (Home)
  - `/gettingstarted`
  - `/outline`
  - `/content`
  We will take screenshots and verify that they render without server errors.
