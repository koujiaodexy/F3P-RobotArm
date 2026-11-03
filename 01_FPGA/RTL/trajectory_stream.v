`timescale 1ns/1ps
// V9 exclusive CAN trajectory engine. A FIFO entry is six signed pulse targets
// and six (ACC[23:16], RPM[15:0]) words, seq[415:384], final[416].
// Every target is staged with Emm FD sync=1. Only a complete acknowledged batch
// may be released by FF. Ordinary V8 control remains in its separate engine.
module trajectory_stream #(
 parameter integer CLK_HZ=50000000,
 parameter integer TICK_TICKS=CLK_HZ/25,
 parameter integer REPLY_TICKS=CLK_HZ/200,
 parameter integer WATCHDOG_TICKS=CLK_HZ/4,
 parameter integer DEPTH=32
)(
 input wire clk_i,rst_ni,legacy_idle_i,
 input wire ctl_pulse_i, input wire [2:0] ctl_i,
 input wire commit_pulse_i, input wire [416:0] frame_i,
 input wire heartbeat_i,
 output wire owned_o,running_o,draining_o,stop_done_o,final_sent_o,stopping_o,
 output reg fault_o, output reg [31:0] error_o,
 output wire [5:0] count_o,output reg [31:0] accepted_seq_o,fired_seq_o,
 output reg [5:0] stop_mask_o,
 output wire tx_abort_o,output reg tx_valid_o,input wire tx_ready_i,tx_done_i,tx_error_i,
 output reg [28:0] tx_id_o,output reg [3:0] tx_dlc_o,output reg [63:0] tx_data_o,
 input wire rx_valid_i,rx_extended_i,input wire [28:0] rx_id_i,
 input wire [3:0] rx_dlc_i,input wire [63:0] rx_data_i,
 output reg [1535:0] feedback_o,output reg feedback_toggle_o,
 output reg [31:0] now_ms_o
);
 localparam IDLE=0,PREFILL=1,Q_SEND=2,Q_TX=3,Q_WAIT=4,LOAD=5,
  FD_FIRST=6,FD_FIRST_TX=7,FD_SECOND=8,FD_SECOND_TX=9,FD_ACK=10,
  WAIT_TICK=11,FF_SEND=12,FF_TX=13,STOP_SEND=14,STOP_TX=15,
  STOP_WAIT=16,SETTLE=17,TERMINAL=18,DRAIN_WAIT=19,FF_ACK=20,STOP_QUIET=21;
 reg [4:0] state;
 reg owned,running,draining,final_sent,final_queued;
 reg [416:0] fifo[0:DEPTH-1]; reg [4:0] wr_ptr,rd_ptr; reg [5:0] count;
 reg [416:0] current_frame;
 reg [31:0] clock_tick,next_tick,reply_timer,watchdog,settle_timer;
 reg [31:0] ms_div;
 reg [2:0] axis; reg [1:0] query_kind; reg query_initial;
 reg [31:0] feedback_sequence;
 reg [31:0] position_mag[0:5],position_sign[0:5],motor_flags[0:5],home_flags[0:5];
 reg [31:0] position_time[0:5],motor_time[0:5],home_time[0:5];
 reg [31:0] position_seq[0:5],motor_seq[0:5],home_seq[0:5];
 // Feedback snapshot: per axis 8 words: sign+flags, magnitude, position/motor/home
 // timestamps, position/motor/home sequence counters. Snapshot is held across CDC.
 reg snapshot_pending;
 integer i;
 wire [31:0] pulse_word=current_frame[axis*64 +: 32];
 wire [31:0] parameters=current_frame[axis*64+32 +: 32];
 wire [31:0] magnitude=pulse_word[31] ? (~pulse_word+1'b1) : pulse_word;
 wire [7:0] query_function=(query_kind==0)?8'h36:(query_kind==1)?8'h3A:8'h3B;
 wire reply_address=rx_valid_i && rx_extended_i && rx_id_i==((axis+29'd1)<<8);
 wire ack_ok=reply_address && rx_dlc_i==3 && rx_data_i[23:16]==8'h6B;
 wire is_stop_state=state==STOP_QUIET||state==STOP_SEND||state==STOP_TX||state==STOP_WAIT||state==SETTLE||state==TERMINAL;
 wire past_tick=$signed(clock_tick-next_tick)>=0;
 wire pop=(state==LOAD && count!=0);
 wire commit_ok=commit_pulse_i && owned && !final_queued && !fault_o &&
   (state==PREFILL || running) && count<DEPTH && frame_i[415:384]==accepted_seq_o+1;
 assign tx_abort_o=owned && state==STOP_QUIET;
 assign stopping_o=is_stop_state&&state!=TERMINAL;
 assign owned_o=owned; assign running_o=running; assign draining_o=draining;
 assign final_sent_o=final_sent; assign count_o=count;
 assign stop_done_o=owned && state==TERMINAL && stop_mask_o==6'b111111;
 function [15:0] speed_limit;
 input integer n; begin case(n) 0,1,2:speed_limit=3000;3:speed_limit=700;4:speed_limit=373;5:speed_limit=16;default:speed_limit=0;endcase end endfunction
 reg valid_frame;
 integer j;
 always @* begin
  valid_frame=1;
  for(j=0;j<6;j=j+1)
   if(frame_i[j*64+32 +: 16]==0 || frame_i[j*64+32 +:16]>speed_limit(j) || frame_i[j*64+56 +:8]!=0) valid_frame=0;
 end
 task stop_all; input [31:0] reason; begin
  state<=STOP_QUIET;axis<=0;running<=0;draining<=0;count<=0;wr_ptr<=0;rd_ptr<=0;
  stop_mask_o<=0;reply_timer<=0;watchdog<=0;final_queued<=0;
  if(reason!=0) begin fault_o<=1;error_o<=reason;end
 end endtask
 task next_stop; begin
  reply_timer<=0;
  if(axis==5) begin state<=SETTLE;settle_timer<=0;end
  else begin axis<=axis+1'b1;state<=STOP_SEND;end
 end endtask
 always @* begin
  tx_valid_o=0;tx_id_o=(axis+29'd1)<<8;tx_dlc_o=0;tx_data_o=0;
  case(state)
   Q_SEND:begin tx_valid_o=1;tx_dlc_o=2;tx_data_o={48'd0,8'h6B,query_function};end
   FD_FIRST:begin tx_valid_o=1;tx_dlc_o=8;tx_data_o={magnitude[15:8],magnitude[23:16],magnitude[31:24],parameters[23:16],parameters[7:0],parameters[15:8],7'd0,pulse_word[31],8'hFD};end
   FD_SECOND:begin tx_valid_o=1;tx_id_o=((axis+29'd1)<<8)|1;tx_dlc_o=5;tx_data_o={24'd0,8'h6B,8'h01,8'h01,magnitude[7:0],8'hFD};end
   FF_SEND:begin tx_valid_o=1;tx_id_o=0;tx_dlc_o=3;tx_data_o=64'h6B66FF;end
   STOP_SEND:begin tx_valid_o=1;tx_dlc_o=4;tx_data_o=64'h6B0098FE;end
  endcase
  // Do not dispatch a new CAN frame on the same cycle as cancel/watchdog.
  if((ctl_pulse_i && ctl_i==3) || ((running||draining)&&watchdog>=WATCHDOG_TICKS)) tx_valid_o=0;
 end
 always @(posedge clk_i or negedge rst_ni) begin
  if(!rst_ni) begin
   state<=IDLE;owned<=0;running<=0;draining<=0;final_sent<=0;final_queued<=0;
   count<=0;wr_ptr<=0;rd_ptr<=0;current_frame<=0;accepted_seq_o<=0;fired_seq_o<=0;
   fault_o<=0;error_o<=0;stop_mask_o<=0;clock_tick<=0;next_tick<=0;reply_timer<=0;watchdog<=0;
   settle_timer<=0;axis<=0;query_kind<=0;query_initial<=0;ms_div<=0;now_ms_o<=0;
   feedback_o<=0;feedback_toggle_o<=0;snapshot_pending<=0;feedback_sequence<=0;
   for(i=0;i<6;i=i+1) begin position_mag[i]<=0;position_sign[i]<=0;motor_flags[i]<=0;home_flags[i]<=0;position_time[i]<=0;motor_time[i]<=0;home_time[i]<=0;position_seq[i]<=0;motor_seq[i]<=0;home_seq[i]<=0;end
  end else begin
   clock_tick<=clock_tick+1'b1;reply_timer<=reply_timer+1'b1;
   if(ms_div>=CLK_HZ/1000-1) begin ms_div<=0;now_ms_o<=now_ms_o+1'b1;end else ms_div<=ms_div+1'b1;
   if(heartbeat_i)watchdog<=0;else if(running||draining)watchdog<=watchdog+1'b1;
   if(snapshot_pending) begin
    for(i=0;i<6;i=i+1) begin
     feedback_o[i*256 +:32]<={8'd0,home_flags[i][7:0],motor_flags[i][7:0],position_sign[i][7:0]};
     feedback_o[i*256+32 +:32]<=position_mag[i];
     feedback_o[i*256+64 +:32]<=position_time[i];feedback_o[i*256+96 +:32]<=motor_time[i];feedback_o[i*256+128 +:32]<=home_time[i];
     feedback_o[i*256+160 +:32]<=position_seq[i];feedback_o[i*256+192 +:32]<=motor_seq[i];feedback_o[i*256+224 +:32]<=home_seq[i];
    end
    feedback_toggle_o<=~feedback_toggle_o;snapshot_pending<=0;
   end
   if(commit_ok && valid_frame) begin
    fifo[wr_ptr]<=frame_i;wr_ptr<=wr_ptr+1'b1;accepted_seq_o<=frame_i[415:384];
    if(frame_i[416])final_queued<=1;
   end
   case({commit_ok && valid_frame,pop})
    2'b10:count<=count+1'b1;2'b01:count<=count-1'b1;default:begin end
   endcase
   if(pop)begin current_frame<=fifo[rd_ptr];rd_ptr<=rd_ptr+1'b1;end
   if(ctl_pulse_i && ctl_i==1 && !owned && legacy_idle_i) begin
    owned<=1;state<=PREFILL;count<=0;wr_ptr<=0;rd_ptr<=0;accepted_seq_o<=0;fired_seq_o<=0;
    fault_o<=0;error_o<=0;stop_mask_o<=0;final_sent<=0;final_queued<=0;running<=0;draining<=0;watchdog<=0;
    for(i=0;i<6;i=i+1)begin position_seq[i]<=0;motor_seq[i]<=0;home_seq[i]<=0;end
    snapshot_pending<=1;
   end else if(ctl_pulse_i && ctl_i==3 && owned) begin stop_all(0);
   end else if((running||draining)&&watchdog>=WATCHDOG_TICKS)begin stop_all(32'hFFFF3101);
   end else if(ctl_pulse_i && ctl_i==4 && stop_done_o)begin owned<=0;state<=IDLE;
   end else if(commit_pulse_i && owned && (!commit_ok || !valid_frame))begin stop_all(32'hFFFF3102);
   end else if(running && !query_initial && past_tick &&
      (state==Q_SEND||state==Q_TX||state==Q_WAIT||state==LOAD||state==FD_FIRST||state==FD_FIRST_TX||state==FD_SECOND||state==FD_SECOND_TX||state==FD_ACK))begin stop_all(32'hFFFF3103);
   end else begin
    case(state)
     IDLE:begin end
     PREFILL:if(ctl_pulse_i && ctl_i==2)begin
      if(count>=4 || (count>0&&final_queued))begin
       running<=1;query_initial<=1;axis<=0;query_kind<=0;state<=Q_SEND;reply_timer<=0;watchdog<=0;
      end else stop_all(32'hFFFF3104);
     end
     Q_SEND:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3201);
       else if(tx_valid_o&&tx_ready_i)begin state<=Q_TX;reply_timer<=0;end
     Q_TX:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3202);
       else if(tx_done_i)begin state<=Q_WAIT;reply_timer<=0;end
     Q_WAIT:begin
      if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3203);
      else if(reply_address && rx_data_i[7:0]==query_function &&
       ((query_kind==0&&rx_dlc_i==7&&rx_data_i[55:48]==8'h6B&&rx_data_i[15:8]<=1)||(query_kind!=0&&rx_dlc_i==3&&rx_data_i[23:16]==8'h6B)))begin
       feedback_sequence<=feedback_sequence+1'b1;snapshot_pending<=1;
       if(query_kind==0)begin position_sign[axis]<=rx_data_i[15:8];position_mag[axis]<={rx_data_i[23:16],rx_data_i[31:24],rx_data_i[39:32],rx_data_i[47:40]};position_time[axis]<=now_ms_o;position_seq[axis]<=feedback_sequence+1'b1;end
       if(query_kind==1)begin motor_flags[axis]<=rx_data_i[15:8];motor_time[axis]<=now_ms_o;motor_seq[axis]<=feedback_sequence+1'b1;end
       if(query_kind==2)begin home_flags[axis]<=rx_data_i[15:8];home_time[axis]<=now_ms_o;home_seq[axis]<=feedback_sequence+1'b1;end
       if((query_kind==1&&((rx_data_i[15:8]&8'h8C)!=0||!rx_data_i[8])) || (query_kind==2&&(rx_data_i[15:8]&8'h3F)!=8'h03))stop_all(32'hFFFF3204);
       else begin
        reply_timer<=0;
        if(query_kind!=2)begin query_kind<=query_kind+1'b1;state<=Q_SEND;end
        else if(axis!=5)begin axis<=axis+1'b1;query_kind<=0;state<=Q_SEND;end
        else begin
         axis<=0;query_kind<=0;
         if(draining)begin state<=DRAIN_WAIT;next_tick<=clock_tick+TICK_TICKS;end
         else begin state<=LOAD;if(query_initial)begin query_initial<=0;next_tick<=clock_tick+TICK_TICKS;end end
        end
       end
      end
     end
     DRAIN_WAIT:if(past_tick)begin state<=Q_SEND;reply_timer<=0;end
     LOAD:begin
      if(count==0)stop_all(32'hFFFF3105);
      else begin axis<=0;state<=FD_FIRST;reply_timer<=0;end
     end
     FD_FIRST:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3301);
       else if(tx_valid_o&&tx_ready_i)begin state<=FD_FIRST_TX;reply_timer<=0;end
     FD_FIRST_TX:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3302);
       else if(tx_done_i)begin state<=FD_SECOND;reply_timer<=0;end
     FD_SECOND:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3303);
       else if(tx_valid_o&&tx_ready_i)begin state<=FD_SECOND_TX;reply_timer<=0;end
     FD_SECOND_TX:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3304);
       else if(tx_done_i)begin state<=FD_ACK;reply_timer<=0;end
     FD_ACK:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3305);
       else if(ack_ok&&rx_data_i[7:0]==8'hFD&&rx_data_i[15:8]!=8'h9F)begin
        if(rx_data_i[15:8]!=8'h02)stop_all(32'hFFFF3306);
        else if(axis==5)begin state<=WAIT_TICK;reply_timer<=0;end
        else begin axis<=axis+1'b1;state<=FD_FIRST;reply_timer<=0;end
       end
     WAIT_TICK:if(past_tick)begin state<=FF_SEND;reply_timer<=0;end
     FF_SEND:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3401);
       else if(tx_valid_o&&tx_ready_i)begin state<=FF_TX;reply_timer<=0;end
     FF_TX:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3402);
       else if(tx_done_i)begin state<=FF_ACK;reply_timer<=0;end
     FF_ACK:if(tx_error_i||reply_timer>=REPLY_TICKS)stop_all(32'hFFFF3403);
       else if(rx_valid_i&&rx_extended_i&&rx_id_i==29'h100&&rx_dlc_i==3&&rx_data_i[23:16]==8'h6B&&rx_data_i[7:0]==8'hFF&&rx_data_i[15:8]!=8'h9F)begin
        if(rx_data_i[15:8]!=8'h02)stop_all(32'hFFFF3404);
        else begin
        fired_seq_o<=current_frame[415:384];next_tick<=next_tick+TICK_TICKS;
        if(current_frame[416])begin final_sent<=1;draining<=1;running<=0;end
        axis<=0;query_kind<=0;state<=Q_SEND;reply_timer<=0;
        end
       end
     // A cancelled CAN request may still be on the wire. Let its addressed
     // response clear before FE (same arbitration ID), preventing data collision.
     STOP_QUIET:if(tx_done_i||tx_error_i)reply_timer<=0;
       else if(reply_timer>=REPLY_TICKS)begin state<=STOP_SEND;reply_timer<=0;end
     STOP_SEND:if(tx_error_i||reply_timer>=REPLY_TICKS)begin fault_o<=1;if(!fault_o)error_o<=32'hFFFF3501;next_stop;end
       else if(tx_valid_o&&tx_ready_i)begin state<=STOP_TX;reply_timer<=0;end
     STOP_TX:if(tx_error_i||reply_timer>=REPLY_TICKS)begin fault_o<=1;if(!fault_o)error_o<=32'hFFFF3502;next_stop;end
       else if(tx_done_i)begin state<=STOP_WAIT;reply_timer<=0;end
     STOP_WAIT:if(tx_error_i||reply_timer>=REPLY_TICKS)begin fault_o<=1;if(!fault_o)error_o<=32'hFFFF3503;next_stop;end
       else if(ack_ok&&rx_data_i[7:0]==8'hFE)begin
        if(rx_data_i[15:8]==8'h02)stop_mask_o[axis]<=1;
        else begin fault_o<=1;if(!fault_o)error_o<=32'hFFFF3504;end
        next_stop;
       end
     SETTLE:if(settle_timer>=REPLY_TICKS*2)state<=TERMINAL;else settle_timer<=settle_timer+1'b1;
     TERMINAL:begin end
     default:stop_all(32'hFFFF31FF);
    endcase
   end
  end
 end
endmodule
