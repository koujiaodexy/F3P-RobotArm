/************************************************************\
**	Copyright (c) 2012-2025 Anlogic Inc.
**	All Right Reserved.
\************************************************************/
/************************************************************\
**	Build time: Sep 30 2025 16:28:09
**	TD version	:	6.2.175876
************************************************************/
module system_ChipWatcher_0
(
  input   [0:0]                 probe0,
  input   [0:0]                 probe1,
  input   [0:0]                 probe2,
  input   [0:0]                 probe3,
  input   [0:0]                 probe4,
  input                         clk
);

  ChipWatcher_ccd60ae86889  ChipWatcher_ccd60ae86889_Inst
  (
      .probe0(probe0),
      .probe1(probe1),
      .probe2(probe2),
      .probe3(probe3),
      .probe4(probe4),
      .clk(clk)
  );
endmodule
