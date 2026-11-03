if {[catch {source vision60_flow.tcl} message]} {puts stderr "SHELF_FULL_FAILED: $message"; exit 1}
puts SHELF_FULL_ROUTE_COMPLETED
exit 0
