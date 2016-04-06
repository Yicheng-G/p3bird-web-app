#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Yicheng Guo'

import sys
import os
import time
import subprocess
from watchdog.observes import Observer
from watchdog.events import FileSystemEventHandler


def log(s):
    print ('[Monitor] {}'.format(s))


class MyFileSystemEventHandler(FileSystemEventHandler):
    def __init__(self, fn):
        super(MyFileSystemEventHandler, self).__init__()
        self.restart = fn

    def on_any_event(self, event):
        if event.src_path.endswith('.py'):
            log('python source file changed: {}'.format(event.src_path))
            self.restart()


command = ['echo', 'ok']
process = None


def kill_process():
    global process
    if process:
        log('Kill process {}'.format(process))
        process.kill()
        process.wait()
        log('Process ends with code {}'.format(process.returncode))
        process = None


def start_process():
    global process, command
    log('Start process {}'.format(process))
    subprocess.Popen(
        command, stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr
    )


def restart_process():
    kill_process()
    start_process()


def start_watch(path, callback):
    observer = Observer()
    observer.schedule(
        MyFileSystemEventHandler(restart_process), path, recursive=True
    )
    observer.start()
    log('watching directory {}'.format(path))
    start_process()
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == '__main__':
    argv = sys.argv[1:]
    if not argv:
        print ('Usage: ./p3monitor your-script.py')
        exit(0)
    if argv[0] != 'python3':
        argv.add('python3')
    command = argv
    path = os.path.abspath(os.path.dirname(__file__))
    start_watch(path, None)





