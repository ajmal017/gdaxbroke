#!/usr/bin/env python
"""
Convenience wrapper for Interactive Brokers API.
"""
import random
import sys
import time
from collections import defaultdict
from datetime import datetime
import logging
from copy import copy

import math
from ib.opt import ibConnection, message
from ib.ext.Contract import Contract
from ib.ext.Order import Order as IBOrder
from ib.ext.TickType import TickType

#: API warning codes that are not actually problems and should not be logged
BENIGN_ERROR_CODES = (200, 2104, 2106)
#: API error codes indicating IB/TWS disconnection
DISCONNECT_ERROR_CODES = (504, 502, 1100, 1300, 2110)
#: When an order fails, the orderStatus message doesn't tell you why.  The description comes in a separate error message, so you gotta be able to tell if the "id" in an error message is an order id or a ticker id.
ORDER_RELATED_ERRORS = (103, 104, 105, 106, 107, 109, 110, 111, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 129, 131, 132, 133, 134, 135, 136, 137, 140, 141, 144, 146, 147, 148, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 163, 164, 166, 167, 168, 200, 201, 202, 203, 303, 311, 312, 313, 314, 315, 325, 327, 328, 329, 335, 336, 337, 338, 339, 340, 341, 342, 343, 347, 348, 349, 350, 351, 352, 353, 355, 356, 358, 359, 360, 361, 362, 363, 364, 367, 368, 369, 370, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380, 382, 383, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 422, 423, 424, 425, 426, 427, 428, 429, 433, 434, 435, 436, 437, 512, 515, 516, 517, 10003, 10005, 10006, 10007, 10008, 10009, 10010, 10011, 10012, 10013, 10014, 10016, 10017, 10018, 10019, 10020, 10021, 10022, 10023, 10024, 10025, 10026, 10027,)
#: Error codes related to data requests, i.e., the error id is a ticker id.
TICKER_RELATED_ERRORS = (101, 102, 138, 301, 300, 309, 310, 316, 302, 317, 354, 365, 366, 385, 386, 510, 511, 519, 520, 524, 525, 529, 530,)
#: A commission value you'd never expect to see.  Sometimes we get bogus commission values.
CRAZY_HIGH_COMMISSION = 1000000


class Instrument:
    """Represents a stock, bond, future, forex currency pair, or option."""
    def __init__(self, broker, symbol, sec_type='STK', exchange='SMART', currency='USD', expiry=None, strike=None, opt_type=None):
        """Create a Contract object defining what will
        be purchased, at which exchange and in which currency.

        :param broker IBroker: IBroker instance
        :param str symbol: The ticker symbol for the contract
        :param str sec_type: The security type for the contract ('STK', 'FUT', 'CASH' (forex))
        :param str currency: - The currency in which to purchase the contract
        :param str exchange: - The exchange to carry out the contract on.
          Usually: stock: SMART, futures: GLOBEX, forex: IDEALPRO
        :param float strike: The strike price for options
        :param str opt_type: 'PUT' or 'GET' for options
        """
        if strike or opt_type:      # TODO: IB requres PUT or CALL (not GET)
            raise NotImplementedError('Options not implemented yet.')
        contract = Contract()
        contract.m_symbol = symbol
        contract.m_secType = sec_type
        contract.m_exchange = exchange
        contract.m_currency = currency
        contract.m_expiry = expiry
        contract.m_strike = strike
        contract.m_right = opt_type
        contract.m_primaryExch = exchange
        self._broker = broker
        self._contract = contract

    @property
    def symbol(self):
        return self._contract.m_symbol

    @property
    def sec_type(self):
        return self._contract.m_secType

    @property
    def exchange(self):
        return self._contract.m_exchange

    @property
    def currency(self):
        return self._contract.m_currency

    @property
    def expiry(self):
        return self._contract.m_expiry

    @property
    def strike(self):
        return self._contract.m_strike

    @property
    def opt_type(self):
        return self._contract.m_right

    def details(self):
        """:Return: contract details."""
        raise NotImplementedError

    @property
    def id(self):
        """:Return: a unique ID for this instrument."""
        return self.symbol, self.sec_type, self.exchange, self.currency, self.expiry, self.strike, self.opt_type

    def __str__(self):
        return "Instrument<{}>".format(', '.join('{}={}'.format(prop, getattr(self, prop)) for prop in ('id', 'symbol', 'sec_type', 'exchange', 'currency', 'expiry', 'strike', 'opt_type',)))

    def __repr__(self):
        return str(self)


class Order:
    """An order for an Instrument"""
    def __init__(self, id_, instrument, price, quantity, filled, open, cancelled):
        """
        :param int quantity: Positive for buy, negative for sell
        :param int filled: Number of shares filled.  NEGATIVE FOR SELL ORDERS (when `quantity` is negative).
          If `quantity` is -5 (sell short 5), then `filled` == -3 means 3 out of 5 shares have been sold.
        """
        self.id = id_
        self.instrument = instrument
        self.price = price
        self.quantity = quantity
        self.filled = filled
        self.avg_price = None
        self.open = open
        self.cancelled = cancelled
        self.commission = 0
        self.open_time = None           # openOrder server time (epoch sec)
        self.fill_time = None           # Most recent fill (epoch sec)

    @property
    def complete(self):
        """:Return: True iff ``filled == quantity``."""
        return self.filled == self.quantity

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "Order<{}>".format(', '.join('{}={}'.format(prop, getattr(self, prop)) for prop in ('id', 'instrument', 'quantity', 'price', 'filled', 'avg_price', 'open', 'cancelled', 'commission', 'open_time', 'fill_time')))


class IBroke:
    """Interactive Brokers connection."""
    RTVOLUME = "233,mdoff"

    def __init__(self, host='localhost', port=7497, client_id=None, timeout_sec=5, verbose=0):
        """Connect to Interactive Brokers.

        :param float timeout_sec: If a connection cannot be established within this time,
          an exception is raised.
        """
        client_id = client_id if client_id is not None else random.randint(1, 2**31 - 1)       # TODO: It might be nice if this was a consistent hash of the caller's __file__ or __module__ or something.
        self._conn = ibConnection(host, port, client_id)
        self.log = logging.getLogger(__name__)
        self.log.setLevel(logging.DEBUG)
        self.verbose = verbose
        self.account = None
        self.__next_ticker_id = 0
        self.__next_order_id = 0
        self._tick_handlers = defaultdict(list)     # Maps ticker_id to list of functions to be called with those ticks
        self._order_handlers = defaultdict(list)    # Maps instrument id to list of functions to be called with order updates for that instrument
        self._alert_hanlders = defaultdict(list)    # Maps ticker_id to list of functions to be called with alerts for those tickers
        self._orders = dict()                       # Maps order_id to Order object
        self._executions = dict()                   # Maps execution IDs to order IDs.  Tracked because commissions are per-execution with no order ref.
        self._positions = dict()                    # Maps instrumetnt ID to number of shares held
        self.timeout_sec = timeout_sec
        self.connected = None                       # Tri-state: None -> never been connected, False: initially was connected but not now, True: connected
        self._conn.registerAll(self._handle_message)
        self._conn.connect()
        # The idea here is to catch errors synchronously, so if you can't connect, you know it at IBroke()
        start = time.time()
        while not self.connected:           # Set by _handle_message()
            if time.time() - start > timeout_sec:
                raise RuntimeError('Error connecting to IB')
            else:
                time.sleep(0.1)
        self._conn.reqPositions()

    def _next_ticker_id(self):
        """Increment the internal ticker id counter and return it."""
        self.__next_ticker_id += 1
        return self.__next_ticker_id

    def _next_order_id(self):
        """Increment the internal order id counter and return it."""
        self.__next_order_id += 1
        return self.__next_order_id

    def _to_instrument(self, inst):
        """:Return: an Instrument created from a string, tuple, or Instrument."""
        if isinstance(inst, str):
            return Instrument(self, inst)
        elif isinstance(inst, tuple):
            return Instrument(self, *inst)
        elif isinstance(inst, Instrument):
            return inst
        else:
            raise ValueError('Need string, tuple, or Instrument, got {}'.format(type(inst).__name__))

    def get_instrument(self, symbol, sec_type='STK', exchange='SMART', currency='USD', expiry=None, strike=None, opt_type=None):
        """Return an Instrument object defining what will be purchased, at which exchange and in which currency.

        symbol - The ticker symbol for the contract
        sec_type - The security type for the contract ('STK', 'FUT', 'CASH' (forex))
        exchange - The exchange to carry out the contract on
        currency - The currency in which to purchase the contract"""
        return Instrument(self, symbol, sec_type, exchange, currency, expiry, strike, opt_type)

    def register(self, instrument, on_tick=None, on_order=None, on_alert=None, aftermarket=False):
        """Register tick, order, and alert handlers for an `instrument`.

        :param str,tuple,Instrument instrument: The instrument to register callbacks for.
        :param func on_tick: Call ``func(timestamp, price, size, volume, vwap)`` for each tick of `contract`.
        :param func on_order: Call ``func(order)`` on order status changes for `contract`.
        :param func on_alert: Call ``func(alert_type)`` for notification of session start/end, trading halts, corporate actions, etc related to `contract`.
        :param bool aftermarket: If true, call `on_tick` with ticks outside regular market hours.
        """
        instrument = self._to_instrument(instrument)
        ticker_id = self._next_ticker_id()
        if on_tick:
            # TODO: Use contract IDs as ticker IDs
            self._tick_handlers[ticker_id].append(on_tick)
            self._conn.reqRealTimeBars(ticker_id, instrument._contract, 5, "TRADES", not aftermarket)
            self._conn.reqMktData(ticker_id, instrument._contract, self.RTVOLUME, False)
        if on_order:
            self._order_handlers[instrument.id].append(on_order)
        if on_alert:
            raise NotImplementedError

    def order(self, instrument, quantity, limit=0, target=0, stop=0):
        """Place and order and return an Order object."""
        if target:
            raise NotImplementedError

        typemap = {
            (False, False): 'MKT',
            (False, True):  'LMT',
            (True, False):  'STP',
            (True, True):   'STP LMT',
        }

        # TODO: Check stop limit values are consistent
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
        order.m_clientId = self._conn.clientId

        order_id = self._next_order_id()
        self.log.debug('Place order %d: %s %s', order_id, ib2dict(instrument._contract), ib2dict(order))
        self._orders[order_id] = Order(order_id, instrument, price=limit or None, quantity=quantity, filled=0, open=True, cancelled=False)
        self._conn.placeOrder(order_id, instrument._contract, order)        # This needs come after updating self._orders
        return self._orders[order_id]

    def cancel(self, order):
        """Cancel an order."""
        raise NotImplementedError

    def exit(self, instrument):
        """Set position to 0 for (aka flatten) `instrument` and cancel any outstanding orders."""
        raise NotImplementedError

    def get_position(self, instrument):
        """:Return: the number of shares of `instrument` held (negative for short)."""
        return self._positions.get(instrument.id, 0)

    def disconnect(self):
        """Disconnect from IB, rendering this object mostly useless."""
        self.connected = False
        self._conn.disconnect()

    def _call_order_handlers(self, order):
        """Call any order handlers registered for ``order.instrument``."""
        for handler in self._order_handlers.get(order.instrument.id, ()):
            handler(copy(order))

    @staticmethod
    def _instrument_id_from_contract(contract):
        # TODO: Just use the contract id
        return contract.m_symbol, contract.m_secType, contract.m_exchange, contract.m_currency, contract.m_expiry, contract.m_strike, contract.m_right


    #########################################
    # Message Handlers
    def _handle_message(self, msg):
        """Root message handler, dispatches to methods named `_typeName`.

        E.g., `tickString` messages are dispatched to `self._tickString()`.
        """
        if self.verbose >= 2:
            self.log.debug('MSG %s', str(msg))

        name = getattr(msg, 'typeName', None)
        if not name or not name.isidentifier():
            self.log.error('Invalid message name %s', name)
            return
        handler = getattr(self, '_' + name, self._defaultHandler)
        if not callable(handler):
            self.log.error("Message handler '%s' (type %s) is not callable", str(handler), type(handler))
            return
        if handler != self._error:      # I suppose there are a few errors that indicate you're connected, but...
            self.connected = True
        handler(msg)

    def _error(self, msg):
        code = getattr(msg, 'errorCode', None)
        if code in BENIGN_ERROR_CODES:
            return
        if code in DISCONNECT_ERROR_CODES:
            self.connected = False
        if not isinstance(code, int):
            self.log.error(str(msg))
        elif 2100 <= code < 2200:
            self.log.warn(str(msg))
        else:
            self.log.error(str(msg))
            if code in ORDER_RELATED_ERRORS:
                order = self._orders.get(msg.id)
                if order:
                    order.cancelled = True
                    order.open = False
                    order.message = msg.errorMsg
                    self.log.debug('ORDER ERR %s', vars(order))
                    self._call_order_handlers(order)

            if code in TICKER_RELATED_ERRORS:
                pass  # TODO: Connect error with ticker request

    def _managedAccounts(self, msg):
        accts = msg.accountsList.split(',')
        if len(accts) != 1:
            raise ValueError('Multiple accounts not supported.  Accounts: {}'.format(accts))
        self.account = accts[0]

    def _tickString(self, msg):
        if msg.tickType != TickType.RT_VOLUME:
            print('Weird tickstring ', msg.value)
            return
        #Last trade price
        #Last trade size
        #Last trade time
        #Total volume - Total for day since market open (in lots (of 100 for stocks?))
        #VWAP - Avg for day since market open
        #Single trade flag - True indicates the trade was filled by a single market maker; False indicates multiple market-makers helped fill the trade
        vals = msg.value.split(';')
        for i in range(5):
            try:
                vals[i] = float(vals[i])
            except ValueError:      # Sometimes prices are missing (empty string)
                vals[i] = float('NaN')
        price, size, timestamp, volume, vwap = vals[:5]       # Volume is total cumulative volume for the day (or something like that)
        handlers = self._tick_handlers.get(msg.tickerId)        # get() does not insert into the defaultdict
        if handlers is None:
            self.log.warning('No handler for ticker id {}'.format(msg.tickerId))
        else:
            for handler in handlers:
                handler(timestamp / 1000.0, price, size, volume, vwap)

    def _nextValidId(self, msg):
        if msg.orderId >= self.__next_order_id:
            self.__next_order_id = msg.orderId
        else:
            self.log.warn('nextValidId {} less than current id {}'.format(msg.orderId, self.__next_order_id))

    def _orderStatus(self, msg):
        """Called with changes in order status.

        Except:
        "Typically there are duplicate orderStatus messages with the same information..."
        "There are not guaranteed to be orderStatus callbacks for every change in order status."
        """
        order = self._orders.get(msg.orderId)
        if not order:
            self.log.error('Got orderStatus for unknown orderId {}'.format(msg.orderId))
            return

        # TODO: Worth making these immutable and replacing them?  Or *really* immutable and appending to a list of them?
        if order.open_time is None:
            order.open_time = time.time()
        if msg.status in ('ApiCanceled', 'Canceled'):       # Inactive can mean error or not
            order.cancelled = True
            order.open = False
        elif msg.filled > abs(order.filled):      # Suppress duplicate / out-of-order fills  (order.filled is negative for sells)
            order.filled = int(math.copysign(msg.filled, order.quantity))
            order.avg_price = msg.avgFillPrice
            if order.filled == order.quantity:
                order.open = False
            self.log.info('Order %d (%d @ %s) filled %d @ %.2f', msg.orderId, order.quantity, str(order.price or 'MKT'), order.filled, order.avg_price)
            self._call_order_handlers(order)

    def _openOrder(self, msg):
        """Called when orders are submitted and completed."""
        order = self._orders.get(msg.orderId)
        if not order:
            self.log.error('Got openOrder for unknown orderId {}'.format(msg.orderId))
            return
        assert order.id == msg.orderId
        assert order.instrument._contract.m_symbol == msg.contract.m_symbol     # TODO: More thorough equality
        if order.open_time is None:
            order.open_time = time.time()
        # possible status: Submitted Cancelled Filled Inactive
        if msg.orderState.m_status == 'Cancelled':
            order.cancelled = True
            order.open = False
        elif msg.orderState.m_status == 'Filled':
            order.open = False
        # In theory we might be able to use orderState instead of commissionReport, but...
        # It's kinda whack.  Sometime's it's giant numbers, and there are dupes so it's hard to use.
        if msg.orderState.m_warningText:
            self.log.warn('Order %d: %s', msg.orderId, msg.orderState.m_warningText)
            order.message = msg.orderState.m_warningText

        self.log.debug('STATE %d %s', msg.orderId, ib2dict(msg.orderState))

    def _execDetails(self, msg):
        """Called on order executions."""
        order = self._orders.get(msg.execution.m_orderId)
        if not order:
            self.log.error('Got execDetails for unknown orderId {}'.format(msg.execution.m_orderId))
            return
        exec = msg.execution
        self.log.info('EXEC %s order %d %s %d @ %.2f (cumulative qty %d)', exec.m_time, order.id, order.instrument.symbol, int(math.copysign(exec.m_shares, order.quantity)), exec.m_price, int(math.copysign(exec.m_cumQty, order.quantity)))
        assert order.id == exec.m_orderId
        if order.open_time is None:
            order.open_time = time.time()
        self._executions[exec.m_execId] = order.id      # Track which order executions belong to, since commissions are per-exec
        if exec.m_cumQty > abs(order.filled):           # Suppress duplicate / late fills.  Remember, kids: sells are negative!
            # TODO: Save server time delta
            order.fill_time = time.time()
            order.filled = int(math.copysign(exec.m_cumQty, order.quantity))
            order.avg_price = exec.m_avgPrice
            if order.filled == order.quantity:
                order.open = False
            # We call order handlers in commissionReport() instead of here so we can include commission info.

    def _position(self, msg):
        """Called when positions change; gives new position."""
        self.log.debug('POS %d %s', msg.pos, self._instrument_id_from_contract(msg.contract))
        self._positions[self._instrument_id_from_contract(msg.contract)] = msg.pos

    def _commissionReport(self, msg):
        """Called after executions; gives commission charge and PNL.  Calls order handlers."""
        # In theory we might be able to use orderState instead of commissionReport, but...
        # It's kinda whack.  Sometime's it's giant numbers, and there are dupes so it's hard to use.
        report = msg.commissionReport
        self.log.debug('COMM %s', vars(report))
        order = self._orders.get(self._executions.get(report.m_execId))
        if order:
            if 0 <= report.m_commission < CRAZY_HIGH_COMMISSION:        # We sometimes get bogus placeholder values
                order.commission += report.m_commission
            # TODO: We're potentially calling handlers more than once, here and in orderStatus
            # TODO: register() flag to say only fire on_order() events on totally filled, or cancel/error.
            self._call_order_handlers(order)
        else:
            self.log.error('No order found for execution {}'.format(report.m_execId))

    def _defaultHandler(self, msg):
        """Called when there is no other message handler for `msg`."""
        if self.verbose < 2:        # Don't log again if already logged in main handler
            self.log.debug('MSG %s', msg)


def ib2dict(obj):
    """Convert an (IBPy) object to a dict containing any non-default values."""
    default = obj.__class__()
    return {field: val for field, val in vars(obj).items() if val != getattr(default, field, None)}


#############################################################


def on_tick(timestamp, price, size, volume, vwap):
    timestamp = datetime.utcfromtimestamp(timestamp)
    print('{} price {:.2f} size {:.0f} vol {:.0f} vwap {:.2f}'.format(timestamp, price, size, volume, vwap))


def on_order(order):
    print('order', order)


def main():
    """Do it."""
    ib = IBroke(verbose=0)
    #inst = ib.get_instrument("AAPL")
    inst = ib.get_instrument("ES", "FUT", "GLOBEX", expiry="20161216")
    ib.register(inst, on_tick, on_order)
    time.sleep(3)
    ib.order(inst, 50)
    time.sleep(10)
    ib.order(inst, -50)
    time.sleep(10)
    ib.disconnect()
    time.sleep(0.5)


if __name__ == '__main__':
    main()



