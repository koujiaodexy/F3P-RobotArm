`timescale 1ns/1ps
// IMX415 16-bit register addresses, ACK checked at each of four I2C bytes.
module imx415_init #(parameter TICK=60, parameter GAP=24000, parameter START_WAIT=240000)(
 input wire clk,rst_n, output reg scl, inout wire sda,
 output reg configured,failed,output wire [31:0] debug
);
 reg release_sda;assign sda=release_sda?1'bz:1'b0;
 reg [3:0] state;reg [31:0] delay_count;reg [15:0] tick_count;
 reg [8:0] index;reg [1:0] byte_index;reg [3:0] bit_index;reg [7:0] value;
 wire [31:0] lut;wire [7:0] lut_size;
 ui_imx415reg lut_instance(.REG_INDEX(index),.REG_DATA(lut),.REG_SIZE(lut_size));
 wire [23:0] word_value=index==201?24'h300000:index==202?24'h300200:lut[23:0];
 localparam WAIT=0,START_A=1,START_B=2,LOW=3,RISE=4,HIGH=5,FALL=6,STOP_LOW=7,STOP_HIGH=8,STOP_RELEASE=9,DONE=10;
 wire [31:0] wait_limit=index==0?START_WAIT:index>=201?START_WAIT*5:GAP;
 assign debug={12'd0,state,index,byte_index,bit_index,failed};
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=WAIT;delay_count<=0;tick_count<=0;index<=0;byte_index<=0;bit_index<=0;value<=8'h34;
   scl<=1;release_sda<=1;configured<=0;failed<=0;
  end else if(state==WAIT)begin
   if(delay_count>=wait_limit-1)begin
    // A stuck-low SDA must not masquerade as 203 successful ACKs.
    if(sda!==1'b1)begin failed<=1;state<=DONE;end
    else begin state<=START_A;delay_count<=0;tick_count<=0;byte_index<=0;bit_index<=0;value<=8'h34;end
   end
   else delay_count<=delay_count+1;
  end else if(state!=DONE)begin
   if(tick_count==TICK-1)begin
    tick_count<=0;
    case(state)
     START_A:begin scl<=1;release_sda<=1;state<=START_B;end
     START_B:begin release_sda<=0;state<=LOW;end
     LOW:begin scl<=0;release_sda<=bit_index==8?1'b1:value[7-bit_index];state<=RISE;end
     RISE:begin scl<=1;state<=HIGH;end
     HIGH:begin if(bit_index==8&&sda!==1'b0)failed<=1;state<=FALL;end
     FALL:begin
      scl<=0;
      if(bit_index==8)begin
       bit_index<=0;
       if(byte_index==3)state<=STOP_LOW;
       else begin
        byte_index<=byte_index+1;
        case(byte_index)
         0:value<=word_value[23:16];1:value<=word_value[15:8];2:value<=word_value[7:0];
        endcase
        state<=LOW;
       end
      end else begin bit_index<=bit_index+1;state<=LOW;end
     end
     STOP_LOW:begin scl<=0;release_sda<=0;state<=STOP_HIGH;end
     STOP_HIGH:begin scl<=1;state<=STOP_RELEASE;end
     STOP_RELEASE:begin
      release_sda<=1;
      if(failed)state<=DONE;
      else if(index==202)begin configured<=1;state<=DONE;end
      else begin index<=index+1;state<=WAIT;delay_count<=0;end
     end
     default:state<=DONE;
    endcase
   end else tick_count<=tick_count+1;
  end
 end
endmodule
