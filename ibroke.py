#!/usr/bin/env python3
"""
Convenience wrapper for Interactive Brokers API.

    Copyright (C) 2016  Doctor J

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Lesser General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Lesser General Public License for more details.

    You should have received a copy of the GNU Lesser General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import random
import sys
import time
from collections import defaultdict, namedtuple
from datetime import datetime
import logging
from copy import copy

import math
from itertools import takewhile
from queue import Queue, Empty

from ib.opt import ibConnection
from ib.ext.Contract import Contract
from ib.ext.Order import Order as IBOrder
from ib.ext.TickType import TickType

__version__ = "0.0.3"


#: API warning codes that are not actually problems and should not be logged
BENIGN_ERRORS = (2104, 2106, 2137)
#: API error codes indicating IB/TWS disconnection
DISCONNECT_ERRORS = (504, 502, 1100, 1300, 2110)
#: When an order fails, the orderStatus message doesn't tell you why.  The description comes in a separate error message, so you gotta be able to tell if the "id" in an error message is an order id or a ticker id.
ORDER_RELATED_ERRORS = (103, 104, 105, 106, 107, 109, 110, 111, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 124, 125, 126, 129, 131, 132, 133, 134, 135, 136, 137, 140, 141, 144, 146, 147, 148, 151, 152, 153, 154, 155, 156, 157, 158, 159, 160, 161, 163, 164, 166, 167, 168, 201, 202, 203, 303, 311, 312, 313, 314, 315, 325, 327, 328, 329, 335, 336, 337, 338, 339, 340, 341, 342, 343, 347, 348, 349, 350, 351, 352, 353, 355, 356, 358, 359, 360, 361, 362, 363, 364, 367, 368, 369, 370, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380, 382, 383, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414, 415, 416, 417, 418, 419, 422, 423, 424, 425, 426, 427, 428, 429, 433, 434, 435, 436, 437, 512, 515, 516, 517, 10003, 10005, 10006, 10007, 10008, 10009, 10010, 10011, 10012, 10013, 10014, 10016, 10017, 10018, 10019, 10020, 10021, 10022, 10023, 10024, 10025, 10026, 10027,)
#: Error codes related to data requests, i.e., the error id is a ticker id.
TICKER_RELATED_ERRORS = (101, 102, 138, 301, 300, 309, 310, 316, 302, 317, 354, 365, 366, 385, 386, 420, 510, 511, 519, 520, 524, 525, 529, 530,)
#: Errors requesting contract details
CONTRACT_REQUEST_ERRORS = (200,)
#: A commission value you'd never expect to see.  Sometimes we get bogus commission values.
CRAZY_HIGH_COMMISSION = 1000000
#: A fill profit you'd never expect to see.
CRAZY_HIGH_PROFIT = 1000000
#: Map verbosity levels to logger levels
LOG_LEVELS = {
    0: logging.CRITICAL,
    1: logging.ERROR,
    2: logging.WARNING,
    3: logging.INFO,
    4: logging.DEBUG,
    5: logging.DEBUG,
}
InstrumentDefaults = namedtuple('InstrumentDefaults', 'symbol sec_type exchange currency expiry strike opt_type')
#: Default values for instrument fields
INSTRUMENT_DEFAULTS = InstrumentDefaults(None, 'STK', 'SMART', 'USD', None, 0.0, None)


class Instrument:
    """Represents a stock, bond, future, forex currency pair, or option."""
    def __init__(self, broker, contract):
        """Create a Contract object defining what will
        be purchased, at which exchange and in which currency.

        :param IBroker broker: IBroker instance
        :param Contract contract: IBPy Contract object (must have conID from contractDetails())
        """
        if not contract.m_conId:
            raise ValueError('Contract must have conId (obtained from contractDetails()).')
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
        return IBroke._instrument_id_from_contract(self._contract)

    def tuple(self):
        """:Return: The instrument as a 7-tuple."""
        return tuple(getattr(self, prop) for prop in InstrumentDefaults._fields)

    def __str__(self):
        return str(self.tuple())

    def __repr__(self):
        return str(self)

    def __eq__(self, other):
        """:Return: True iff `other` has the same IB Contract ID as this Instrument."""
        return self.id == other.id

    def __hash__(self):
        return self.id


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
        self.profit = 0                 # Realized profit so far for this order, net commisssions (negative for loss).  Reflects IB's (strange) accounting.
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
        inst = tuple(val for default, val in zip(INSTRUMENT_DEFAULTS, self.instrument.tuple()) if val != default)
        return "Order<{inst} {filled}/{quantity} @ {price} {open}{cancelled} #{id}>".format(
            id=self.id, inst=inst, filled=self.filled, quantity=self.quantity, price=self.price, open='open' if self.open else 'closed', cancelled=' cancelled' if self.cancelled else '')


class IBroke:
    """Interactive Brokers connection.

    It is not safe to call the methods of this object from multiple threads.
    """
    RTVOLUME = "233,mdoff"

    def __init__(self, host='localhost', port=7497, client_id=None, timeout_sec=5, verbose=3):
        """Connect to Interactive Brokers.

        :param float timeout_sec: If a connection cannot be established within this time,
          an exception is raised.
        """
        client_id = client_id if client_id is not None else random.randint(1, 2**31 - 1)       # TODO: It might be nice if this was a consistent hash of the caller's __file__ or __module__ or something.
        self.log = logging.getLogger(__name__)
        self.log.setLevel(LOG_LEVELS[verbose])
        self.verbose = verbose
        self.account = None
        self.__next_order_id = 0
        self._tick_handlers = defaultdict(list)     # Maps instrument ID (contract ID) to list of functions to be called with those ticks
        self._tick_errors = dict()                  # Maps instrument ID (contract ID) to queue of any exceptions (errors) generated by requesting that ticker
        self._order_handlers = defaultdict(list)    # Maps instrument ID (contract ID) to list of functions to be called with order updates for that instrument
        self._alert_hanlders = defaultdict(list)    # Maps instrument ID (contract ID) to list of functions to be called with alerts for those tickers
        self._orders = dict()                       # Maps order_id to Order object
        self._executions = dict()                   # Maps execution IDs to order IDs.  Tracked because commissions are per-execution with no order ref.
        self._positions = dict()                    # Maps instrument ID to number of shares held
        self._contract_details = []                 # Maps contractDetails() request id (int) to ContractDetails object.
        self.timeout_sec = timeout_sec
        self.connected = None                       # Tri-state: None -> never been connected, False: initially was connected but not now, True: connected
        self._conn = ibConnection(host, port, client_id)
        self._conn.registerAll(self._handle_message)
        self._conn.connect()
        # The idea here is to catch errors synchronously, so if you can't connect, you know it at IBroke()
        start = time.time()
        while not self.connected:           # Set by _handle_message()
            if time.time() - start > timeout_sec:
                raise RuntimeError('Error connecting to IB')
            else:
                time.sleep(0.1)
        self.log.info('IBroke %s connected to %s:%d, client ID %d', __version__, host, port, client_id)
        self._conn.reqPositions()

    def get_instrument(self, symbol, sec_type='STK', exchange='SMART', currency='USD', expiry=None, strike=0.0, opt_type=None):
        """Return an Instrument object defining what will be purchased, at which exchange and in which currency.

        :param str,tuple,Instrument symbol: The ticker symbol for the contract, or an Instrument object.
        :param str sec_type: The security type for the contract ('STK', 'FUT', 'CASH' (forex))
        :param str currency: - The currency in which to purchase the contract
        :param str exchange: - The exchange to carry out the contract on.
          Usually: stock: SMART, futures: GLOBEX, forex: IDEALPRO
        :param float strike: The strike price for options
        :param str opt_type: 'PUT' or 'CALL' for options
        """
        if isinstance(symbol, Instrument):
            return symbol
        elif isinstance(symbol, tuple):
            return self.get_instrument(*symbol)
        elif not isinstance(symbol, str):
            raise ValueError("symbol must be string, tuple, or Instrument")

        contract = make_contract(symbol, sec_type, exchange, currency, expiry, strike, opt_type)
        req_id = len(self._contract_details)        # TODO: race condition between getting length and extending
        self._contract_details.append(Queue())      # Filled by _contractDetails(), capped off with None by _contractDetailsEnd()
        self._conn.reqContractDetails(req_id, contract)
        # Wait on all ContractDetails objects to fill in the queue, toss the terminating None, put into a tuple.
        details = tuple(takewhile(lambda v: v is not None, iter_except(lambda: self._contract_details[req_id].get(timeout=self.timeout_sec), Empty)))
        if not details:
            raise ValueError("Timed out looking for matching contracts.")
        elif isinstance(details[0], Exception):       # Error
            raise details[0]

        best = choose_best_contract(details)
        self.log.debug('BEST %s', obj2dict(best.m_summary))
        return Instrument(self, best.m_summary)

    def register(self, instrument, on_tick=None, on_order=None, on_alert=None, aftermarket=False):
        """Register tick, order, and alert handlers for an `instrument`.

        :param str,tuple,Instrument instrument: The instrument to register callbacks for.
        :param func on_tick: Call ``func(timestamp, price, size, volume, vwap)`` for each tick of `instrument`.
        :param func on_order: Call ``func(order)`` on order status changes for `instrument`.
        :param func on_alert: Call ``func(alert_type)`` for notification of session start/end, trading halts, corporate actions, etc related to `instrument`.
        :param bool aftermarket: If true, call `on_tick` with ticks outside regular market hours.
        """
        # TODO: Maybe rename on_tick on_data, add param for type of data ('trade' (last trade price + vol), 'quote' (bid/ask), or float sec for bars)
        instrument = self.get_instrument(instrument)
        if on_tick:
            if not self._tick_handlers.get(instrument.id):      # New ticker (get() does not insert into defaultdict)
                def unblock_register(*args):
                    """Temporary initial on_tick handler to unblock register() if a tick arrives"""
                    self._tick_errors[instrument.id].put_nowait(None)

                self._tick_errors[instrument.id] = Queue()      # _error() stuffs an exception in if it gets an error message; unblock_register stuffs None if it gets a tick
                self._tick_handlers[instrument.id].append(unblock_register)
                self._conn.reqMktData(instrument.id, instrument._contract, self.RTVOLUME, snapshot=False)
                # Wait for errors
                # TODO: Something about waiting on errors.  There's no message on successful mkt data subscription,
                # so it's hard to know when it worked.  There won't always be a tick on success.
                # The delay compounds when subscribing to many tickers.  One shared
                # Queue to wait on?  Poll all queues (python doesn't have a wait-on-multiple-queues select() type thing)?
                try:
                    err = self._tick_errors[instrument.id].get(timeout=self.timeout_sec)
                    if err is not None:
                        raise err
                except Empty:       # No errors (or ticks) within timeout
                    pass
                assert len(self._tick_handlers[instrument.id]) == 1, 'Found more than initial tick handler on register {}: {}'.format(instrument.id, self._tick_handlers[instrument.id])
                self._tick_handlers[instrument.id].pop()        # Remove initial handler
            self._tick_handlers[instrument.id].append(on_tick)
            self.log.debug('REGISTER %d %s', instrument.id, instrument)
        if on_order:
            self._order_handlers[instrument.id].append(on_order)
        if on_alert:
            raise NotImplementedError

    def order(self, instrument, quantity, limit=0.0, stop=0.0, target=0.0):
        """Place an order and return an Order object, or None if no order was made.

        The returned object does not change (will not update).
        """
        if target:
            raise NotImplementedError
        if quantity == 0:
            return None

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
        self.log.debug('ORDER %d: %s %s', order_id, obj2dict(instrument._contract), obj2dict(order))
        self._orders[order_id] = Order(order_id, instrument, price=limit or None, quantity=quantity, filled=0, open=True, cancelled=False)
        self.log.info('ORDER %s', self._orders[order_id])
        self._conn.placeOrder(order_id, instrument._contract, order)        # This needs come after updating self._orders
        return copy(self._orders[order_id])

    def order_target(self, instrument, quantity, limit=0.0, stop=0.0):
        """Place orders as necessary to bring position in `instrument` to `quantity`.

        Bracket orders (with `target`) don't really make sense here.
        """
        return self.order(instrument, quantity - self.get_position(instrument), limit=limit, stop=stop)

    def cancel(self, order):
        """Cancel an `order`."""
        self.log.info('CANCEL %s', order)
        self._conn.cancelOrder(order.id)

    def cancel_all(self, instrument=None):
        """Cancel all open orders.  If given, only cancel orders for `instrument`."""
        # TODO: We might want to request all open orders, since our order status tracking might not be perfect.
        for order in self._orders.values():
            if order.open and (instrument is None or order.instrument == instrument):
                self.cancel(order)

    def exit(self, instrument):
        """Set position to 0 for (aka flatten) `instrument` and cancel any outstanding orders."""
        self.order_target(instrument, 0)        # TODO: Do we really need this method?

    def get_position(self, instrument):
        """:Return: the number of shares of `instrument` held (negative for short)."""
        pos = self._positions.get(instrument.id)
        if pos is None:
            self.log.warn('get_position() for unknown instrument {}'.format(instrument))
            return 0
        return pos

    def disconnect(self):
        """Disconnect from IB, rendering this object mostly useless."""
        self.connected = False
        self._conn.disconnect()

    def _next_order_id(self):
        """Increment the internal order id counter and return it."""
        self.__next_order_id += 1
        return self.__next_order_id

    def _call_order_handlers(self, order):
        """Call any order handlers registered for ``order.instrument``."""
        for handler in self._order_handlers.get(order.instrument.id, ()):
            handler(copy(order))

    @staticmethod
    def _instrument_id_from_contract(contract):
        # TODO: Just use the contract id
        if not contract.m_conId:        # 0 is default
            raise ValueError('Invalid contract ID {} for contract {}'.format(contract.m_conId, obj2dict(contract)))
        return contract.m_conId


    #########################################
    # Message Handlers
    def _handle_message(self, msg):
        """Root message handler, dispatches to methods named `_typeName`.

        E.g., `tickString` messages are dispatched to `self._tickString()`.
        """
        if self.verbose >= 5:
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
        """Handle error messages from the API."""
        code = getattr(msg, 'errorCode', None)
        if code in BENIGN_ERRORS:
            return
        if code in DISCONNECT_ERRORS:
            self.connected = False
        if not isinstance(code, int):
            self.log.error(str(msg))
        elif 2100 <= code < 2200:
            self.log.warn(msg.errorMsg + ' [{}]'.format(msg.errorCode))
        else:
            if code in ORDER_RELATED_ERRORS:         # TODO: Some of these are actually warnings (like 399, sometimes...?)...
                order = self._orders.get(msg.id)
                if order:
                    order.cancelled = True
                    order.open = False
                    order.message = msg.errorMsg
                    self.log.error('ORDER ERR %d %s', code, order)
                    # TODO: This "error" changes the price but does not cancel (not sure of code): "Order Message:\nSELL 2 ES DEC'16\nWarning: Your order was repriced so as not to cross a related resting order"
                    self._call_order_handlers(order)

            if code in TICKER_RELATED_ERRORS:
                self.log.error(str(msg))
                err_q = self._tick_errors.get(msg.id)       # register() puts a Queue here and waits for any errors (with timeout)
                if err_q is None:
                    self.log.warn('Got ticker error for unexpected request id {}: {} [{}]'.format(msg.id, msg.errorMsg, code))
                else:
                    err_q.put_nowait(ValueError('{} [{}]'.format(msg.errorMsg, code)))

            if code in CONTRACT_REQUEST_ERRORS:
                self.log.error(str(msg))
                if msg.id >= len(self._contract_details):
                    self.log.error('No request slot for contract details {} found'.format(msg.id))
                else:
                    self._contract_details[msg.id].put_nowait(ValueError(msg.errorMsg))
                    self._contract_details[msg.id].put_nowait(None)     # None signals end of messages in queue

    def _managedAccounts(self, msg):
        """Save the account number."""
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
        """Sets next valid order ID."""
        if msg.orderId >= self.__next_order_id:
            self.__next_order_id = msg.orderId
        else:
            self.log.warn('nextValidId {} less than current id {}'.format(msg.orderId, self.__next_order_id))

    def _contractDetails(self, msg):
        """Callback for reqContractDetails.  Called multiple times with all possible matches for one request,
        followed by a contractDetailsEnd.  We put the responses in a Queue (self._contract_details[req_id]),
        followed by None to indicate the end."""
        self.log.debug('DETAILS %d %s', msg.reqId, obj2dict(msg.contractDetails))
        if msg.reqId >= len(self._contract_details):
            self.log.error('Could not find contract details slot %d for %s', msg.reqId, obj2dict(msg.contractDetails))
        else:
            self._contract_details[msg.reqId].put_nowait(msg.contractDetails)

    def _contractDetailsEnd(self, msg):
        """Called after all contractDetails messages for a given request have been sent.  Stuffs None into the Queue
        for the request ID to indicate the end."""
        self.log.debug('DETAILS END %s', msg)
        if msg.reqId >= len(self._contract_details):
            self.log.error('Could not find contract details slot %d for %s', msg.reqId, obj2dict(msg.contractDetails))
        else:
            self._contract_details[msg.reqId].put_nowait(None)

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
        if msg.status in ('ApiCanceled', 'Cancelled'):       # Inactive can mean error or not.  And yes, they appear to spell cancelled differently.
            if not order.cancelled:     # Only log the first time (can be dupes)
                self.log.info('CANCELLED %s', order)
            order.cancelled = True
            order.open = False
        elif msg.filled > abs(order.filled):      # Suppress duplicate / out-of-order fills  (order.filled is negative for sells)
            order.filled = int(math.copysign(msg.filled, order.quantity))
            order.avg_price = msg.avgFillPrice
            if order.filled == order.quantity:
                order.open = False
            self._call_order_handlers(order)

    def _openOrder(self, msg):
        """Called when orders are submitted and completed."""
        self.log.debug('STATE %d %s', msg.orderId, obj2dict(msg.orderState))
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
        elif msg.orderState.m_status == 'Filled':       # Filled means completely filled
            order.open = False
            self.log.info('COMPLETE %s avg price %f', order, order.avg_price)
        if msg.orderState.m_warningText:
            self.log.warn('Order %d: %s', msg.orderId, msg.orderState.m_warningText)
            order.message = msg.orderState.m_warningText

    def _execDetails(self, msg):
        """Called on order executions."""
        order = self._orders.get(msg.execution.m_orderId)
        if not order:
            self.log.error('Got execDetails for unknown orderId {}'.format(msg.execution.m_orderId))
            return
        exec = msg.execution
        # TODO: 5 digits of precision on price for forex
        self.log.info('EXEC %(symbol)s %(qty)d @ %(price).2f (%(total_qty)d filled) order %(id)d pos %(pos)d' % dict(time=exec.m_time, id=order.id, symbol=order.instrument.symbol, qty=int(math.copysign(exec.m_shares, order.quantity)), price=exec.m_price, total_qty=int(math.copysign(exec.m_cumQty, order.quantity)), pos=self.get_position(order.instrument)))
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
            # Call order handlers in commissionReport() instead of here so we can include commission info.

    def _position(self, msg):
        """Called when positions change; gives new position."""
        self.log.debug('POS %d %s %s', msg.pos, self._instrument_id_from_contract(msg.contract), obj2dict(msg.contract))
        self._positions[self._instrument_id_from_contract(msg.contract)] = msg.pos

    def _commissionReport(self, msg):
        """Called after executions; gives commission charge and PNL.  Calls order handlers."""
        # In theory we might be able to use orderState instead of commissionReport, but...
        # It's kinda whack.  Sometime's it's giant numbers, and there are dupes so it's hard to use.
        # TODO: We might want to guard against duplicate commissionReport messages.  Not sure if they happen or not.  But since we do accounting here...
        report = msg.commissionReport
        self.log.debug('COMM %s', vars(report))
        order = self._orders.get(self._executions.get(report.m_execId))
        if order:
            if 0 <= report.m_commission < CRAZY_HIGH_COMMISSION:        # We sometimes get bogus placeholder values
                order.commission += report.m_commission
            if -CRAZY_HIGH_PROFIT < report.m_realizedPNL < CRAZY_HIGH_PROFIT:
                order.profit += report.m_realizedPNL
            # TODO: We're potentially calling handlers more than once, here and in orderStatus
            # TODO: register() flag to say only fire on_order() events on totally filled, or cancel/error.
            self._call_order_handlers(order)
        else:
            self.log.error('No order found for execution {}'.format(report.m_execId))

    def _defaultHandler(self, msg):
        """Called when there is no other message handler for `msg`."""
        if self.verbose < 5:        # Don't log again if already logged in main handler
            self.log.debug('MSG %s', msg)


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


def choose_best_contract(details):
    """:Return: the "best" contract from the list of ``ContractDetails`` objects `details`, or None
    if there is no unambiguous best."""
    if not details:
        return None
    elif len(details) == 1:
        return details[0]

    types = frozenset(det.m_summary.m_secType for det in details)
    if len(types) == 1 and 'FUT' in types:      # Futures: choose nearest expiry
        best = min(details, key=lambda det: det.m_contractMonth)
    else:
        # TODO: Stocks, options, forex?
        return None
    return best


def obj2dict(obj):
    """Convert an (IBPy) object to a dict containing any fields with non-default values."""
    default = obj.__class__()
    return {field: val for field, val in vars(obj).items() if val != getattr(default, field, None)}


def iter_except(func, exception, first=None):
    """ Call a function repeatedly until an exception is raised.

    Converts a call-until-exception interface to an iterator interface.
    Like builtins.iter(func, sentinel) but uses an exception instead
    of a sentinel to end the loop.
    """
    try:
        if first is not None:
            yield first()            # For database APIs needing an initial cast to db.first()
        while True:
            yield func()
    except exception:
        pass


#############################################################


def main():
    """Simple test."""
    last_price = 0.0

    def on_tick(timestamp, price, size, volume, vwap):
        nonlocal last_price
        last_price = price
        timestamp = datetime.utcfromtimestamp(timestamp)
        print('{} price {:.2f} size {:.0f} vol {:.0f} vwap {:.2f}'.format(timestamp, price, size, volume, vwap))

    def on_order(order):
        print('order {} @ {}, profit ${:.2f}'.format(order.quantity, order.avg_price, order.profit))

    ib = IBroke(verbose=5)
    #inst = ib.get_instrument("AAPL"); quantity = 200
    #inst = ib.get_instrument('EUR', 'CASH', 'IDEALPRO'); quantity = 20000
    inst = ib.get_instrument("ES", "FUT", "GLOBEX", expiry="201612"); quantity = 1
    try:
        ib.register(inst, on_tick, on_order, aftermarket=True)
        for _ in range(20):
            time.sleep(random.random() * 30)
            if last_price:
                ib.cancel_all()
                time.sleep(0.5)
                ib.order_target(inst, quantity if random.random() > 0.5 else -quantity, limit=last_price)
    except KeyboardInterrupt:
        print('\nClosing...\n', file=sys.stderr)
        ib.cancel_all()
        ib.exit(inst)

    time.sleep(3)
    ib.exit(inst)
    time.sleep(3)
    ib.disconnect()
    time.sleep(0.5)


if __name__ == '__main__':
    main()
