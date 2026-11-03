`timescale 1ns/1ps
// Independent motor I/O island. No writes outside word addresses 0x90..0xaf.
module car_io #(parameter integer CLK_HZ=133333333,
                parameter integer WATCHDOG_MS=100)(
 input wire clk,rst_n,wr,input wire[7:0]addr,input wire[31:0]wdata,
 output reg[31:0]rdata,input wire[3:0]encoder,keys_n,
 output wire pwma,pwmb,ain1,ain2,bin1,bin2);
 localparam integer SAMPLE_CYCLES=CLK_HZ/100;
 localparam integer PWM_CYCLES=CLK_HZ/10000;
 localparam integer WD_CYCLES=(CLK_HZ/1000)*WATCHDOG_MS;
 localparam[31:0] COMMIT=32'h43415201;
 (* ASYNC_REG="TRUE" *) reg[3:0] enc_meta,enc_sync,key_meta,key_sync;
 reg[1:0] prev_l,prev_r;reg[3:0] settle;
 reg[31:0] count_l,count_r,snap_l,snap_r,sample_seq;
 reg[3:0] snap_keys;reg[31:0] sample_counter,pwm_counter,watchdog;
 reg signed[31:0] pending_l,pending_r,active_l,active_r;
 reg armed,wd_fault,config_fault;reg[31:0] commits,invalid_l,invalid_r;
 function signed[2:0] quadrature;
  input[1:0] previous,current;
  begin
   case({previous,current})
    4'h1,4'h7,4'h8,4'he:quadrature=-1;
    4'h2,4'h4,4'hb,4'hd:quadrature=1;
    default:quadrature=0;
   endcase
  end
 endfunction
 wire signed[2:0] dl=quadrature(prev_l,enc_sync[3:2]);
 wire signed[2:0] dr=quadrature(prev_r,enc_sync[1:0]);
 wire commit_valid=wr&&addr==8'h9c&&wdata==COMMIT&&!wd_fault&&!config_fault&&
                   pending_l<=800&&pending_l>=-800&&pending_r<=800&&pending_r>=-800;
 wire enabled=armed&&!wd_fault&&!config_fault;
 wire[31:0] abs_l=active_l[31]?-active_l:active_l;
 wire[31:0] abs_r=active_r[31]?-active_r:active_r;
 // Constant divisor; duty scale and +/-800 limit match the source project.
 wire[63:0] high_l=(64'd1*PWM_CYCLES*abs_l)/1000;
 wire[63:0] high_r=(64'd1*PWM_CYCLES*abs_r)/1000;
 assign pwma=enabled&&(pwm_counter<high_l);
 assign pwmb=enabled&&(pwm_counter<high_r);
 assign ain1=enabled&&(active_l<0);
 assign ain2=enabled&&(active_l>0);
 assign bin1=enabled&&(active_r<0);
 assign bin2=enabled&&(active_r>0);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin enc_meta<=0;enc_sync<=0;key_meta<=15;key_sync<=15;end
  else begin enc_meta<=encoder;enc_sync<=enc_meta;key_meta<=keys_n;key_sync<=key_meta;end
 end
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin
   prev_l<=0;prev_r<=0;settle<=0;count_l<=0;count_r<=0;
   snap_l<=0;snap_r<=0;snap_keys<=0;sample_seq<=0;sample_counter<=0;
   pwm_counter<=0;watchdog<=0;armed<=0;wd_fault<=0;config_fault<=0;
   pending_l<=0;pending_r<=0;active_l<=0;active_r<=0;commits<=0;
   invalid_l<=0;invalid_r<=0;
  end else begin
   if(pwm_counter==PWM_CYCLES-1)pwm_counter<=0;else pwm_counter<=pwm_counter+1;
   prev_l<=enc_sync[3:2];prev_r<=enc_sync[1:0];
   if(settle<4)settle<=settle+1;
   else begin
    count_l<=count_l+{{29{dl[2]}},dl};
    count_r<=count_r+{{29{dr[2]}},dr};
    if((prev_l^enc_sync[3:2])==2'b11)invalid_l<=invalid_l+1;
    if((prev_r^enc_sync[1:0])==2'b11)invalid_r<=invalid_r+1;
   end
   if(sample_counter==SAMPLE_CYCLES-1)begin
    sample_counter<=0;sample_seq<=sample_seq+1;
    // Include transitions occurring exactly on the sample edge.
    snap_l<=count_l+((settle>=4)?{{29{dl[2]}},dl}:32'd0);
    snap_r<=count_r+((settle>=4)?{{29{dr[2]}},dr}:32'd0);
    snap_keys<=~key_sync;
   end else sample_counter<=sample_counter+1;
   // A valid command on the expiry edge renews the watchdog atomically.
   if(armed&&!commit_valid)begin
    if(watchdog>=WD_CYCLES-1)begin armed<=0;wd_fault<=1;active_l<=0;active_r<=0;end
    else watchdog<=watchdog+1;
   end
   if(wr)case(addr)
    8'h9a:pending_l<=wdata;
    8'h9b:pending_r<=wdata;
    8'h9c:begin
     if(wdata==0)begin armed<=0;active_l<=0;active_r<=0;watchdog<=0;end
     else if(wdata==COMMIT&&!wd_fault&&!config_fault)begin
      if(pending_l>800||pending_l< -800||pending_r>800||pending_r< -800)
       begin armed<=0;active_l<=0;active_r<=0;config_fault<=1;end
      else begin active_l<=pending_l;active_r<=pending_r;armed<=1;watchdog<=0;commits<=commits+1;end
     end
    end
    8'h9d:if(wdata==32'h434c5200&&!armed)begin wd_fault<=0;config_fault<=0;end
    default:begin end
   endcase
  end
 end
 always @* begin
  rdata=0;
  case(addr)
   8'h90:rdata=32'h4d4f5431;
   8'h91:rdata=32'h00010000;
   8'h92:rdata=CLK_HZ;
   8'h93:rdata=SAMPLE_CYCLES;
   8'h94:rdata=PWM_CYCLES;
   8'h95:rdata=sample_seq;
   8'h96:rdata=snap_l;
   8'h97:rdata=snap_r;
   8'h98:rdata={28'd0,snap_keys};
   8'h99:rdata={29'd0,config_fault,wd_fault,armed};
   8'h9a:rdata=pending_l;
   8'h9b:rdata=pending_r;
   8'h9c:rdata=active_l;
   8'h9d:rdata=active_r;
   8'h9e:rdata=commits;
   8'h9f:rdata=invalid_l;
   8'ha0:rdata=invalid_r;
   8'ha1:rdata=WD_CYCLES;
   8'hb8:rdata=32'd800; // Additive read-only PWM limit capability.
   default:rdata=0;
  endcase
 end
endmodule
