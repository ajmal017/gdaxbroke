#!/usr/bin/env python
"""
Record tick data to TSV files in the current directory.

By default, records data for USD-denominated GLOBEX futures.

Output goes to files of the form `symbol-sec_type-exchange-currency-expiry-strike-opt_type.tsv`
in the current directory.  Existing files are appended to.
"""

import sys, time, math, atexit
from datetime import datetime

from ibroke import IBroke, TICK_FIELDS


PRINT_EVERY = 10000      #: Print a message every this many ticks (per instrument)
SYMBOLS = {
    'AUD': 'Australian dollar',
    'BOS': 'Boston Housing Index',
    'BQX': 'CME E-Mini NASDAQ Biotechnology',
    'BRE': 'Brazilian Real in US Dollars',
    'CAD': 'Canadian dollar',
    'CB': 'CME Cash-Settled Butter Futures',
    'CHF': 'Swiss franc',
    'CHI': 'Chicago Housing Index',
    'CSC': 'Cheese',
    'CUS': 'Housing Index Composite',
    'CZK': 'Czech koruna',
    'DA': 'MILK CLASS III INDEX',
    'DEN': 'Denver Housing Index',
    'DY': 'CME DRY WHEY INDEX',
    'E7': 'European Monetary Union Euro',
    'EM': '1 Month LIBOR (Int. Rate)',
    'EMD': 'E-mini S&P Midcap 400 Futures',
    'ES': 'E-mini S&P 500',
    'EUR': 'European Monetary Union Euro',
    'GBP': 'British pound',
    'GDK': 'Class IV Milk - 200k lbs',
    'GE': 'GLOBEX Euro-Dollar',
    'GF': 'Feeder Cattle',
    'GSCI': 'S&P-GSCI Index',
    'HE': 'Lean Hogs',
    'HUF': 'Hungarian forint',
    'IBAA': 'Bovespa Index - USD',
    'ILS': 'Israeli Shekel in US Dollar',
    'IXB': 'Materials Select Sector Index',
    'IXE': 'Energy Select Sector Index',
    'IXI': 'Industrial Select Sector Index',
    'IXM': 'Financial Select Sector Index',
    'IXR': 'Consumer Staples Select Sector Index',
    'IXT': 'Technology Select Sector Index -',
    'IXU': 'Utilities Select Sector Index',
    'IXV': 'Health Care Select Sector Index',
    'IXY': 'Consumer Discretionary Select Sector Index',
    'J7': 'Japanese yen',
    'JPY': 'Japanese yen',
    'KRW': 'Korean Won',
    'LAV': 'Las Vegas Housing Index',
    'LAX': 'Los Angeles Housing Index',
    'LB': 'Random Length Lumber',
    'LE': 'Live Cattle',
    'M6A': 'Australian dollar',
    'M6B': 'British pound',
    'M6E': 'European Monetary Union Euro',
    'MCD': 'Canadian dollar',
    'MIA': 'Miami Housing Index',
    'MIR': 'Indian Rupee',
    'MJY': 'Japanese yen',
    'MSF': 'Swiss franc',
    'MXP': 'Mexican Peso',
    'NF': 'NON FAT DRY MILK INDEX',
    'NKD': 'Dollar Denominated Nikkei 225 Index',
    'NOK': 'Norwegian krone',
    'NQ': 'E-mini NASDAQ 100 Futures',
    'NYM': 'New York Housing Index',
    'NZD': 'New Zealand dollar',
    'PLN': 'Polish zloty',
    'RMB': 'CME Chinese Renminbi in US Dollar Cross Rate',
    'RUR': 'Russian Ruble in US Dollars',
    'SDG': 'San Diego Housing Index',
    'SEK': 'Swedish krona',
    'SFR': 'San Francisco Housing Index',
    'SGX': 'S&P 500 / Citigroup Growth Index',
    'SIR': 'Indian Rupee',
    'SMC': 'E-Mini S&P SmallCap 600 Futures',
    'SPX': 'S&P 500 Stock Index',
    'SVX': 'S&P 500 / Citigroup Value Index',
    'WDC': 'Washington DC Housing Index',
    'ZAR': 'South African Rand',
}


class TickRecorder:
    """Callable that handles ticks by writing to a file."""
    FIELDS = TICK_FIELDS[1:]       # Handle timestamp separately

    def __init__(self, instrument, file):
        """:param str,file file: a filename string or open-for-appending File object."""
        if isinstance(file, str):
            self.file = open(file, 'a')
        else:
            self.file = file
        self.prev = [None] * len(self.FIELDS)
        self.tick_count = 0
        print('{}\t{}\t{}'.format(datetime.utcnow().replace(microsecond=0), self.file.name, self.tick_count))

    def __call__(self, instrument, timestamp, *tick):
        assert len(tick) == len(self.prev) == len(self.FIELDS)
        if self.file.closed:
            return

        for idx, (field, prev, val) in enumerate(zip(self.FIELDS, self.prev, tick)):
            if math.isfinite(val) and val != prev:
                print(timestamp, field, val, sep='\t', file=self.file)
                self.prev[idx] = val

        self.tick_count += 1
        if self.tick_count % PRINT_EVERY == 0:
            print('{}\t{}\t{}'.format(datetime.utcnow().replace(microsecond=0), self.file.name, self.tick_count))

    def __del__(self):
        self.file.close()


def main(args):
    """Connect and register handlers to write data."""
    instruments = tuple((symbol, 'FUT', 'GLOBEX', 'USD') for symbol in SYMBOLS)
    ib = IBroke()
    for tup in instruments:
        instrument = ib.get_instrument(*tup)
        filename = '-'.join(map(str, instrument.tuple())) + '.tsv'
        recorder = TickRecorder(instrument, filename)
        ib.register(instrument, on_tick=recorder)
        atexit.register(recorder.__del__)

    while ib.connected:
        time.sleep(1)


if __name__ == '__main__':
    main(sys.argv)
