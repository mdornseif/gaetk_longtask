#!/usr/bin/python
# encoding: utf-8
"""
longtask.py - handling of long running tasks on appengine.

Created by Maximillian Dornseif on 2009-07-19 for HUDORA.
Copyright (c) 2009-2012 HUDORA. All rights reserved.
Available under the Apache License Version 2.0.
"""

# This modules handles Tasks which need to be computed offline.
#
# Many things take longer than a user is willing to wait. Appengine with
# it's request deadline of 10s (later liftet to 30s and then to 60s) is
# also not willing to wait very long. This class encapsulates a pattern to
# provide users with updatates (and finally the results) of long running
# tasks. It is currently limted to tasks running not more than 10 minutes.
#
# The general pattern works like this:
#
# * Browser calls the handler
# * handler fires of a task queue job, does all kind of housekeeping and
#   redirects user to a status page
# * task queue jobs computes (up to 10 Minutes)
# * statuspage is reloaded periodically and informs the user of progress,
#   whenthe task queue job is done the user is redirected to the result page
# * the result page displays the results of the task queue job.
#
# See `LongRunningTaskHandler` for details.

import datetime
import logging
import pickle
import time

import webapp2
from webob.exc import HTTPTemporaryRedirect as HTTP307_TemporaryRedirect
from webob.exc import HTTPFound as HTTP302_Found
from google.appengine.api import memcache
from google.appengine.api import taskqueue
from google.appengine.ext import ndb
from urllib import urlencode


class gaetk_LongTask(ndb.Model):
    """Represents a long running task."""
    # url-path to do statistic for common kinds of tasks
    path = ndb.StringProperty()
    method = ndb.StringProperty(default='GET')
    parameters_blob = ndb.BlobProperty(compressed=True)
    result_blob = ndb.BlobProperty(compressed=True)
    status = ndb.StringProperty(default='ready',
                                choices=['ready', 'started', 'error', 'done', 'showing', 'finished'])
    starttime = ndb.FloatProperty()  # Unix timestamp
    endtime = ndb.FloatProperty()  # Unix timestamp
    # When was the result last accessed
    last_accessed_at = ndb.DateTimeProperty(auto_now=True)
    # Speichern wann und von wem der Datensatz angelegt und geändert wurde. Die Appengine füllt diese
    # Felder automatisch aus.
    updated_at = ndb.DateTimeProperty(auto_now=True)
    updated_by = ndb.UserProperty(required=False, auto_current_user=True)
    created_at = ndb.DateTimeProperty(auto_now_add=True)
    created_by = ndb.UserProperty(required=False, auto_current_user_add=True)

    def __repr__(self):
        return '<LongTask status=%r>' % self.status


class LongRunningTaskHandler(webapp2.RequestHandler):
    """Handles Tasks which need to be computed offline.

    The general pattern works like this:

    * Browser calls the handler
    * handler fires of a task queue job, does all kind of housekeeping and
      redirects user to a status page
    * task queue jobs computes (up to 10 Minutes)
    * statuspage is reloaded periodically and informs the user of progress,
      whenthe task queue job is done the user is redirected to the result page
    * the result page displays the results of the task queue job.

    In most cases you only have to overwrite `execute_task(self, parameters)`
    to implement your calculation. Everything else is handle by `LongRunningTaskHandler`.
    You can periodically call `log_progress()` to keep users updated what is happening.

    WARNING: `execute_task()` *must* be idempotent.
    """

    def get(self, *args, **kwargs):
        """Central dispatching functionality for LongRunningTaskHandler."""

        # Start, task execution, status queries and result display are
        # all passing throug this handler. We use `_longtaskjob` to identify
        # what should be done next.
        # Every long running Task is represented by a `LongTask` entity in the datastore.
        # We are somewhat wasteful in regard to datastore writes since we assume
        # the long running calculation wraped by this handler burns so much CPU
        # nobody would notice the datastore writes.
        # The datastore entity is referenced by `_longtaskid`
        task = None
        if self.request.get('_longtaskid'):
            key = ndb.Key(urlsafe=self.request.get('_longtaskid', ''))
            task = key.get()
        if task:
            self.task = task
            if self.request.get('_longtaskjob') == 'execute':
                self.get_execute(task)
            elif self.request.get('_longtaskjob') == 'query':
                self.get_query(task)
            elif self.request.get('_longtaskjob') == 'showresult':
                # We are called to display the result
                if task.status not in ['done', 'showing', 'finished']:
                    raise RuntimeError("task %s is not 'done'", task)
                task.last_accessed_at = datetime.datetime.now()
                task.put()

                parameters = pickle.loads(task.parameters_blob)
                result = pickle.loads(task.result_blob)
                task.status = 'finished'
                task.put()
                logging.info("showing result of %s", task)
                self.display_result(parameters, result, task)
        else:
            if self.request.get('_longtaskid'):
                # Something went wrong, we couldn't find that Task in the datastore.
                # try to restart the task by redirecting to the original url.
                if self.request.get('_longtaskstartingpoint'):
                    raise HTTP307_TemporaryRedirect(location=self.request.get('_longtaskstartingpoint'))
                # We don't know the original URL so we crash.
                raise RuntimeError("Der Task %s wurde nicht gefunden", self.request.get('_longtaskid'))
            # Prepare a task in the datasotre an fire a task queue
            self.get_start(*args, **kwargs)

    def get_start(self, *args, **kwargs):
        """Prepare a task in the datasotre an fire a task queue."""

        # Start a new task
        paramters = self.prepare_task(*args, **kwargs)
        task = gaetk_LongTask(
            method=self.request.method,
            parameters_blob=pickle.dumps(paramters),
            path=self.request.path, status='ready')
        task.put()
        logging.info("starting %s", task)
        self.task = task
        # Start TaskQueue
        taskqueue.add(url=self.request.path, method='GET',
                  params={'_longtaskjob': 'execute', '_longtaskid': task.key.urlsafe()})
        self.log_progress("Starting", step=0)
        # Redirect to status page
        self._redirect(task, 'query')

    def _redirect(self, task, typ):
        logging.warn("redirect to %s", typ)
        longtaskstartingpoint = self.request.get('_longtaskstartingpoint', self.request.url)
        if task.method == 'PUT':
            # happens usually with file uploads
            parameters = urlencode([('_longtaskjob', typ),
                                    ('_longtaskid', task.key.urlsafe()),
                                   ])
            raise HTTP302_Found(location=self.request.path + '?' + parameters)
        else:
            parameters = urlencode([('_longtaskjob', typ),
                                    ('_longtaskid', task.key.urlsafe()),
                                    # Original URL to restart the Task
                                    ('_longtaskstartingpoint', longtaskstartingpoint)]
                                    # original Parameters
                                   + [(name, self.request.get(name)) for name in self.request.arguments()
                                      if not name.startswith('_') and len(self.request.get(name)) < 512])
            raise HTTP307_TemporaryRedirect(location=self.request.path + '?' + parameters)

    def get_query(self, task):
        """Return current Task Status or redirect to the result."""
        # Statustext - Generic Variant.
        display = dict(info='Status: %s' % task.status, refresh=3)

        if task.status == 'showing':
            # Redirect to result page
            self._redirect(task, 'showresult')

        if task.status == 'done':
            display['info'] = 'Fertig! Wird angezeigt/heruntergeladen.'
            display['info'] = display['info'] + u"<p><progress></progress></p>"
            display['refresh'] = 0

        if task.status == 'ready':
            display['info'] = 'Warte auf Start.'
        if task.status == 'error':
            display['info'] = u'Fehler, wird automatisch erneut versucht.'
        if task.status == 'started':
            # We are running. Read current Status Message from memcache and prepare for display
            display['statusinfo'] = memcache.get("longtask_status_%s" % task.key.urlsafe())
            if not display['statusinfo']:
                display['statusinfo'] = {}
            logging.info("%r", display['statusinfo'].get('message'))
            display['info'] = u'%s<br>Läuft seit %d Sekunden.' % (display['statusinfo'].get('message'),
                                                                  time.time() - task.starttime)
            # Display Progress Bar if sufficient data is available
            # TODO: "AJAX" based progress display
            if display['statusinfo'].get('total_steps'):
                display['info'] = display['info'] + u"""<p>Fortgang:
  <progress value="%d" max="%d">%d %%</progress></p>
""" % (display['statusinfo'].get('step'),
      display['statusinfo'].get('total_steps'),
      int(display['statusinfo'].get('step') * 100.0 / display['statusinfo'].get('total_steps')))
            else:
                # indetermine progress bar
                display['info'] = display['info'] + u"<p><progress></progress></p>"

        self.render_status(display, task)

        if task.status == 'done':
            # We are done!
            task.status = 'showing'
            task.put()

    def get_execute(self, task):
        """Handle calling of execute_task()."""

        # We are being called by the task queue machinery and thus have 10
        # minutes to do our work.
        logging.info("executing %s", task)
        if task.status not in ['ready', 'error']:
            # strange internal error
            # but the reason might be a timeout which kept us from updating the state to error
            if task.status == 'started' and task.starttime + (11 * 60) > time.time():
                # on taskqueues this should completely aboid dupes, on backends it might not
                logging.info("restarting task aufter timeout")
            else:
                raise RuntimeError("task %s is not 'ready'", task)
            # load
        # first note that the task has started. We do a async write, so we don't have to wait
        # for the datastore. Since `execute_task()` is idempotent this shoult never result in
        # anything messy.
        task.status = 'started'
        task.starttime = time.time()
        task.put()
        self.task = task
        logging.info("started %s", task)

        # Decode Parameters from Datastore and execute the actual task.
        parameters = pickle.loads(task.parameters_blob)
        try:
            result = self.execute_task(parameters)
            logging.info("returned from execution %s", task)
            key = ndb.Key(urlsafe=self.request.get('_longtaskid', ''))
            task = key.get()
            task.result_blob = pickle.dumps(result)
            task.status = 'done'
            task.endtime = time.time()
            task.put()
        except Exception, msg:
            # If an exception occured, note htat in the Datastore an re raise an error.
            # We could probably add one day some fancy error logging.
            logging.error(msg)
            key = ndb.Key(urlsafe=self.request.get('_longtaskid', ''))
            task = key.get()
            task.status = 'error'
            task.put()
            raise

        logging.info("finishing %s", task)

    def post(self, *args, **kwargs):
        """Allow firing of longtasks via POST requests."""
        self.get(*args, **kwargs)

    def prepare_task(self, *args, **kwargs):
        """Prepares a task to be started. Returnes a Dict of Data to be given to the Task."""
        # move all HTTP-parameters not starting with `_` in the parameters dict.
        # This dict will be used to call `execute_task()`.
        # Overwrite `prepare_task()` if you need fancier preprocessing.
        parameters = dict([(name, self.request.get(name)) for name in self.request.arguments()
                            if not name.startswith('_')])
        parameters.update(kwargs)
        for i, arg in enumerate(args):
            parameters["arg%d" % i] = arg
        return parameters

    def execute_task(self, parameters):
        """Is called to do the actual work."""
        raise NotImplementedError

    def render_status(self, display, task):
        # Generate HTML output
        html = u"""<html><head><meta http-equiv="refresh" content="%(refresh)s"><title>Task Status</title></head>
<body><p>%(info)s</p>
</p></body></html>""" % display
        self.response.write(html)

    def display_result(self, paramters, result, task):
        """Is called after Task completion with the output of `execute_task()`"""
        # can be overwritten to do fancier output processing.
        self.response.out.write(result)

    def log_progress(self, message, step=0, total_steps=0):
        """Communicate progress to the user.

        Whenever possible you should give the number of the step you are preforming and of the
        estimated number of total steps. This allows for a fancier progress display.
        E.g.:

            self.log_progress(u"Starting", 1, 12)
            ...
            self.log_progress(u"Doing Dtuff", 2, 12)
            ...
            self.log_progress(u"Finalizing", 12, 12)

        Alternatively you can provide the class variable `total_steps`
        """
        if not total_steps:
            total_steps = getattr(self, 'total_steps', 0)
        memcache.set("longtask_status_%s" % self.task.key.urlsafe(),
                     dict(message=unicode(message), step=step, total_steps=total_steps))

# TODO: garbage collection
