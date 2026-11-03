`timescale 1ns/1ps
// Dual-clock RAM with Gray pointers. Read responses are registered, one cycle.
module vision_async_fifo #(parameter AW=11,DW=64)(
 input wire rst_n,wclk,rclk,we,re,input wire[DW-1:0]di,
 output reg[DW-1:0]dout,output reg valid,
 output wire full,empty,output wire[AW:0]count
);
 reg[DW-1:0]mem[0:(1<<AW)-1];
 reg[AW:0]wp,rp,wg,rg,wg1,wg2,rg1,rg2;
 function[AW:0]binary;input[AW:0]g;integer j;begin binary[AW]=g[AW];for(j=AW-1;j>=0;j=j-1)binary[j]=binary[j+1]^g[j];end endfunction
 wire[AW:0]wn=wp+1'b1,rn=rp+1'b1;
 assign full=wg=={~rg2[AW:AW-1],rg2[AW-2:0]};
 assign empty=rg==wg2;assign count=binary(wg2)-rp;
 always @(posedge wclk)if(we&&!full)mem[wp[AW-1:0]]<=di;
 always @(posedge rclk)if(re&&!empty)dout<=mem[rp[AW-1:0]];
 always @(posedge wclk or negedge rst_n)begin
  if(!rst_n)begin wp<=0;wg<=0;rg1<=0;rg2<=0;end
  else begin rg1<=rg;rg2<=rg1;if(we&&!full)begin wp<=wn;wg<=(wn>>1)^wn;end end
 end
 always @(posedge rclk or negedge rst_n)begin
  if(!rst_n)begin rp<=0;rg<=0;wg1<=0;wg2<=0;valid<=0;end
  else begin wg1<=wg;wg2<=wg1;valid<=re&&!empty;if(re&&!empty)begin rp<=rn;rg<=(rn>>1)^rn;end end
 end
endmodule
