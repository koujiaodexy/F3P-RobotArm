`timescale 1ns/1ps
// Dedicated 8N1 UART for JY61P. No sensor commands are sent at reset.
module jy61p_uart #(parameter integer CLK_HZ=133333333,
                    parameter integer DEFAULT_BAUD=115200)(
 input wire clk,rst_n,wr,input wire[7:0]addr,input wire[31:0]wdata,
 output reg[31:0]rdata,input wire rx,output wire tx);
 localparam integer DEFAULT_DIV=(CLK_HZ+DEFAULT_BAUD/2)/DEFAULT_BAUD;
 reg[31:0]divisor;
 (* ASYNC_REG="TRUE" *)reg rx_meta,rx_sync;
 reg[2:0]rx_state;reg[31:0]rx_timer;reg[2:0]rx_bit;
 reg[7:0]rx_shift,rx_byte;reg rx_valid,rx_bad;
 reg[7:0]fifo[0:511];reg[8:0]head,tail;reg[9:0]level;
 reg[31:0]rx_total,tx_total;reg[15:0]framing_errors,overflow_errors;
 reg config_fault;
 reg tx_busy;reg[9:0]tx_shift;reg[3:0]tx_bit;reg[31:0]tx_timer;
 wire baud_write=wr&&addr==8'haa;
 wire baud_valid=wdata>=16&&wdata<=CLK_HZ/1200&&!tx_busy;
 wire clear=wr&&addr==8'had&&wdata==32'h4a594300&&!tx_busy;
 wire reset_stream=clear||(baud_write&&baud_valid);
 wire pop=wr&&addr==8'hab&&wdata==32'h52585001&&level!=0&&!reset_stream;
 wire push=rx_valid&&(level<512||pop);
 wire send=wr&&addr==8'hac&&wdata[31:8]==24'h545800;
 assign tx=tx_busy?tx_shift[0]:1'b1;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin rx_meta<=1;rx_sync<=1;end
  else begin rx_meta<=rx;rx_sync<=rx_meta;end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin divisor<=DEFAULT_DIV;rx_state<=0;rx_timer<=0;rx_bit<=0;rx_shift<=0;rx_byte<=0;rx_valid<=0;rx_bad<=0;end
  else begin
   rx_valid<=0;rx_bad<=0;
   if(baud_write&&baud_valid)divisor<=wdata;
   if(reset_stream)begin rx_state<=0;rx_timer<=0;rx_bit<=0;end
   else case(rx_state)
    0:if(!rx_sync)begin rx_state<=1;rx_timer<=(divisor>>1)-1;end
    1:if(rx_timer!=0)rx_timer<=rx_timer-1;
      else if(rx_sync)rx_state<=0;
      else begin rx_state<=2;rx_timer<=divisor-1;rx_bit<=0;end
    2:if(rx_timer!=0)rx_timer<=rx_timer-1;
      else begin
       rx_shift[rx_bit]<=rx_sync;rx_timer<=divisor-1;
       if(rx_bit==7)rx_state<=3;else rx_bit<=rx_bit+1;
      end
    3:if(rx_timer!=0)rx_timer<=rx_timer-1;
      else if(rx_sync)begin rx_byte<=rx_shift;rx_valid<=1;rx_state<=0;end
      else begin rx_bad<=1;rx_state<=4;end
    4:if(rx_sync)rx_state<=0; // A held-low wire creates one framing error, not a flood.
    default:rx_state<=0;
   endcase
  end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   head<=0;tail<=0;level<=0;rx_total<=0;framing_errors<=0;overflow_errors<=0;config_fault<=0;
  end else if(reset_stream)begin
   head<=0;tail<=0;level<=0;rx_total<=0;framing_errors<=0;overflow_errors<=0;config_fault<=0;
  end else begin
   if(baud_write&&!baud_valid)config_fault<=1;
   if(send&&tx_busy)config_fault<=1;
   if(rx_bad&&framing_errors!=16'hffff)framing_errors<=framing_errors+1;
   if(rx_valid)begin
    rx_total<=rx_total+1;
    if(!push&&overflow_errors!=16'hffff)overflow_errors<=overflow_errors+1;
   end
   if(push)begin fifo[tail]<=rx_byte;tail<=tail+1;end
   if(pop)head<=head+1;
   case({push,pop})
    2'b10:level<=level+1;
    2'b01:level<=level-1;
    default:begin end
   endcase
  end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin tx_busy<=0;tx_shift<=10'h3ff;tx_bit<=0;tx_timer<=0;tx_total<=0;end
  else if(clear)begin tx_total<=0;tx_shift<=10'h3ff;end
  else if(tx_busy)begin
   if(tx_timer!=0)tx_timer<=tx_timer-1;
   else if(tx_bit==9)begin tx_busy<=0;tx_total<=tx_total+1;end
   else begin tx_bit<=tx_bit+1;tx_shift<={1'b1,tx_shift[9:1]};tx_timer<=divisor-1;end
  end else if(send)begin
   tx_busy<=1;tx_shift<={1'b1,wdata[7:0],1'b0};tx_bit<=0;tx_timer<=divisor-1;
  end
 end
 always @*begin
  rdata=0;
  case(addr)
   8'ha8:rdata=32'h4a593631;
   8'ha9:rdata={6'd0,level,10'd0,(rx_state!=0),config_fault,(framing_errors!=0),(overflow_errors!=0),tx_busy,(level!=0)};
   8'haa:rdata=divisor;
   8'hab:rdata=level?{23'd0,1'b1,fifo[head]}:32'd0;
   8'hac:rdata=tx_total;
   8'had:rdata=32'h00010000;
   8'hae:rdata=rx_total;
   8'haf:rdata={framing_errors,overflow_errors};
   default:begin end
  endcase
 end
endmodule
