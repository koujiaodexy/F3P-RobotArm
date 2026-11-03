import_device dr1_90.db -package DR1M90GEG400 -speed 2
open_project vision60.prj -noanalyze
import_db vision60_pr.db
bitgen -bit coordinated-ptp.bit
puts COORDINATED_PTP_BITSTREAM_GENERATED
exit
