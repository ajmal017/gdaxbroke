#!/usr/bin/env python3
"""Simple example using the IBroke Interactive Brokers API."""
from time import sleep
from gbroke import IBroke

def on_bar(instrument, bar):
    """Called every second with market data `bar` namedtuple."""
    print(instrument.symbol, bar)

ib = IBroke()       # Connects to a locally running TWS on port 7497 by default
ib.register("AAPL", on_bar, bar_size=1)     # Call `on_bar()` every 1 second with Bar namedtuple for Apple stock
sleep(10)
