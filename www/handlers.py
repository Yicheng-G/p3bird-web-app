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
import markdown2
from aiohttp import web
from apis import Page, APIError, APIValueError, APIPermissionError, APIResourceNotFoundError
from coroweb import get, post
from models import User, Blog, Comment, next_id
from config import configs

COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


def check_admin(request):
    if not request.__user__ or not request.__user__.admin:
        raise APIPermissionError('Permission Denied')


def get_page_index(page_str):
    p = 1
    try:
        p = int(page_str)
    except ValueError as e:
        pass
    if p < 1:
        p = 1
    return p


def user2cookie(user, max_age):
    """
    Generate cookie str by user.
    """
    # build cookie string by: id-expires-sha1
    expires = str(int(time.time() + max_age))
    s = '{}-{}-{}-{}'.format(user.id, user.password, expires, _COOKIE_KEY)
    items = [user.id, expires, hashlib.sha1(s.encode('utf-8')).hexdigest()]
    return '-'.join(items)


def text2html(text):
    lines = map(
        lambda s: '<p>{}</p>'.format(
            s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        ),
        filter(lambda s: s.strip() != '', text.split('\n'))
    )
    return ''.join(lines)


@asyncio.coroutine
def cookie2user(cookie_str):
    """
    Parse cookie and load user if cookie is valid.
    """
    if not cookie_str:
        return None
    try:
        items = cookie_str.split('-')
        if len(items) != 3:
            return None
        uid, expires, sha1 = items
        if int(expires) < time.time():
            return None
        user = yield from User.find(uid)
        if user is None:
            return None
        s = '{}-{}-{}-{}'.format(uid, user.password, expires, _COOKIE_KEY)
        if sha1 != hashlib.sha1(s.encode('utf-8')).hexdigest():
            logging.info('invalid sha1')
            return None
        user.password = '******'
        return user
    except Exception as e:
        logging.exception(e)
        return None


@get('/')
def index(request):
    summary = 'Lorem ipsum dolor sit amet, consectetur adipisicing elit, ' \
              'sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.'
    blogs = [
        Blog(id='1', name='Test Blog', summary=summary, created_at=time.time()-120),
        Blog(id='2', name='Something New', summary=summary, created_at=time.time()-3600),
        Blog(id='3', name='Learn Swift', summary=summary, created_at=time.time()-7200)
    ]
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }


@get('/blogs')
def get_blogs(*, page=1):
    page_index = get_page_index(page)
    num = yield from Blog.find_number('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = yield from Blog.find_all(orderBy='created_at desc', limit=(p.offset, p.limit))
    return {
        '__template__': 'blogs.html',
        'blogs': blogs
    }


@get('/blogs/{id}')
def get_blog(id):
    blog = yield from Blog.find(id)
    comments = yield from Comment.find_all(
            'blog_id=?', [id], orderBy='created_at desc')
    for comment in comments:
        comment.html_content = text2html(comment.content)
    blog.html_content = markdown2.markdown(blog.content)
    return {
        '__template__': 'blog.html',
        'blog': blog,
        'comments': comments
    }


@get('/register')
def register():
    return {
        '__template__': 'register.html'
    }


@get('/sign_in')
def sign_in():
    return {
        '__template__': 'sign_in.html'
    }


@post('/api/authenticate')
def authenticate(*, email, password):
    if not email:
        raise APIValueError('email', 'Invalid email.')
    if not password:
        raise APIValueError('password', 'Invalid password.')
    users = yield from User.find_all('email=?', [email])
    if len(users) == 0:
        raise APIValueError('email', 'Email not exist.')
    user = users[0]
    # check password:
    sha1 = hashlib.sha1()
    sha1.update(user.id.encode('utf-8'))
    sha1.update(b':')
    sha1.update(password.encode('utf-8'))
    if user.password != sha1.hexdigest():
        raise APIValueError('password', 'Invalid password.')
    # authenticate ok, set cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.password = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/sign_out')
def sign_out(request):
    referer = request.headers.get('Referer')
    logging.debug('sign out to: {}'.format(str(referer)))
    r = web.HTTPFound(referer or '/')
    r.set_cookie(COOKIE_NAME, '-deleted-', max_age=0, httponly=True)
    logging.info('user signed out.')
    return r


@get('/manage/blogs')
def manage_blogs(*, page='1'):
    return {
        '__template__': 'manage_blogs.html',
        'page_index': get_page_index(page)
    }


@get('/manage/blogs/create')
def manage_create_blog():
    return {
        '__template__': 'manage_blog_edit.html',
        'id': '',
        'action': '/api/blogs'
    }


@get('/manage/blogs/edit')
def manage_edit_blog(*, id):
    return {
        '__template__': 'manage_blog_edit.html',
        'id': id,
        'action': '/api/blogs/{}'.format(id)
    }


_RE_EMAIL = re.compile(r'^[a-z0-9\.\-\_]+\@[a-z0-9\-\_]+(\.[a-z0-9\-\_]+){1,4}$')
_RE_SHA1 = re.compile(r'^[0-9a-f]{40}$')


@post('/api/blogs/{id}/comments')
def api_create_comment(id, request, *, content):
    user = request.__user__
    if user is None:
        raise APIPermissionError('Please signin first.')
    if not content or not content.strip():
        raise APIValueError('content')
    blog = yield from Blog.find(id)
    if blog is None:
        raise APIResourceNotFoundError('Blog')
    comment = Comment(
        blog_id=blog.id, user_id=user.id, user_name=user.name, 
        user_image=user.image, content=content.strip()
    )
    yield from comment.save()
    return comment


@post('/api/users')
def api_register_users(*, email, name, password):
    if not name or not name.strip():
        raise APIValueError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIValueError('email')
    if not password or not _RE_SHA1.match(password):
        raise APIValueError('password')
    users = yield from User.find_all('email=?', [email])
    if len(users) > 0:
        raise APIError('register:failed', 'email', 'This email is already in use.')
    uid = next_id()
    sha1_pw = '{}:{}'.format(uid, password)
    password = hashlib.sha1(sha1_pw.encode('utf-8')).hexdigest()
    image = 'http://www.gravatar.com/avatar/{}?d=mm&s=120'.format(
        hashlib.md5(email.encode('utf-8')).hexdigest())
    user = User(
        id=uid, name=name.strip(), email=email, password=password, image=image
    )
    yield from user.save()
    # make session cookie:
    r = web.Response()
    r.set_cookie(COOKIE_NAME, user2cookie(user, 86400), max_age=86400, httponly=True)
    user.password = '******'
    r.content_type = 'application/json'
    r.body = json.dumps(user, ensure_ascii=False).encode('utf-8')
    return r


@get('/api/blogs')
def api_blogs(*, page='1'):
    page_index = get_page_index(page)
    num = yield from Blog.find_number('count(id)')
    p = Page(num, page_index)
    if num == 0:
        return dict(page=p, blogs=())
    blogs = yield from Blog.find_all(
            orderBy='created_at desc', limit=(p.offset, p.limit)
            )
    return dict(page=p, blogs=blogs)


@get('/api/blogs/{id}')
def api_get_blog(*, id):
    blog = yield from Blog.find(id)
    return blog


@post('/api/blogs')
def api_create_blog(request, *, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = Blog(
        user_id=request.__user__.id, user_name=request.__user__.name,
        user_image=request.__user__.image, name=name.strip(),
        summary=summary.strip(), content=content.strip()
    )
    yield from blog.save()
    return blog


@post('/api/blogs/{id}')
def api_update_blog(request, *, id, name, summary, content):
    check_admin(request)
    if not name or not name.strip():
        raise APIValueError('name', 'name cannot be empty.')
    if not summary or not summary.strip():
        raise APIValueError('summary', 'summary cannot be empty.')
    if not content or not content.strip():
        raise APIValueError('content', 'content cannot be empty.')
    blog = yield from Blog.find(id)
    blog.name = name.strip()
    blog.summary = summary.strip()
    blog.content = content.strip()
    yield from blog.update()
    return blog


@post('/api/blogs/{id}/delete')
def api_delete_blog(request, *, id):
    check_admin(request)
    blog = yield from Blog.find(id)
    yield from blog.remove()
    return dict(id=id)
