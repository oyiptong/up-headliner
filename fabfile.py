import time
from datetime import datetime
from distutils.util import strtobool
from functools import wraps

from fabric import colors
from fabric.api import env, run, local, require, put

env.path = "/var/www/headliner"
env.user = "headliner"
env.num_keep_releases = 10
env.use_ssh_config = True
env.release = time.strftime("%Y-%m-%d-%H-%M-%S", datetime.utcnow().timetuple())


def section(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        print colors.cyan('Running section "{}"'.format(f.__name__), bold=True)
        f(*args, **kwargs)
        print
    return wrapper


### Utility

@section
def upload_from_git():
    """
    Create tarball, send over the wire and untar
    """
    require("release", provided_by=[setup, deploy_cold, deploy])
    local("git archive --format=tar master | bzip2 > %(release)s.tar.bz2" % env)
    put("%(release)s.tar.bz2" % env, "/tmp/")

    run("mkdir %(path)s/%(release)s" % env)
    run("cd %(path)s/%(release)s && tar xjf /tmp/%(release)s.tar.bz2" % env)
    run("rm /tmp/%(release)s.tar.bz2" % env)

    local("rm %(release)s.tar.bz2" % env)


@section
def set_symlinks():
    require("release", provided_by=[setup, deploy, deploy_cold])
    run("if [ -h %(path)s/previous ]; then rm %(path)s/previous; fi" % env)
    run("if [ -h %(path)s/current ]; then mv %(path)s/current %(path)s/previous; fi" % env)
    run("ln -s %(path)s/%(release)s %(path)s/current" % env)


@section
def setup_virtualenv():
    require("release", provided_by=[setup, deploy, deploy_cold])
    run("cd %(path)s/%(release)s && MOZ_UPHEADLINER_PROD=1 ./setup-project.sh" % env)


@section
def clean_release_dir():
    """
    Delete releases if the number of releases to keep has gone beyond the threshold set by num_keep_releases
    """
    if env.num_keep_releases > 1:
        # keep at least 2 releases: one previous and one current
        releases = run("find %(path)s -maxdepth 1 -mindepth 1 -type d | sort" % env).split()
        if len(releases) > env.num_keep_releases:
            delete_num = len(releases) - env.num_keep_releases
            delete_list = " ".join(releases[:delete_num])
            run("rm -rf {0}".format(delete_list))


### Tasks

@section
def deploy_cold():
    """
    Deploy code but don"t change current running version
    """
    upload_from_git()
    setup_virtualenv()


@section
def setup():
    """
    Create directories and deploy cold
    """
    run("mkdir -p %(path)s" % env)
    deploy_cold()


@section
def deploy():
    """
    Deploy code, set symlinks and restart supervisor
    """
    deploy_cold()
    clean_release_dir()
    set_symlinks()
    restart_processes()


@section
def restart_processes():
    run("sudo supervisorctl restart headliner:*")


### Development

def to_bool(value):
    if not isinstance(value, bool):
        return strtobool(value)
    else:
        return value


def build():
    test()
    flake()
    package()


@section
def test(config="nose.cfg", debug_errors=False, debug_failures=False):
    """
    Run automated tests.
    If debug_errors is provided as a truey value, will drop on debug prompt as soon as an exception bubbles out from the tests.
    If debug_failures is provided as a truey value, will drop on debug prompt as soon as an assertion fails.
    """
    command = "nosetests --config={}".format(config)
    if to_bool(debug_errors):
        command += " --ipdb"
    if to_bool(debug_failures):
        command += " --ipdb-failures"
    local(command)


@section
def flake(config="flake8.cfg"):
    local("flake8 . --config={}".format(config))


@section
def package(clean=True):
    if to_bool(clean):
        local("rm -rf build/")
    local("python setup.py build")
