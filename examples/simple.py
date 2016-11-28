#!/usr/bin/env python3
"""
Simple example using the IBroke Interactive Brokers API.
"""
from time import sleep
from ibroke import IBroke

def on_bar(instrument, timestamp, open, high, low, close, volume, open_interest):
    print(instrument.symbol, timestamp, open, high, low, close, volume, open_interest, sep='\t')

ib = IBroke()
ib.register("AAPL", on_bar)
sleep(10)
