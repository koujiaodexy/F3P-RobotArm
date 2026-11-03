`timescale 1ns/1ps
// Read-only observation. Never gates requests, ready, clocks, resets or data.
module camera_dma_diagnostics(
 input wire clk,rst_n,input wire[31:0]compact_state,compact_address,
 input wire[15:0]ps_signals,flags,input wire compact_pop,write_busy,read_busy,
 output reg[159:0]snapshot
);
 reg frozen;reg[31:0]gap;reg[15:0]write_length,read_length;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin frozen<=0;gap<=0;write_length<=0;read_length<=0;snapshot<=0;end
  else if(!compact_state[30])begin frozen<=0;gap<=0;write_length<=0;read_length<=0;end
  else if(!frozen)begin
   if(compact_pop)gap<=0;else if(gap!=32'hffffffff)gap<=gap+1'b1;
   if(!write_busy)write_length<=0;else if(write_length!=16'hffff)write_length<=write_length+1'b1;
   if(!read_busy)read_length<=0;else if(read_length!=16'hffff)read_length<=read_length+1'b1;
   snapshot<={read_length,write_length,gap,{compact_state[31],flags[14:0],ps_signals},compact_address,compact_state};
   if(compact_state[31])frozen<=1;
  end
 end
endmodule
