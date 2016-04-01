#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'Yicheng Guo'

import asyncio, logging
import aiomysql


def log(sql, args=()):
    logging.info('SQL: {}'.format(sql))


@asyncio.coroutine
def create_pool(loop, **kw):
    logging.info('create data base connecting pool...')
    global __pool
    __pool = yield from aiomysql.create_pool(
        host=kw.get('host', 'localhost'),
        port=kw.get('port', '3306'),
        user=kw['user'],
        password=kw['password'],
        db=kw['db'],
        charset=kw.get('charset', 'utf8'),
        autocommit=kw.get('autocommit', True),
        maxsize=kw.get('maxsize', 10),
        minsize=kw.get('minsize', 1),
        loop=loop
    )


@asyncio.coroutine
def select(sql, args, size=None):
    log(sql, args)
    with (yield from __pool) as conn:
        cur = yield from conn.cursor(aiomysql.DictCursor)
        yield from cur.execute(sql.replace('?', '%s'), args or ())
        if size:
            rs = yield from cur.fetchmany(size)
        else:
            rs = yield from cur.fetchall()
        yield from cur.close()
        logging.info('rows returned: {}'.format(len(rs)))
        return rs


@asyncio.coroutine
def execute(sql, args):
    log(sql, args)
    with (yield from __pool) as conn:
        try:
            cur = yield from conn.cursor()
            yield from cur.execute(sql.replace('?', '%s'), args or ())
            affected = cur.rowcount
            print(cur)
            yield from cur.close()
        except BaseException:
            raise
        return affected


def create_args_string(num):
    args_str = []
    for n in range(num):
        args_str.append('?')
    return ','.join(args_str)


class Field(object):
    def __init__(self, name, column_type, primary_key, default):
        self.name = name
        self.column_type = column_type
        self.primary_key = primary_key
        self.default = default

    def __str__(self):
        return '<{}, {}: {}>'.format(
            self.__class__.__name__, self.column_type, self.name
        )


class StringField(Field):
    def __init__(self, name=None, primary_key=False,
                 default=None, ddl='varchar(100)'):
        super().__init__(name, ddl, primary_key, default)


class BooleanField(Field):
    def __init__(self, name=None, default=False):
        super().__init__(name, 'boolean', False, default)


class IntegerField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'bigint', primary_key, default)


class FloatField(Field):
    def __init__(self, name=None, primary_key=False, default=0):
        super().__init__(name, 'real', primary_key, default)


class TextField(Field):
    def __init__(self, name=None, default=None):
        super().__init__(name, 'text', False, default)


class ModelMetaclass(type):
    def __new__(mcs, name, bases, attrs):
        if name == 'Model':
            return type.__new__(mcs, name, bases, attrs)
        table_name = attrs.get('__table__', None) or name
        logging.info('find model: {} (table: {})'.format(name, table_name))

        mapping = dict()
        fields = []
        primary_key = None
        for k, v in attrs.items():
            if isinstance(v, Field):
                logging.info('    find mapping: {} ==> {}'.format(k, v))
                mapping[k] = v
                if v.primary_key:
                    if primary_key:
                        raise RuntimeError(
                            'Duplicated primary key for filed: {}'.format(k)
                        )
                    primary_key = k
                else:
                    fields.append(k)
        if not primary_key:
            raise RuntimeError('Primary key not found.')
        for k in mapping.keys():
            attrs.pop(k)
        escaped_fields = list(map(lambda f: '`{}`'.format(f), fields))
        attrs['__mapping__'] = mapping
        attrs['__table__'] = table_name
        attrs['__primary_key__'] = primary_key
        attrs['__fields__'] = fields
        attrs['__select__'] = 'select `{}`, {} from {}'.format(
            primary_key, ', '.join(escaped_fields), table_name
        )
        attrs['__insert__'] = 'insert into `{}` ({}, `{}`) values ({})'.format(
            table_name, ', '.join(escaped_fields),
            primary_key, create_args_string(len(escaped_fields) + 1)
        )
        attrs['__update__'] = 'update `{}` set {} where `{}`=?'.format(
            table_name,
            ', '.join(map(lambda f: '`{}`=?'.format(mapping.get(f).name or f), fields)),
            primary_key
        )
        attrs['__delete__'] = 'delete from `{}` where `{}`=?'.format(
            table_name, primary_key
        )
        return type.__new__(mcs, name, bases, attrs)


class Model(dict, metaclass=ModelMetaclass):
    def __init__(self, **kwargs):
        super(Model, self).__init__(**kwargs)

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError:
            raise AttributeError(r"Model object has no attribute {}".format(item))

    def __setattr__(self, key, value):
        self[key] = value

    def get_value(self, key):
        return getattr(self, key, None)

    def get_value_or_default(self, key):
        value = getattr(self, key, None)
        if value is None:
            field = self.__mapping__[key]
            if field.default is not None:
                value = field.default() if callable(field.default) else field.default
                logging.debug('using default value for {}: {}'.format(key, str(value)))
                setattr(self, key, value)
        return value

    @classmethod
    @asyncio.coroutine
    def find_all(cls, where=None, args=None, **kwargs):
        """ find pbjects by where clause."""
        sql = [cls.__select__]
        if where:
            sql.append('where')
            sql.append(where)
        if args is None:
            args = []
        order_by = kwargs.get('orderBy', None)
        if order_by:
            sql.append('order by')
            sql.append(order_by)
        limit = kwargs.get('limit', None)
        if limit:
            sql.append('limit')
            if isinstance(limit, int):
                sql.append('?')
                args.append(limit)
            elif isinstance(limit, tuple) and len(limit) == 2:
                sql.append('?, ?')
                args.extend(limit)
            else:
                raise ValueError('Invalid limit value: {}'.format(str(limit)))
        rs = yield from select(' '.join(sql), args)
        return [cls(**r) for r in rs]  # cls(**r): unpack dict r, passing contents as kw args

    @classmethod
    @asyncio.coroutine
    def find(cls, pk):
        """ find object by primary key
        :param pk: primary key
        :return:
        """
        rs = yield from select(
            '{} where `{}`=?'.format(cls.__select__, cls.__primary_key__),
            [pk], 1
        )
        if len(rs) == 0:
            return None
        return cls(**rs[0])

    @asyncio.coroutine
    def save(self):
        args = list(map(self.get_value_or_default, self.__fields__))
        args.append(self.get_value_or_default(self.__primary_key__))
        rows = yield from execute(self.__insert__, args)
        if rows != 1:
            logging.warning(
                'failed to insert by primary key, affected rows: {}'.format(rows)
            )

    @asyncio.coroutine
    def update(self):  # same name to dict.update, override
        args = list(map(self.get_value, self.__fields__))
        args.append(self.get_value(self.__primary_key__))
        rows = yield from execute(self.__update__, args)
        if rows != 1:
            logging.warning(
                'failed to update by primary key, affected rows: {}'.format(rows)
            )

    @asyncio.coroutine
    def remove(self):
        args = [self.get_value(self.__primary_key__)]
        rows = yield from execute(self.__delete__, args)
        if rows != 1:
            logging.warning(
                'failed to remove by primary key, affected rows: {}'.format(rows)
            )
