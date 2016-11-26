#!/usr/bin/env python3
"""
Log raw messages from IBPy.  This is for debugging and does not use IBroke.
"""
import sys
import random
import logging
from time import sleep, time

from ib.opt import ibConnection, message
from ib.ext.Contract import Contract
from ib.ext.Order import Order as IBOrder
from ib.ext.TickType import TickType

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


def main():
    """Connect, request, display."""
    safe_account = False        # Ensure we're not using a real-money account

    def handle(msg):
        nonlocal safe_account
        log.debug(msg)
        if getattr(msg, 'typeName', None) == 'accountSummary' and msg.tag == 'AccountType' and msg.value == 'UNIVERSAL':
            safe_account = True


    host, port, client_id = 'localhost', 7497, random.randint(1, 2 ** 31 - 1)
    timeout_sec = 5.0

    conn = ibConnection(host, port, client_id)
    conn.registerAll(handle)
    conn.connect()
    log.info('Connected')

    # Make sure it's a demo account
    conn.reqAccountSummary(0, 'All', 'AccountType')
    sleep(1)
    if not safe_account:
        log.error('Refusing to run with non-demo account')
        sys.exit(1)

    #contract = make_contract('es', 'fut', 'globex', 'usd', '20161216')
    #contract = make_contract('AAPL')
    contract = make_contract('EUR', 'CASH', 'IDEALPRO')
    conn.reqMktData(0, contract, RTVOLUME, False)
    #conn.reqRealTimeBars(1, contract, 5, "TRADES", False)

    while True:
        sleep(1)


if __name__ == '__main__':
    main()
