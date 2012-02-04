Longtask for Long running tasks
===============================

Many things take longer than a user is willing to wait. AppEngine with it's request deadline of 10s (later lifted to 30s and then to 60s) is also not willing to wait very long. `longtask` encapsulates a pattern to do the actual work in a taskqueue while providing users with updates (and finally the results) via self reloading webpages.
Per default this is limited to tasks running not more than 10 minutes but with the use of backends this can be incerased to nearly unlimited runtime.

Usage is extremely simple:

    class myTask(longtask.LongRunningTaskHandler):
        def execute_task(self, parameters):
            self.log_progress("Starting", step=0, total_steps=5):
            time.sleep(15)
            for x in range(5):
                self.log_progress("Step %d" % (x + 1), step=(x + 1), total_steps=5)
                time.sleep(15)
            return "<html><body>Done!</body></html>"

Thats basically all you need.
