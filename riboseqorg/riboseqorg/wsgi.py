"""
WSGI config for riboseqorg project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.1/howto/deployment/wsgi/
"""
# Added by Anmol
import os, sys, subprocess
PROJECT_DIR = '/home/DATA/www/RiboSeqOrg-DataPortal/riboseqorg'
sys.path.insert(0, PROJECT_DIR)
def execfile(filename):
    globals = dict( __file__ = filename )
    exec( open(filename).read(), globals )

activate_this = os.path.join( PROJECT_DIR, '../riboseq_venv/bin', 'activate_this.py' )
execfile( activate_this )

# End

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "riboseqorg.settings")

application = get_wsgi_application()