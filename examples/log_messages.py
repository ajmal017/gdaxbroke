#!/usr/bin/env python3
"""
Log raw messages from IBPy.  This is for debugging and does not use IBroke.

Use with demo account or set IB_PAPER_ACCOUNT env var to paper account number.
"""
import sys
import random
import logging
from itertools import count
from time import sleep, time
import os

from ib.opt import ibConnection, message
from ib.ext.Contract import Contract
from ib.ext.Order import Order as IBOrder

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


def make_order(quantity, limit=0.0, stop=0.0):
    """Return: an IB Order object."""
    typemap = {
        (False, False): 'MKT',
        (False, True):  'LMT',
        (True, False):  'STP',
        (True, True):   'STP LMT',
    }

    order = IBOrder()
    order.m_action = 'BUY' if quantity >= 0 else 'SELL'
    order.m_minQty = abs(quantity)
    order.m_totalQuantity = abs(quantity)
    order.m_orderType = typemap[(bool(stop), bool(limit))]
    order.m_lmtPrice = limit
    order.m_auxPrice = stop
    order.m_tif = 'DAY'     # Time in force: DAY, GTC, IOC, GTD
    order.m_allOrNone = False   # Fill or Kill
    order.m_goodTillDate = "" #  FORMAT: 20060505 08:00:00 {time zone}
    return order


def main():
    """Connect, request, display."""
    paper_account = False        # Ensure we're not using a real-money account
    account = None

    def handle(msg):
        nonlocal paper_account, account
        log.debug(msg)
        if getattr(msg, 'typeName', None) == 'accountSummary' and msg.tag == 'AccountType' and msg.value == 'UNIVERSAL':
            paper_account = True
        if getattr(msg, 'typeName', None) == 'managedAccounts':
            account = msg.accountsList
            if account and account == os.environ.get('IB_PAPER_ACCOUNT'):
                paper_account = True

    host, port, client_id = 'localhost', 7497, random.randint(1, 2 ** 31 - 1)

    conn = ibConnection(host, port, client_id)
    conn.registerAll(handle)
    conn.connect()
    log.info('Connected')

    # Make sure it's a paper account
    conn.reqAccountSummary(0, 'All', 'AccountType')
    sleep(1)
    print('Account {}, Paper Trading = {}'.format(account, paper_account))
    if not paper_account:
        log.error('Refusing to run with non-demo account')
        sys.exit(1)

    #contract = make_contract('es', 'fut', 'globex', 'usd', '20161216')
    #contract = make_contract('AAPL')
    contract = make_contract('EUR', 'CASH', 'IDEALPRO')
    conn.reqMktData(0, contract, RTVOLUME, False)
    #conn.reqRealTimeBars(1, contract, 5, "BID", False)

    #conn.reqGlobalCancel()
    sleep(30)


if __name__ == '__main__':
    main()
