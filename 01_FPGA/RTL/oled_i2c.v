`timescale 1ns/1ps
// Single-controller I2C packet writer; external pull-ups must be to 3.3 V.
// Never drives a logic 1. OLED transfers cannot change motor registers.
module oled_i2c #(parameter integer CLK_HZ=133333333,
                  parameter integer BUS_HZ=100000,
                  parameter integer TIMEOUT_MS=2)(
 input wire clk,rst_n,wr,input wire[7:0]addr,input wire[31:0]wdata,
 output reg[31:0]rdata,inout wire scl,sda);
 localparam integer HALF=(CLK_HZ+2*BUS_HZ-1)/(2*BUS_HZ);
 localparam integer HOLD=(CLK_HZ/1000000<1)?1:CLK_HZ/1000000;
 localparam integer TIMEOUT=(CLK_HZ/1000)*TIMEOUT_MS;
 localparam integer PACKET_TIMEOUT=(CLK_HZ/1000)*10;
 localparam IDLE=0,START_WAIT=1,START_HOLD=2,BIT_LOW=3,BIT_HIGH=4,
            ACK_LOW=5,ACK_HIGH=6,ACK_END=7,STOP_LOW=8,STOP_HIGH=9,STOP_RELEASE=10;
 reg[3:0]state;reg scl_low,sda_low;
 assign scl=scl_low?1'b0:1'bz;
 assign sda=sda_low?1'b0:1'bz;
 (* ASYNC_REG="TRUE" *)reg scl_meta,scl_sync,sda_meta,sda_sync;
 reg[7:0]fifo[0:31];reg[5:0]count,length,byte_index;reg[2:0]bit_index;
 reg[31:0]timer,stretch_timer,packet_timer,completed,errors;
 reg nack_fault,timeout_fault,overflow_fault;
 wire busy=(state!=IDLE);
 wire line_wait=(state==START_WAIT&&(!scl_sync||!sda_sync)) ||
   ((state==BIT_HIGH||state==ACK_HIGH||state==STOP_HIGH)&&!scl_sync) ||
   (state==STOP_RELEASE&&!sda_sync);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin scl_meta<=1;scl_sync<=1;sda_meta<=1;sda_sync<=1;end
  else begin scl_meta<=scl;scl_sync<=scl_meta;sda_meta<=sda;sda_sync<=sda_meta;end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   state<=IDLE;scl_low<=0;sda_low<=0;count<=0;length<=0;byte_index<=0;bit_index<=7;
   timer<=0;stretch_timer<=0;packet_timer<=0;completed<=0;errors<=0;
   nack_fault<=0;timeout_fault<=0;overflow_fault<=0;
  end else begin
   if(line_wait)stretch_timer<=stretch_timer+1;else stretch_timer<=0;
   if(busy)packet_timer<=packet_timer+1;else packet_timer<=0;
   if(busy&&((line_wait&&stretch_timer>=TIMEOUT-1)||packet_timer>=PACKET_TIMEOUT-1))begin
    // A missing/stuck device must never hold up the motor control bus.
    state<=IDLE;scl_low<=0;sda_low<=0;count<=0;timer<=0;
    timeout_fault<=1;errors<=errors+1;stretch_timer<=0;
   end else case(state)
    IDLE:begin scl_low<=0;sda_low<=0;timer<=0;end
    START_WAIT:begin
     if(!scl_sync||!sda_sync)timer<=0;
     else if(timer>=HALF-1)begin timer<=0;sda_low<=1;state<=START_HOLD;end
     else timer<=timer+1;
    end
    START_HOLD:if(timer>=HALF-1)begin timer<=0;scl_low<=1;state<=BIT_LOW;end
               else timer<=timer+1;
    BIT_LOW:begin
     if(timer==HOLD)sda_low<=!fifo[byte_index][bit_index];
     if(timer>=HALF-1)begin timer<=0;scl_low<=0;state<=BIT_HIGH;end
     else timer<=timer+1;
    end
    BIT_HIGH:begin
     if(!scl_sync)timer<=0;
     else if(timer>=HALF-1)begin
      timer<=0;scl_low<=1;
      if(bit_index==0)state<=ACK_LOW;
      else begin bit_index<=bit_index-1;state<=BIT_LOW;end
     end else timer<=timer+1;
    end
    ACK_LOW:begin
     if(timer==HOLD)sda_low<=0;
     if(timer>=HALF-1)begin timer<=0;scl_low<=0;state<=ACK_HIGH;end
     else timer<=timer+1;
    end
    ACK_HIGH:begin
     if(!scl_sync)timer<=0;
     else if(timer>=HALF-1)begin
      timer<=0;scl_low<=1;state<=ACK_END;
      if(sda_sync)begin nack_fault<=1;errors<=errors+1;end
     end else timer<=timer+1;
    end
    ACK_END:if(timer>=HALF-1)begin
     timer<=0;
     if(nack_fault||byte_index+1>=length)state<=STOP_LOW;
     else begin byte_index<=byte_index+1;bit_index<=7;state<=BIT_LOW;end
    end else timer<=timer+1;
    STOP_LOW:begin
     if(timer==HOLD)sda_low<=1;
     if(timer>=HALF-1)begin timer<=0;scl_low<=0;state<=STOP_HIGH;end
     else timer<=timer+1;
    end
    STOP_HIGH:begin
     if(!scl_sync)timer<=0;
     else if(timer>=HALF-1)begin timer<=0;sda_low<=0;state<=STOP_RELEASE;end
     else timer<=timer+1;
    end
    STOP_RELEASE:begin
     if(!sda_sync)timer<=0;
     else if(timer>=HALF-1)begin timer<=0;state<=IDLE;count<=0;completed<=completed+1;end
     else timer<=timer+1;
    end
    default:begin state<=IDLE;scl_low<=0;sda_low<=0;end
   endcase
   if(wr&&!busy)case(addr)
    8'ha4:if(count<32)begin fifo[count]<=wdata[7:0];count<=count+1;end
          else begin overflow_fault<=1;errors<=errors+1;end
    8'ha5:begin
     if(wdata==32'h4f4c0000)begin count<=0;nack_fault<=0;timeout_fault<=0;overflow_fault<=0;end
     else if(wdata==32'h4f4c0001&&count!=0&&!nack_fault&&!timeout_fault&&!overflow_fault)begin
      state<=START_WAIT;length<=count;byte_index<=0;bit_index<=7;timer<=0;stretch_timer<=0;
     end
    end
    default:begin end
   endcase
  end
 end
 always @*begin
  rdata=0;
  case(addr)
   8'ha2:rdata=32'h4f4c4431;
   8'ha3:rdata={28'd0,overflow_fault,timeout_fault,nack_fault,busy};
   8'ha4:rdata={26'd0,count};
   8'ha5:rdata=completed;
   8'ha6:rdata=errors;
   8'ha7:rdata=HALF;
   default:begin end
  endcase
 end
endmodule
