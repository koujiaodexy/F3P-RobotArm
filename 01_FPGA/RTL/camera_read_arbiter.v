`timescale 1ns/1ps
// Registered grants remain owned through the complete FDMA read transaction.
module camera_read_arbiter(
 input wire clk,rst_n,input wire[31:0]a_addr,b_addr,input wire[15:0]a_size,b_size,
 input wire a_req,b_req,a_ready,b_ready,output wire a_busy,b_busy,a_valid,b_valid,
 output reg[31:0]m_addr,output reg[15:0]m_size,output wire m_req,m_ready,
 input wire m_busy,m_valid,output reg error
);
 reg[1:0] state;reg owner,last_owner;reg[15:0]beats;
 wire pick_b=b_req&&(!a_req||!last_owner);
 assign a_busy=state!=0&&!owner;assign b_busy=state!=0&&owner;
 assign a_valid=state!=0&&!owner&&m_valid;assign b_valid=state!=0&&owner&&m_valid;
 assign m_req=state==1;assign m_ready=state!=0&&(owner?b_ready:a_ready);
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=0;owner<=0;last_owner<=1;m_addr<=0;m_size<=0;beats<=0;error<=0;end
  else begin
   if(m_valid)begin beats<=beats+1;if(state==0)error<=1;end
   case(state)
    0:if(!m_busy&&(a_req||b_req))begin
     owner<=pick_b;last_owner<=pick_b;m_addr<=pick_b?b_addr:a_addr;m_size<=pick_b?b_size:a_size;beats<=0;state<=1;
    end
    1:if(m_busy)state<=2;
    2:if(!m_busy)begin if(beats!=m_size)error<=1;state<=0;end
   endcase
  end
 end
endmodule
