Longtask for Long running tasks
===============================

Many things take longer than a user is willing to wait. See [this Blogposting][1] for further references. AppEngine with it's request deadline of 10s (later lifted to 30s and then to 60s) is also not willing to wait very long. `longtask` encapsulates a pattern to do the actual work in a taskqueue while providing users with updates (and finally the results) via self reloading webpages.
Per default this is limited to tasks running not more than 10 minutes but with the use of backends this can be incerased to nearly unlimited runtime.

Usage is extremely simple:

    class myTask(longtask.LongRunningTaskHandler):
        def execute_task(self, parameters):
            self.log_progress("Starting", step=0, total_steps=5)
            time.sleep(15)
            for x in range(5):
                self.log_progress("Step %d" % (x + 1), step=(x + 1), total_steps=5)
                time.sleep(15)
            return "<html><body>Done!</body></html>"

Thats basically all you need.


Installation
------------

I strongly suggest to create a `./lib/` directory within your AppEngine application and put `gae_longtask` there.


    mkdir -p lib
    git submodule add git://github.com/mdornseif/gaetk_longtask.git lib/gaetk_longtask
    echo "import os.path" > lib/__init__.py
    echo "import site" >> lib/__init__.py
    echo "site.addsitedir(os.path.dirname(__file__))" >> lib/__init__.py
    echo "./gaetk_longtask" >> lib/submodules.pth

Now within your application first `import lib` to initialize the library directory, then `import longtask`.


See also
--------

* [Long running Tasks for Websites][1]

[1]: http://mdornseif.github.com/2012/02/04/long_tasks.html


[![Bitdeli Badge](https://d2weczhvl823v0.cloudfront.net/mdornseif/gaetk_longtask/trend.png)](https://bitdeli.com/free "Bitdeli Badge")

