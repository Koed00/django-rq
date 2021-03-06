import importlib
import logging
from optparse import make_option
import multiprocessing

from django.core.management.base import BaseCommand
from django_rq.queues import get_queues
from redis.exceptions import ConnectionError
from rq import use_connection
from rq.utils import ColorizingStreamHandler




# Setup logging for RQWorker if not already configured
logger = logging.getLogger('rq.worker')
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(fmt='%(asctime)s %(message)s',
                                  datefmt='%H:%M:%S')
    handler = ColorizingStreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)


# Copied from rq.utils
def import_attribute(name):
    """Return an attribute from a dotted path name (e.g. "path.to.func")."""
    module_name, attribute = name.rsplit('.', 1)
    module = importlib.import_module(module_name)
    return getattr(module, attribute)


class Command(BaseCommand):
    """
    Runs RQ workers on specified queues. Note that all queues passed into a
    single rqworker command must share the same connection.

    Example usage:
    python manage.py rqworker high medium low
    """
    option_list = BaseCommand.option_list + (
        make_option(
            '--burst',
            action='store_true',
            dest='burst',
            default=False,
            help='Run worker in burst mode'
        ),
        make_option(
            '--worker-class',
            action='store',
            dest='worker_class',
            default='rq.Worker',
            help='RQ Worker class to use'
        ),
        make_option(
            '--name',
            action='store',
            dest='name',
            default=None,
            help='Name of the worker'
        ),
        make_option(
            '--count',
            action='store',
            dest='count',
            default=1,
            help='Amount of workers'
        ),
    )
    args = '<queue queue ...>'

    def handle(self, *args, **options):
        worker_count = int(options['count'])
        if worker_count > 1:
            jobs = []
            name = options['name']
            for i in range(worker_count):
                if name:
                    options['name'] = '{}.{}'.format(name, i)
                p = multiprocessing.Process(target=self.worker, args=args, kwargs=options)
                jobs.append(p)
                p.start()
        else:
            self.worker(*args, **options)

    @staticmethod
    def worker(*args, **options):
        try:
            # Instantiate a worker
            worker_class = import_attribute(options.get('worker_class', 'rq.Worker'))
            queues = get_queues(*args)
            w = worker_class(queues, connection=queues[0].connection, name=options['name'])

            # Call use_connection to push the redis connection into LocalStack
            # without this, jobs using RQ's get_current_job() will fail
            use_connection(w.connection)
            w.work(burst=options.get('burst', False))
        except ConnectionError as e:
            print(e)
