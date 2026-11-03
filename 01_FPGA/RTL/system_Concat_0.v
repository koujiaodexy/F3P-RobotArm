/************************************************************\
**	Copyright (c) 2012-2025 Anlogic Inc.
**	All Right Reserved.
\************************************************************/
/************************************************************\
**	Build time: Oct 04 2025 18:48:55
**	TD version	:	6.2.175876
************************************************************/
module system_Concat_0
(
  input   [0:0]                 In0,
  input   [0:0]                 In1,
  input   [0:0]                 In2,
  output  [2:0]                 Dout
);

  Concat_fe5c73756bec
  #(
      .PORT_NUM(3),
      .IN_WIDTH_0(1),
      .IN_WIDTH_1(1),
      .IN_WIDTH_2(1),
      .OUT_WIDTH(3)
  )Concat_fe5c73756bec_Inst
  (
      .In0(In0),
      .In1(In1),
      .In2(In2),
      .Dout(Dout)
  );
endmodule
