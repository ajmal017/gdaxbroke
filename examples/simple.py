#!/usr/bin/env python3
"""Simple example using the IBroke Interactive Brokers API."""
from time import sleep
from gbroke import GBroke

def on_bar(instrument, bar):
    """Called every second with market data `bar` namedtuple."""
    print(instrument.symbol, bar)

gb = GBroke(wsurl = 'wss://ws-feed-public.sandbox.gdax.com')       # Connects to a locally running TWS on port 7497 by default
instrument = gb.register("BTC-USD", on_bar, bar_size=1)     # Call `on_bar()` every 1 second with Bar namedtuple for Apple stock
print ("instrucment:",instrument)

pos = gb.get_position(instrument)
print('pos:',pos)

#gb.watch_bookorder(instrument)
#sleep(10)

gb.order_target(instrument,0.01)

print('pos:',gb.get_position(instrument))
sleep(10000)
