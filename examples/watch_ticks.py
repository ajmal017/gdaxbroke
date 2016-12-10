#!/usr/bin/env python3
"""
Watch raw ticks from IBPy.  This is for debugging and does not use IBroke.
"""
import random
import logging
from time import sleep

from ib.ext.TickType import TickType
from ib.opt import ibConnection
from ib.ext.Contract import Contract

log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)


RTVOLUME = "233"


def make_contract(symbol, sec_type='STK', exchange='SMART', currency='USD', expiry=None, strike=0.0, opt_type=None):
    """:Return: an (unvalidated, no conID) IB Contract object with the given parameters."""
    contract = Contract()
    contract.m_symbol = symbol
    contract.m_secType = sec_type
    contract.m_exchange = exchange
    contract.m_currency = currency
    contract.m_expiry = expiry
    contract.m_strike = strike
    contract.m_right = opt_type
    return contract

FIELDS = ('time', 'bid', 'bidsize', 'ask', 'asksize', 'last', 'lastsize', 'volume')


def show(name, line_count=[0], **kwargs):
    """Print any given values in consistently ordered tab-separated format to stdout."""
    if line_count[0] % 25 == 0:
        line_count[0] += 1
        print()
        show('name', **dict(zip(FIELDS, FIELDS)))
    line_count[0] += 1

    width = 12
    print('{:<{}}'.format(name, width), end='')
    for field in FIELDS:
        val = kwargs.get(field)
        print('{:>{}}'.format('' if val is None else val, 15 if field == 'time' else width), end='')
    print()


def handle(msg):
    #print(msg)
    name = getattr(msg, 'typeName', None)

    if name == 'tickSize':
        if msg.field == TickType.BID_SIZE:
            show('bidsize', bidsize=msg.size)
        elif msg.field == TickType.ASK_SIZE:
            show('asksize', asksize=msg.size)
        elif msg.field == TickType.LAST_SIZE:
            show('lastsize', lastsize=msg.size)
        elif msg.field == TickType.VOLUME:
            show('volume', volume=msg.size)

    elif name == 'tickPrice':
        if msg.field == TickType.BID:
            show('bid', bid=msg.price)
        elif msg.field == TickType.ASK:
            show('ask', ask=msg.price)
        elif msg.field == TickType.LAST:
            show('last', last=msg.price)

    elif name == 'tickString':
        if msg.tickType == TickType.LAST_TIMESTAMP:
            show('lasttime', time=msg.value)
        elif msg.tickType == TickType.RT_VOLUME:
            vals = msg.value.split(';')
            for i in range(5):
                try:
                    vals[i] = float(vals[i])
                except ValueError:      # Sometimes prices are missing (empty string);
                    return      # Don't show missing prices
                    # vals[i] = float('NaN')
            price, size, timestamp, volume, vwap = vals[:5]
            show('rtvolume', time=round(timestamp / 1000, 3), last=price, lastsize=size, volume=volume)


def main():
    """Connect, request, display."""
    host, port, client_id = 'localhost', 7497, random.randint(1, 2 ** 31 - 1)

    conn = ibConnection(host, port, client_id)
    conn.registerAll(handle)
    conn.connect()
    log.info('Connected')

    contract = make_contract('es', 'fut', 'globex', 'usd', '20161216')
    #contract = make_contract('AAPL')
    #contract = make_contract('EUR', 'CASH', 'IDEALPRO')
    conn.reqMktData(0, contract, RTVOLUME, False)
    #conn.reqRealTimeBars(1, contract, 5, "BID", False)

    while conn.isConnected():
        sleep(1)
    conn.disconnect()


if __name__ == '__main__':
    main()
