#!/usr/bin/env python3
"""
Simple example using the IBroke Interactive Brokers API.
"""
from time import sleep
from ibroke import IBroke

def on_bar(instrument, timestamp, open, high, low, close, volume, open_interest):
    """Called every second with OHLC bar information."""
    print(instrument.symbol, timestamp, open, high, low, close, volume, open_interest, sep='\t')

ib = IBroke()       # Connects to a locally running TWS on port 7497 by default
ib.register("AAPL", on_bar, bar_size=1)     # Call `on_bar()` every 1 second with OHLC bars for Apple stock
sleep(10)
