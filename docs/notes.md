IB / IBPy / IBroke Notes
========================

You must assign monotonically increasing order ids to your orders.
They only have to be monotonic per client ID, but they do persist across disconnects.
reqIds() will send one nextValidId which will give you the next highest unused number.

Positions and portfolio updates are shared between client IDs.

To get commission and PNL info you have to listen for commissionReport messages, which are generated for
every execution, and point to executions (not orders) with crazy string IDs.  So to tally commissions and PNL
per-order, you need to track a map of executions (with crazy string IDs) to orders.
You might try to use openOrder.orderState messages, but there are dupes and the commissions are often giant
placeholder values (and some other dollar values are strings...), and they don't have PNL.

NEXT:
-----

Prettier order display
Order cancel and cancel_all