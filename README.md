IBroke: Interactive Brokers for Humans
======================================

IBroke is a simple Python wrapper for the [Interactive Brokers](https://www.interactivebrokers.com/) API.
It is aimed at intraday (minute, second, tick) trading.

```
from time import sleep

from ibroke import IBroke


def on_tick(timestamp, price, size, volume, vwap):
    print(timestamp, price, size, volume, vwap, sep='\t')


ib = IBroke()
ib.register("AAPL", on_tick)
sleep(10)
```

*Disclaimer*: This software comes with no warranty.  It may contain bugs that
cause you to lose money.  The author accepts no liability of any kind.  This
software is not affiliated in any way with Interactive Brokers, LLC.

Copyright 2016 Doctor J.  Licensed under the LGPL v3.