appinventororg2
==============

This is a fork of the old appinventor.org website.  It has been updated to run on modern python3 and to use modern App Engine infrastructure and deployment methods (gcloud app deploy instead of appcfg).  It is intended to be used as a reference for developers who are working on the new appinventor.org website.

Note that deployment requires uploading the course data (in course_data/appinventor_export.dat), using the `import` command in admin/importcourses on the website.
