#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
url handlers
"""

__author__ = 'Yicheng Guo'


import re
import time
import json
import logging
import hashlib
import base64
import asyncio
from coroweb import get, post
from models import User, Blog, Comment, next_id


@get('/')
@asyncio.coroutine
def index(request):
    users = yield from User.find_all()
    return {
        '__template__': 'test.html',
        'users': users
    }

