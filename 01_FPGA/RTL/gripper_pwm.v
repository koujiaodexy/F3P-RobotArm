`timescale 1ns/1ps
// MG996R signal generator. Power is external +5V_SERVO, never a GPIO supply.
module gripper_pwm #(parameter integer CLK_HZ=133333333,
                     parameter integer WATCHDOG_MS=2000)(
 input wire clk,rst_n,wr,input wire[7:0]addr,input wire[31:0]wdata,
 output reg[31:0]rdata,output wire pwm);
 localparam integer WD_US=WATCHDOG_MS*1000;
 reg[31:0]us_acc;reg[14:0]phase_us;
 reg[31:0]pending_us,committed_us,active_us,min_us,max_us,watchdog_us,frames;
 reg enabled,want_enabled,config_fault,watchdog_fault,operator_stop;
 wire tick_us=(us_acc>=CLK_HZ-1000000);
 wire frame_end=tick_us&&phase_us==19999;
 wire pulse_end=tick_us&&phase_us==active_us-1;
 wire disable_cmd=wr&&addr==8'hb3&&wdata==0;
 wire external_stop=wr&&addr==8'hb3&&wdata==32'h47525354;
 wire enable_cmd=wr&&addr==8'hb3&&wdata==32'h47525001;
 wire heartbeat=wr&&addr==8'hb6&&wdata==32'h47524842;
 wire valid_pulse=pending_us>=min_us&&pending_us<=max_us;
 wire accepted=enable_cmd&&valid_pulse&&!config_fault&&!watchdog_fault&&!operator_stop;
 wire bad_pulse=enable_cmd&&!valid_pulse;
 wire limit_write=wr&&(addr==8'hb4||addr==8'hb5);
 wire limit_valid=!enabled&&!want_enabled&&wdata>=500&&wdata<=2500&&
                  ((addr==8'hb4&&wdata<=max_us)||(addr==8'hb5&&wdata>=min_us));
 wire bad_limits=limit_write&&!limit_valid;
 wire expired=tick_us&&(enabled||want_enabled)&&watchdog_us>=WD_US-1&&!heartbeat&&!accepted;
 wire stop_request=disable_cmd||external_stop||operator_stop||bad_pulse||bad_limits||expired||config_fault||watchdog_fault;
 assign pwm=enabled&&(phase_us<active_us);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   us_acc<=0;phase_us<=0;pending_us<=1500;committed_us<=1500;active_us<=1500;
   min_us<=1000;max_us<=2000;watchdog_us<=0;frames<=0;
   enabled<=0;want_enabled<=0;config_fault<=0;watchdog_fault<=0;operator_stop<=0;
  end else begin
   // Fractional microsecond divider: bounded one-clock jitter, no cumulative drift.
   if(tick_us)us_acc<=us_acc+1000000-CLK_HZ;else us_acc<=us_acc+1000000;
   if(tick_us)begin
    if(phase_us==19999)begin phase_us<=0;frames<=frames+1;end
    else phase_us<=phase_us+1;
   end
   if(enabled||want_enabled)begin if(tick_us)watchdog_us<=watchdog_us+1;end
   else watchdog_us<=0;
   if(heartbeat||accepted)watchdog_us<=0;
   if(expired)watchdog_fault<=1;
   if(external_stop)operator_stop<=1;
   if(bad_pulse||bad_limits)config_fault<=1;
   if(stop_request)want_enabled<=0;
   else if(accepted)begin want_enabled<=1;committed_us<=pending_us;end
   // Never truncate an active pulse on a command/fault; suppress following pulses.
   if(stop_request||!want_enabled)begin
    if(!enabled||phase_us>=active_us||pulse_end)enabled<=0;
   end
   if(frame_end)begin
    if(want_enabled&&!stop_request)begin enabled<=1;active_us<=committed_us;end
    else enabled<=0;
   end
   if(wr)case(addr)
    8'hb2:pending_us<=wdata;
    8'hb3:if(wdata==32'h47524300&&!enabled&&!want_enabled)begin config_fault<=0;watchdog_fault<=0;operator_stop<=0;watchdog_us<=0;end
    8'hb4:if(limit_valid)min_us<=wdata;
    8'hb5:if(limit_valid)max_us<=wdata;
    default:begin end
   endcase
  end
 end
 always @*begin
  rdata=0;
  case(addr)
   8'hb0:rdata=32'h47525031;
   8'hb1:rdata={27'd0,operator_stop,want_enabled,watchdog_fault,config_fault,enabled};
   8'hb2:rdata=pending_us;
   8'hb3:rdata=active_us;
   8'hb4:rdata=min_us;
   8'hb5:rdata=max_us;
   8'hb6:rdata=WATCHDOG_MS;
   8'hb7:rdata=frames;
   default:begin end
  endcase
 end
endmodule
