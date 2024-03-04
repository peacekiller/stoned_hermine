#!/usr/bin/python3

import configparser
import logging
import sched
import sqlite3
import time
from pyliquibase import Pyliquibase
from Diff import Diff
from Stashcat import StashCatClient
from steinapi import SteinAPI


def update_and_notify(s: sched):
    logging.debug("looking for updates")
    for incoming_asset in steinapp.getAssets():
        cursor = con.cursor()
        cursor.execute('select * from assets where id = ?', (incoming_asset["id"],))
        existing_asset = cursor.fetchone()
        cursor.close()

        if existing_asset is None:
            create(incoming_asset)
            logging.info("create %s(%s)", incoming_asset["label"], incoming_asset["name"])
            continue

        else:
            diff = determine_difference(existing_asset, incoming_asset)
            if len(diff) > 0:
                logging.info("there are changes for %s(%s)", incoming_asset["label"], incoming_asset["name"])
                update(incoming_asset)
                logging.info("updated %s(%s)", incoming_asset["label"], incoming_asset["name"])
                notify(incoming_asset, diff)
                continue

        logging.debug("no changes in asset %s (%s): skipped update", existing_asset['label'], existing_asset['name'])

    s.enter(delay, 1, update_and_notify, (s,))


def update(incoming_asset: dict):
    data = (incoming_asset["buId"], incoming_asset["groupId"], incoming_asset["label"], incoming_asset["name"],
            incoming_asset["status"], incoming_asset["comment"], incoming_asset["category"], incoming_asset["deleted"],
            incoming_asset["lastModified"], incoming_asset["lastModifiedBy"],
            incoming_asset["radioName"], incoming_asset["issi"], incoming_asset["sortOrder"],
            incoming_asset["operationReservation"], incoming_asset["id"])
    cursor = con.cursor()
    cursor.execute(
        'update assets set buId=?,groupId=?,label=?,name=?,status=?,comment=?,category=?,deleted=?,lastModified=?,'
        'lastModifiedBy=?,radioName=?,issi=?,sortOrder=?,operationReservation=? where id=?', data)
    con.commit()


def create(asset: dict):
    data = [asset["buId"], asset["groupId"], asset["id"], asset["label"], asset["name"], asset["status"],
            asset["comment"], asset["category"], asset["deleted"], asset["lastModified"], asset["lastModifiedBy"],
            asset["created"], asset["radioName"], asset["issi"], asset["sortOrder"], asset["operationReservation"]]
    cursor = con.cursor()
    cursor.execute(
        'insert into assets (buId,groupId,id,label,name,status,comment,category,deleted,lastModified,'
        'lastModifiedBy,created,radioName,issi,sortOrder,operationReservation) values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
        data)
    con.commit()


def create_message(asset, diffs: [Diff]) -> str:
    changes = ""
    for diff in diffs:
        if diff.field == 'status':
            changes += 'Status: {} (war: {})'.format(map_status(diff.new_val), map_status(diff.old_val))
        elif diff.new_val == 'comment':
            changes += diff.new_val
        elif diff.new_val == 'operationReservation':
            changes += 'Steht {}unter Einsatzvorbehalt'.format(('' if diff.new_val else "nicht mehr "))
        changes += '\n'
    return '{} ({}):\n------------------\n{}'.format(asset['label'], asset['name'], changes)


def map_status(status: str) -> str:
    if status == 'ready':
        return 'einsatzbereit'
    if status == 'notready':
        return 'nicht einsatzbereit'
    if status == 'semiready':
        return 'bedingt einsatzbereit'
    if status == 'maint':
        return 'In der Werkstatt'
    if status == 'inuse':
        return 'im Einsatz'
    return 'unbekannt'


def notify(asset: dict, diff: dict):
    logging.info("notify about changes on %s(%s): %s", asset["label"], asset["name"], str(diff))
    message = create_message(asset, diff)
    logging.debug('message to hermine: "{}"', message)
    hermine.send_msg_to_channel(hermine_channel, message)


def determine_difference(old: dict, new: dict) -> [Diff]:
    diff = []
    for key in new:
        if new[key] != old[key]:
            diff.append(Diff(field=key, old_val=old[key], new_val=new[key]))
    return diff


def dict_factory(cursor, row):
    res = {}
    for idx, col in enumerate(cursor.description):
        res[col[0]] = row[idx]
    return res


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('config.ini')

    loglevel = config['default']['log_level']
    logfile = config['default']['log_file']
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=loglevel, datefmt='%Y-%m-%d %H:%M:%S', filename=logfile)
    logging.info("log level is set to %s", loglevel)

    liquibase = Pyliquibase(defaultsFile="./changelogs/liquibase.properties")
    liquibase.update()

    con = sqlite3.connect(config['database']['filename'])
    con.row_factory = dict_factory

    uebung = config['stein.app']['uebung'] != 'false'
    if uebung:
        logging.warning("ÜBUNGSMODUS AKTIV!")
    steinapp = SteinAPI(config['stein.app']['organisation'], uebung)
    steinapp.connect(config['stein.app']['username'], config['stein.app']['password'])

    hermine = StashCatClient()
    logging.info("login into hermine")
    payload = hermine.login(config['hermine']['username'], config['hermine']['password'])
    if not payload:
        raise Exception("login into hermine failed")

    hermine_channel = config['hermine']['channel_id']
    hermine.open_private_key(config['hermine']['encryption_key'])

    s = sched.scheduler(time.time, time.sleep)
    delay = int(config["default"]["update_interval_in_seconds"])
    logging.info("updates are requested every %s seconds", delay)
    s.enter(delay, 1, update_and_notify, (s,))
    s.run()
