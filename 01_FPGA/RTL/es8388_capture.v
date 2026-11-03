`timescale 1ns/1ps
// ES8388 input only. Independent clocks/FIFO; no connection to the CAN owner.
// 50MHz / 4 MCLK, MCLK / 768 LRCK = 50,000,000 / 3072 Hz.
module es8388_capture #(
    parameter AW=15, parameter I2C_TICK=125, parameter CONFIG_WAIT=250000
)(
    input wire clk_i,rst_ni,bus_clk_i,enable_i,reinit_i,
    input wire [3:0] gain_i, input wire [31:0] pop_i,
    output wire [31:0] status_o,head_o,total_o,overflows_o,
    output reg [31:0] ack_o,
    output wire mclk_o, output reg bclk_o,lrck_o,
    output wire dac_o, input wire adc_i,
    output reg scl_o, inout wire sda_io
);
    reg [1:0] mdiv;
    assign mclk_o=mdiv[1];
    assign dac_o=1'b0;
    reg ena1,ena2,re1,re2,re_seen;
    reg [3:0] gain1,gain2;
    reg ad1,ad2;
    always @(posedge clk_i or negedge rst_ni) begin
      if(!rst_ni)begin mdiv<=0;ena1<=0;ena2<=0;re1<=0;re2<=0;gain1<=6;gain2<=6;ad1<=0;ad2<=0;end
      else begin mdiv<=mdiv+1'b1;ena1<=enable_i;ena2<=ena1;re1<=reinit_i;re2<=re1;
        gain1<=gain_i;gain2<=gain1;ad1<=adc_i;ad2<=ad1;end
    end

    // Open-drain SDA and ACK checking for every address/register/data byte.
    reg sda_release;
    assign sda_io=sda_release?1'bz:1'b0;
    reg configured,nack;
    reg [3:0] state;
    reg [31:0] wait_count;
    reg [15:0] tick_count;
    reg [4:0] lut_index;
    reg [1:0] byte_index;
    reg [3:0] bit_index;
    reg [7:0] byte_value;
    reg [3:0] gain_latched;
    localparam WAIT=0,START_A=1,START_B=2,LOW=3,RISE=4,HIGH=5,FALL=6,
               STOP_LOW=7,STOP_HIGH=8,STOP_RELEASE=9,DONE=10;
    function [15:0] config_word;
      input [4:0] n; input [3:0] gain;
      begin case(n)
        0:config_word=16'h0080;1:config_word=16'h0000;
        2:config_word=16'h0158;3:config_word=16'h0150;
        4:config_word=16'h02f3;5:config_word=16'h0200;
        6:config_word=16'h0309;7:config_word=16'h0006;
        8:config_word=16'h04c0;9:config_word=16'h0800;
        10:config_word={8'h09,gain,gain};11:config_word=16'h0a50;
        12:config_word=16'h0c4c;13:config_word=16'h0d06;
        14:config_word=16'h0e30;15:config_word=16'h0f20;
        16:config_word=16'h1000;17:config_word=16'h1100;
        18:config_word=16'h1200;19:config_word=16'h1904;
        20:config_word=16'h2b80;default:config_word=16'h0000;
      endcase end
    endfunction
    wire [15:0] lut_word=config_word(lut_index,gain_latched);
    always @(posedge clk_i or negedge rst_ni) begin
      if(!rst_ni)begin
        configured<=0;nack<=0;state<=WAIT;wait_count<=0;tick_count<=0;
        lut_index<=0;byte_index<=0;bit_index<=0;byte_value<=8'h22;
        scl_o<=1;sda_release<=1;re_seen<=0;gain_latched<=6;
      end else begin
        re_seen<=re2;
        if(re2&&!re_seen)begin
          configured<=0;nack<=0;state<=WAIT;wait_count<=0;tick_count<=0;
          lut_index<=0;byte_index<=0;bit_index<=0;byte_value<=8'h22;
          scl_o<=1;sda_release<=1;gain_latched<=gain2;
        end else if(state==WAIT)begin
          if(wait_count==CONFIG_WAIT-1)begin wait_count<=0;state<=START_A;tick_count<=0;
            byte_index<=0;bit_index<=0;byte_value<=8'h22;end
          else wait_count<=wait_count+1'b1;
        end else if(state!=DONE)begin
          if(tick_count==I2C_TICK-1)begin
            tick_count<=0;
            case(state)
              START_A:begin scl_o<=1;sda_release<=1;state<=START_B;end
              START_B:begin scl_o<=1;sda_release<=0;state<=LOW;end
              LOW:begin scl_o<=0;sda_release<=(bit_index==8)?1'b1:byte_value[7-bit_index];state<=RISE;end
              RISE:begin scl_o<=1;state<=HIGH;end
              HIGH:begin if(bit_index==8&&sda_io!==1'b0)nack<=1;state<=FALL;end
              FALL:begin
                scl_o<=0;
                if(bit_index==8)begin
                  bit_index<=0;
                  if(byte_index==2)state<=STOP_LOW;
                  else begin byte_index<=byte_index+1'b1;
                    byte_value<=(byte_index==0)?lut_word[15:8]:lut_word[7:0];state<=LOW;end
                end else begin bit_index<=bit_index+1'b1;state<=LOW;end
              end
              STOP_LOW:begin scl_o<=0;sda_release<=0;state<=STOP_HIGH;end
              STOP_HIGH:begin scl_o<=1;state<=STOP_RELEASE;end
              STOP_RELEASE:begin
                sda_release<=1;
                if(nack)state<=DONE;
                else if(lut_index==20)begin configured<=1;state<=DONE;end
                else begin lut_index<=lut_index+1'b1;wait_count<=0;state<=WAIT;end
              end
              default:state<=DONE;
            endcase
          end else tick_count<=tick_count+1'b1;
        end
      end
    end

    reg [4:0] bit_div;
    reg [5:0] frame_bit;
    reg [15:0] shift;
    reg frame_started;
    reg [15:0] memory [0:(1<<AW)-1];
    reg [AW:0] wp,wgray,rp,rgray;
    reg [AW:0] rgray1,rgray2,wgray1,wgray2;
    reg [31:0] total,overflows;
    reg overflow;
    wire full=(wgray=={~rgray2[AW:AW-1],rgray2[AW-2:0]});
    wire [AW:0] wp_next=wp+1'b1;
    wire [AW:0] wgray_next=(wp_next>>1)^wp_next;
    always @(posedge clk_i or negedge rst_ni) begin
      if(!rst_ni)begin
        bit_div<=0;frame_bit<=63;bclk_o<=1;lrck_o<=1;shift<=0;frame_started<=0;
        wp<=0;wgray<=0;rgray1<=0;rgray2<=0;total<=0;overflows<=0;overflow<=0;
      end else begin
        rgray1<=rgray;rgray2<=rgray1;
        if(bit_div==23)begin
          bit_div<=0;bclk_o<=~bclk_o;
          if(bclk_o)begin
            frame_bit<=frame_bit+1'b1;lrck_o<=((frame_bit+6'd1)>=6'd32);
            if(frame_bit==63)frame_started<=ena2&&configured;
          end else if(frame_bit>=1&&frame_bit<=16)begin
            shift<={shift[14:0],ad2};
            if(frame_bit==16&&frame_started&&ena2&&configured)begin
              total<=total+1'b1;
              if(!full)begin memory[wp[AW-1:0]]<={shift[14:0],ad2};wp<=wp_next;wgray<=wgray_next;end
              else begin overflow<=1;overflows<=overflows+1'b1;end
            end
          end
        end else bit_div<=bit_div+1'b1;
        if(!ena2)begin wp<=0;wgray<=0;total<=0;overflows<=0;overflow<=0;frame_started<=0;end
      end
    end
    function [AW:0] gray_binary;
      input [AW:0] value;integer k;
      begin gray_binary[AW]=value[AW];for(k=AW-1;k>=0;k=k-1)gray_binary[k]=gray_binary[k+1]^value[k];end
    endfunction
    function [31:0] gray_binary32;
      input [31:0] value;integer k;
      begin gray_binary32[31]=value[31];for(k=30;k>=0;k=k-1)gray_binary32[k]=gray_binary32[k+1]^value[k];end
    endfunction
    wire [AW:0] count=gray_binary(wgray2)-rp;
    wire pop=enable_i&&(pop_i!=ack_o)&&(count!=0);
    wire [AW:0] rp_next=rp+1'b1;
    reg [15:0] head;
    reg cfg1,cfg2,nack1,nack2,ov1,ov2,enabled1,enabled2;
    reg [31:0] total1,total2,over1,over2;
    wire [31:0] total_gray=(total>>1)^total;
    wire [31:0] over_gray=(overflows>>1)^overflows;
    always @(posedge bus_clk_i or negedge rst_ni)begin
      if(!rst_ni)begin
        rp<=0;rgray<=0;wgray1<=0;wgray2<=0;ack_o<=0;head<=0;
        cfg1<=0;cfg2<=0;nack1<=0;nack2<=0;ov1<=0;ov2<=0;enabled1<=0;enabled2<=0;
        total1<=0;total2<=0;over1<=0;over2<=0;
      end else begin
        wgray1<=wgray;wgray2<=wgray1;
        cfg1<=configured;cfg2<=cfg1;nack1<=nack;nack2<=nack1;
        ov1<=overflow;ov2<=ov1;enabled1<=ena2;enabled2<=enabled1;
        total1<=total_gray;total2<=total1;over1<=over_gray;over2<=over1;
        if(!enable_i)begin rp<=0;rgray<=0;ack_o<=0;end
        else if(pop_i!=ack_o)begin ack_o<=pop_i;
          if(count!=0)begin rp<=rp_next;rgray<=(rp_next>>1)^rp_next;end
        end
        head<=memory[pop?rp_next[AW-1:0]:rp[AW-1:0]];
      end
    end
    assign status_o={12'd0,enabled2,ov2,nack2,cfg2,{(16-(AW+1)){1'b0}},count};
    assign head_o={16'd0,head};
    assign total_o=gray_binary32(total2);
    assign overflows_o=gray_binary32(over2);
endmodule
