#!/usr/bin/env python
"""
Cancel all outstanding orders and flatten all positions.  Use with caution.

This is a hard global cancel of all orders in an IB account, including those made by other
API clients and the TWS GUI.

This will liquidate all positions with market orders, which may be financially disadvantageous.
"""
import time

from ibroke import IBroke


def main():
    """Cancel open orders and flatten positions."""
    ib = IBroke(verbose=5, client_id=1)
    ib.flatten(instrument=None, hard_global_cancel=True)
    time.sleep(3)


if __name__ == '__main__':
    main()
