#!/usr/bin/env python3
"""
Simple example using the IBroke Interactive Brokers API.
"""
from time import sleep

from ibroke import IBroke


def on_tick(timestamp, price, size, volume, vwap):
    print(timestamp, price, size, volume, vwap, sep='\t')


ib = IBroke()
ib.register("AAPL", on_tick)
sleep(10)

