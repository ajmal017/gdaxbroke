# IBroke: Interactive Brokers for Humans

IBroke is a simple Python wrapper for the [Interactive Brokers](https://www.interactivebrokers.com/) API.
It is aimed at intraday (minute, second, tick) trading.

```
from time import sleep
from ibroke import IBroke

def on_bar(instrument, timestamp, open, high, low, close, volume, open_interest):
    print(instrument.symbol, timestamp, open, high, low, close, volume, open_interest, sep='\t')

ib = IBroke()
ib.register("AAPL", on_bar)
sleep(10)
```

IBroke wraps [IBPy](https://pypi.python.org/pypi/IbPy2) and provides a higher-level interface.

**What Is Implemented**: market data (quotes and OHLC bars), basic order management, profit and loss.

**What May Be Implemented**: historical data, account / portfolio data, complex order types, market depth (depth of book / Level II data).

**What Is Not Likely To Be Implemented**: backtesting, fundamentals data, news, market scanners, financial advisor functionality.

*Disclaimer*: This software comes with no warranty.  It may contain bugs that
cause you to lose money.  The author accepts no liability of any kind.  This
software is not affiliated in any way with Interactive Brokers, LLC.

Copyright 2016 Doctor J.  Licensed under the LGPL v3.