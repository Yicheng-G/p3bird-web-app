#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Default configurations.
"""

__author__ = 'Yicheng Guo'


configs = {
    'debug': True,
    'db': {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'ycguo',
        'password': '',
        'db': 'p3bird',
    },
    'session': {
        'secret': 'p3bird'
    }
}
