#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Yicheng Guo'

import asyncio
import os
import inspect
import logging
import functools
from urllib import parse
from aiohttp import web
from apis import APIError


def get(path):
    """
    Define decorator @get('/path')
    :param path: url
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.__method__ = 'GET'
        wrapper.__route__ = path
        return wrapper
    return decorator


def post(path):
    """
    Define decorator @post('/path')
    :param path: url
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.__method__ = 'POST'
        wrapper.__route__ = path
        return wrapper
    return decorator


def get_required_kwargs(fn):
    pass


def get_named_kwargs(fn):
    pass


def has_named_kwargs(fn):
    pass


def has_var_kwargs(fn):
    pass


def has_request_arg(fn):
    pass


class RequestHandler(object):
    """
    Packing callable functions which handle requests.
    A func packed becomes a co-routine function and returns a StreamResponse derived instance.
    """
    def __init__(self, app, fn):
        self._app = app
        self._func = fn
        self._has_request_arg = has_request_arg(fn)
        self._has_var_kwargs = has_var_kwargs(fn)
        self._has_named_kwargs = has_named_kwargs(fn)
        self._named_kwargs = get_named_kwargs(fn)
        self._required_kwargs = get_required_kwargs(fn)

    @asyncio.coroutine
    def __call__(self, request):
        kw = None
        if self._has_var_kwargs or self._has_named_kwargs or self._required_kwargs:
            if request.method == 'POST':
                if not request.content_type:
                    return web.HTTPBadRequest('Missing Content-Type.')
                ct = request.content_type.lower()
                if ct.startswith('application/json'):
                    params = yield from request.json()
                    if not isinstance(params, dict):
                        return web.HTTPBadRequest('Json body much be a object.')
                    kw = params
                elif ct.startswith('application/x-www-from-urlencoded') or \
                        ct.startswith('multipart/form-data'):
                    params = yield from request.post()
                else:
                    return web.HTTPBadRequest(
                        'Unsupported Content-Type: {}'.format(request.content_type)
                    )
            if request.method == 'GET':
                qs = request.query_string
                if qs:
                    kw = dict()
                    for k, v in parse.parse_qs(qs, True).items():
                        kw[k] = v[0]
        if kw is None:
            kw = dict(**request.match_info)
        else:
            if not self._has_var_kwargs and self._named_kwargs:
                # remove all unnamed kw:
                copy = dict()
                for name in self._named_kwargs:
                    if name in kw:
                        copy[name] = kw[name]
                kw = copy
            # check named arg:
            for k, v in request.match_info.items():
                if k in kw:
                    logging.warning(
                        'Duplicate arg name in named arg and kw args: {}'.format(k)
                    )
                    kw[k] = v
        if self._has_request_arg:
            kw['request'] = request
        # check required kw:
        if self._required_kwargs:
            for name in self._required_kwargs:
                if not name in kw:
                    return web.HTTPBadRequest(
                        'Missing argument: {}'.format(name)
                    )
        logging.info('call with args: {}'.format(str(kw)))
        try:
            r = yield from self._func(**kw)
            return r
        except APIError as e:
            return dict(error=e.error, data=e.data, message=e.message)


def add_static(app):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    app.router.add_static('/static/', path)
    logging.info('add static {} ==> {}'.format('/static/', path))


def add_route(app, fn):
    """
    Register the func to app.router
    The function should be decorated by @get or @post
    :param app: application
    :param fn: function
    """
    method = getattr(fn, '__method__', None)
    path = getattr(fn, '__route__', None)
    if path is None or method is None:
        raise ValueError('@get / @post not applied on func: {}'.format(fn))
    if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
        fn = asyncio.coroutine(fn)
    logging.info(
        'add route {} {} ==> {}({})'.format(
            method, path, fn.__name__,
            ', '.join(inspect.signature(fn).parameters.keys())
        )
    )
    app.router.add_route(method, path, RequestHandler(app, fn))


def add_routes(app, module_name):
    """
    Register all public funcs in module to app,router automatically
    :param app: application
    :param module_name: module name
    """
    n = module_name.rfind('.')
    if n == -1:
        mod = __import__(module_name, globals(), locals())
    else:
        name = module_name[n+1:]
        mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
    for attr in dir(mod):
        if attr.startswith('_'):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            method = getattr(fn, '__module', None)
            path = getattr(fn, '__route__', None)
            if method and path:
                add_route(app, fn)