
import functools
from .commands import SHARD_METHODS
from ._compat import basestring, iteritems


class Pipeline(object):
    def __init__(self, shard_api):
        self.shard_api = shard_api
        self.pipelines = {}
        self.__counter = 0
        self.__indexes = {}

    def get_pipeline(self, key):
        name = self.shard_api.get_server_name(key)
        if name not in self.pipelines:
            self.pipelines[name] = self.shard_api.connections[name].pipeline()
        return self.pipelines[name]

    def __record_index(self, pipeline):
        if pipeline not in self.__indexes:
            self.__indexes[pipeline] = [self.__counter]
        else:
            self.__indexes[pipeline].append(self.__counter)
        self.__counter += 1

    def __wrap(self, method, *args, **kwargs):
        try:
            key = args[0]
            assert isinstance(key, basestring)
        except:
            raise ValueError("method '%s' requires a key param as the first argument" % method)
        pipeline = self.get_pipeline(key)
        f = getattr(pipeline, method)
        r = f(*args, **kwargs)
        self.__record_index(pipeline)
        return r

    def __wrap_eval(self, method, script_or_sha, numkeys, *keys_and_args):
        if numkeys != 1:
            raise NotImplementedError("The key must be single string;mutiple keys cannot be sharded")
        key = keys_and_args[0]
        pipeline = self.get_pipeline(key)
        f = getattr(pipeline, method)
        r = f(script_or_sha, numkeys, *keys_and_args)
        self.__record_index(pipeline)
        return r

    def __wrap_tag(self, method, *args, **kwargs):
        key = args[0]
        if isinstance(key, basestring) and '{' in key:
            pipeline = self.get_pipeline(key)
        elif isinstance(key, list) and '{' in key[0]:
            pipeline = self.get_pipeline(key[0])
        else:
            raise ValueError("method '%s' requires tag key params as its arguments" % method)
        method = method.lstrip("tag_")
        f = getattr(pipeline, method)
        r = f(*args, **kwargs)
        self.__record_index(pipeline)
        return r

    def execute(self):
        results = []
        for name, pipeline in iteritems(self.pipelines):
            result = pipeline.execute()
            result = zip(self.__indexes[pipeline], result)
            results.extend(result)

        self.__counter = 0
        self.__indexes = {}

        results.sort(key=lambda x: x[0])
        results = [r[1] for r in results]
        return results

    def __getattr__(self, method):
        if method in SHARD_METHODS:
            return functools.partial(self.__wrap, method)
        elif method in ('eval', 'evalsha'):
            return functools.partial(self.__wrap_eval, method)
        elif method.startswith("tag_"):
            return functools.partial(self.__wrap_tag, method)
        else:
            raise NotImplementedError(
                "method '%s' cannot be pipelined" % method)
