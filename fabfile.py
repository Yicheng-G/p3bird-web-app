#!/use/bin/env python2.7

import os
import re
from datetime import datetime
from fabric.api import *

env.user = 'ycguo'
env.sudo_user = 'ycguo'
env.password = 'KebeNebe7445'
env.hosts = ['137.138.216.51']
env.shell = "/bin/bash -l -i -c"

db_user = 'ycguo'
db_password = ''

_TAR_FILE = 'dict-p3bird.tar.gz'
_REMOTE_TMP_TAR = '/home/ycguo/tmp/{}'.format(_TAR_FILE)
_REMOTE_BASE_DIR = '/home/ycguo/srv/p3bird'


def _current_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _now():
   return datetime.now().strftime('%y-%m-%d_%H.%M.%S')


def build():
    """ build p3bird package. """

    www_dir = os.path.join(_current_dir(), 'www')
    tar_file_path = os.path.join(_current_dir(), 'dist', _TAR_FILE)
    include = ['static', 'templates', '*.py']
    exclude = ['test', '.*', '*.pyc', '*.pyo', '__pycache__']

    with lcd(www_dir):
        cmd = ['tar', '--dereference', '-czvf', tar_file_path]
        cmd.extend(['--exclude=\'{}\''.format(ex) for ex in exclude])
        cmd.extend(include)
        local(' '.join(cmd))


def deploy():
    """ deploy new p3bird package on server. """

    # update compressed p3dird package
    run('rm -f {}'.format(_REMOTE_TMP_TAR))
    put('dist/{}'.format(_TAR_FILE), _REMOTE_TMP_TAR)

    # umcompress new package to new dir tagged by time
    new_dir = 'www-{}'.format(_now())
    with cd(_REMOTE_BASE_DIR):
        sudo('mkdir {}'.format(new_dir))
    with cd('{}/{}'.format(_REMOTE_BASE_DIR, new_dir)):
        sudo('tar -xzvf {}'.format(_REMOTE_TMP_TAR))

    # link www to new package, set owner
    with cd(_REMOTE_BASE_DIR):
        sudo('rm -rf www')
        sudo('ln -s {} www'.format(new_dir))
        # sudo('chown p3bird:p3bird www')
        # sudo('chown -R p3bird:p3bird {}'.format(new_dir))

    # call supervisor and nginx
    with settings(warn_only=True):
        sudo('pysudo supervisorctl stop p3bird')
        sudo('pysudo supervisorctl start p3bird')
        sudo('/etc/init.d/nginx reload')
