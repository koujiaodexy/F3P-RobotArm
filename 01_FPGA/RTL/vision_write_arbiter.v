`timescale 1ns/1ps
// Registered, burst-atomic arbiter. Client busy begins at the accepted grant.
// A two-word elastic register isolates client RAM/data muxes from the PS input.
module vision_write_arbiter(
 input wire clk,rst_n,
 input wire[31:0]a_addr,b_addr,input wire[15:0]a_size,b_size,
 input wire a_req,b_req,input wire[63:0]a_data,b_data,input wire a_ready,b_ready,
 output wire a_busy,b_busy,a_pop,b_pop,
 output reg[31:0]m_addr,output reg[15:0]m_size,output wire m_req,
 output wire[63:0]m_data,output wire m_ready,input wire m_busy,m_pop,
 output reg error
);
 localparam IDLE=0,ISSUE=1,ACTIVE=2;
 reg[1:0]state,qcount;reg owner,last_owner,seen_busy;
 reg[15:0]fetched,consumed;reg[63:0]head,tail;
 wire pick_b=b_req&&(!a_req||!last_owner);
 wire source_ready=owner?b_ready:a_ready;
 wire push=state!=IDLE&&fetched<m_size&&source_ready&&qcount<2;
 wire[63:0]source_data=owner?b_data:a_data;
 assign a_busy=state!=IDLE&&!owner;assign b_busy=state!=IDLE&&owner;
 assign a_pop=push&&!owner;assign b_pop=push&&owner;
 assign m_req=state==ISSUE;assign m_data=head;assign m_ready=qcount!=0;
 always @(posedge clk or negedge rst_n)begin
  if(!rst_n)begin state<=IDLE;owner<=0;last_owner<=1;seen_busy<=0;m_addr<=0;m_size<=0;fetched<=0;consumed<=0;head<=0;tail<=0;qcount<=0;error<=0;end
  else begin
   if(m_pop&&(qcount==0||state==IDLE))error<=1;
   case({push,m_pop})
    2'b10:begin if(qcount==0)head<=source_data;else tail<=source_data;qcount<=qcount+1;end
    2'b01:begin head<=tail;qcount<=qcount-1;end
    2'b11:begin if(qcount==1)head<=source_data;else begin head<=tail;tail<=source_data;end end
   endcase
   if(push)fetched<=fetched+1;
   if(m_pop)consumed<=consumed+1;
   case(state)
    IDLE:if(!m_busy&&(a_req||b_req))begin
     owner<=pick_b;last_owner<=pick_b;m_addr<=pick_b?b_addr:a_addr;m_size<=pick_b?b_size:a_size;
     fetched<=0;consumed<=0;qcount<=0;seen_busy<=0;state<=ISSUE;
    end
    ISSUE:if(m_busy)begin state<=ACTIVE;seen_busy<=1;end
    ACTIVE:if(seen_busy&&!m_busy)begin
     if(consumed!=m_size||fetched!=m_size||qcount!=0)error<=1;
     state<=IDLE;
    end
   endcase
  end
 end
endmodule
