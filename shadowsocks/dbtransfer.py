#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import cymysql
import time
import sys
import socket
import config
import json


class DbTransfer(object):

    instance = None

    def __init__(self):
        self.last_get_transfer = {}

    @staticmethod
    def get_instance():
        if DbTransfer.instance is None:
            DbTransfer.instance = DbTransfer()
        return DbTransfer.instance

    @staticmethod
    def send_command(cmd):
        data = ''
        try:
            cli = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            cli.settimeout(1)
            cli.sendto(cmd, ('%s' % (config.MANAGE_BIND_IP), config.MANAGE_PORT))
            data, addr = cli.recvfrom(1500)
            cli.close()
            # TODO: bad way solve timed out
            time.sleep(0.05)
        except:
            logging.warn('send_command response')
        return data

    @staticmethod
    def get_servers_transfer():
        dt_transfer = {}
        cli = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        cli.settimeout(2)
        cli.sendto('transfer: {}', ('%s' % (config.MANAGE_BIND_IP), config.MANAGE_PORT))
        bflag = False
        while True:
            data, addr = cli.recvfrom(1500)
            if data == 'e':
                break
            data = json.loads(data)
            dt_transfer.update(data)
        cli.close()
        return dt_transfer


    def push_db_all_user(self):
        dt_transfer = self.get_servers_transfer()
        query_head = 'UPDATE member'
        query_sub_when = ''
        query_sub_when2 = ''
        query_sub_in = None
        last_time = time.time()
        for id in dt_transfer.keys():
            query_sub_when += ' WHEN %s THEN flow_up+%s' % (id, 0) # all in d
            query_sub_when2 += ' WHEN %s THEN flow_down+%s' % (id, dt_transfer[id])
            if query_sub_in is not None:
                query_sub_in += ',%s' % id
            else:
                query_sub_in = '%s' % id
        if query_sub_when == '':
            return
        query_sql = query_head + ' SET flow_up = CASE port' + query_sub_when + \
                    ' END, flow_down = CASE port' + query_sub_when2 + \
                    ' END, lastConnTime = ' + str(int(last_time)) + \
                    ' WHERE port IN (%s)' % query_sub_in
        # print query_sql
        try:
            conn = cymysql.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT, user=config.MYSQL_USER,
                                   passwd=config.MYSQL_PASS, db=config.MYSQL_DB, charset='utf8')
            cur = conn.cursor()
            cur.execute(query_sql)
            cur.close()
            conn.commit()
            conn.close()
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.warn('db push_db_all_user: %s' % e)

    @staticmethod
    def pull_db_all_user():
        try:
            conn = cymysql.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT, user=config.MYSQL_USER,
                                   passwd=config.MYSQL_PASS, db=config.MYSQL_DB, charset='utf8')
            cur = conn.cursor()
            cur.execute("SELECT port, flow_up, flow_down, transfer, sspwd, enable, method, plan FROM member")
            rows = []
            for r in cur.fetchall():
                rows.append(list(r))
            cur.close()
            conn.close()
            return rows
        except Exception as e:
            import traceback
            traceback.print_exc()
            logging.warn('db pull_db_all_user: %s' % e)

    @staticmethod
    def del_server_out_of_bound_safe(rows):
        for row in rows:
            server = json.loads(DbTransfer.get_instance().send_command('stat: {"server_port":%s}' % row[0]))
            if server['stat'] != 'ko':
                if row[5] == 0:
                    #stop disable or switch off user
                    logging.info('db stop server at port [%s] reason: disable' % (row[0]))
                    DbTransfer.send_command('remove: {"server_port":%s}' % row[0])
                elif row[1] + row[2] >= row[3]:
                    #stop out bandwidth user
                    logging.info('db stop server at port [%s] reason: out bandwidth' % (row[0]))
                    DbTransfer.send_command('remove: {"server_port":%s}' % row[0])
                if server['password'] != row[4] or row[6] is not None and server['method'] != row[6]:
                    #password or method changed
                    logging.info('db stop server at port [%s] reason: password or method changed' % (row[0]))
                    print('db stop server at port [%s] reason: password or method changed' % (row[0]))
                    DbTransfer.send_command('remove: {"server_port":%s}' % row[0])
                if config.PRO_NODE == 1 and row[7] != 'Z':
                	logging.info('db stop server at port [%s] reason: not Z plan' % (row[0]))
                	print('db stop server at port [%s] reason: not Z plan' % (row[0]))
                	DbTransfer.send_command('remove: {"server_port":%s}' % row[0])
            else:
                if config.PRO_NODE == 1 and row[7] != 'Z':
                    continue
                if row[5] == 1 and row[1] + row[2] < row[3]:
                    logging.info('db start server at port [%s] pass [%s]' % (row[0], row[4]))
                    if row[6] is None:
                    	row[6] = config.SS_METHOD
                    DbTransfer.send_command('add: {"server_port": %s, "password":"%s", "method":"%s"}'% (row[0], row[4], row[6]))
                    print('add: {"server_port": %s, "password":"%s", "method":"%s"}'% (row[0], row[4], row[6]))

    @staticmethod
    def thread_db():
        import socket
        import time
        timeout = 30
        socket.setdefaulttimeout(timeout)
        while True:
            logging.info('db loop')
            try:
                DbTransfer.get_instance().push_db_all_user()
                rows = DbTransfer.get_instance().pull_db_all_user()
                DbTransfer.del_server_out_of_bound_safe(rows)
            except Exception as e:
                import traceback
                traceback.print_exc()
                logging.warn('db thread except:%s' % e)
            finally:
                time.sleep(15)


#SQLData.pull_db_all_user()
#print DbTransfer.send_command("")
