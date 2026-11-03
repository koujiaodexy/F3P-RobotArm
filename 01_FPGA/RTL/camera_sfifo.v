
`timescale 1ns/1ps
module camera_sfifo #(parameter DATA_WIDTH_W = 8, 
        parameter DATA_WIDTH_R = 8, 
        parameter ADDR_WIDTH_W = 8, 
        parameter ADDR_WIDTH_R = 8, 
        parameter AL_FULL_NUM = 8, 
        parameter AL_EMPTY_NUM = 8, 
        parameter SHOW_AHEAD_EN = 1'b0, 
        parameter //SHOWAHEAD mode enable
        OUTREG_EN //OUTREG, NOREG
         = "NOREG") (
    //independent clock mode,fixed as asynchronous reset
    input rst,  //asynchronous port,active hight
    input clkw,  //write clock
    input clkr,  //read clock
    input we,  //write enable,active hight
    input [(DATA_WIDTH_W - 1):0] di,  //write data
    input re,  //read enable,active hight
    output [(DATA_WIDTH_R - 1):0] dout,  //read data
    output reg valid,  //read data valid flag
    output full_flag,  //fifo full flag
    output empty_flag,  //fifo empty flag
    output afull,  //fifo almost full flag
    output aempty,  //fifo almost empty flag
    output [(ADDR_WIDTH_W - 1):0] wrusedw,  //stored data number in fifo
    output [(ADDR_WIDTH_R - 1):0] rdusedw //available data number for read      
        )  /* fehdl keep_hierarchy="true" */ ;
    //--------------------------------------------------------------------------------------------
    //-------------internal parameter and signals definition below---------------
    //--------------------------------------------------------------------------------------------
    //-------------parameter definition 
    localparam FULL_NUM = {ADDR_WIDTH_W{1'b1}} ; 
    //-------------signals definition
    reg asy_w_rst0 ; 
    reg asy_w_rst1 ; 
    reg asy_r_rst0 ; 
    reg asy_r_rst1 ; 
    wire rd_rst ; 
    wire wr_rst ; 
    wire [(ADDR_WIDTH_R - 1):0] rd_to_wr_addr ; // read address synchronized to write clock domain
    wire [(ADDR_WIDTH_W - 1):0] wr_to_rd_addr ; // write address synchronized to read clock domain
    reg [(ADDR_WIDTH_W - 1):0] wr_addr ; // current write address
    reg [(ADDR_WIDTH_R - 1):0] rd_addr ; // current write address
    wire wr_en_s ; 
    wire rd_en_s ; 
    reg [(ADDR_WIDTH_W - 1):0] shift_rdaddr ; 
    reg [(ADDR_WIDTH_R - 1):0] shift_wraddr ; 
    wire [(ADDR_WIDTH_W - 1):0] wr_addr_diff ; // the difference between read and write address(synchronized to write clock domain)
    wire [(ADDR_WIDTH_R - 1):0] rd_addr_diff ; // the difference between read and write address(synchronized to read clock domain)
    reg empty_flag_r1 ; 
    reg empty_flag_r2 ; 
    reg re_r1 ; 
    reg re_r2 ; 
    //--------------------------------------------------------------------------------------------
    //--------------------fuctional codes below---------------------------------
    //--------------------------------------------------------------------------------------------
    // =============================================
    // reset control logic below;
    // =============================================
    //Asynchronous reset synchronous release on the write side
    always
        @(posedge clkw or 
            posedge rst)
        begin
            if (rst) 
                begin
                    asy_w_rst0 <=  1'b1 ;
                    asy_w_rst1 <=  1'b1 ;
                end
            else
                begin
                    asy_w_rst0 <=  1'b0 ;
                    asy_w_rst1 <=  asy_w_rst0 ;
                end
        end
    //Asynchronous reset synchronous release on the read side
    always
        @(posedge clkr or 
            posedge rst)
        begin
            if (rst) 
                begin
                    asy_r_rst0 <=  1'b1 ;
                    asy_r_rst1 <=  1'b1 ;
                end
            else
                begin
                    asy_r_rst0 <=  1'b0 ;
                    asy_r_rst1 <=  asy_r_rst0 ;
                end
        end
    assign rd_rst = asy_r_rst1 ; 
    assign wr_rst = asy_w_rst1 ; 
    // =============================================
    // address generate logic below;
    // =============================================
    // write and read ram enable
    assign wr_en_s = ((!full_flag) & we) ; 
    assign rd_en_s = ((!empty_flag) & re) ; 
    // generate write fifo address
    always
        @(posedge clkw or 
            posedge wr_rst)
        begin
            if ((wr_rst == 1'b1)) 
                wr_addr <=  'b0 ;
            else
                if (wr_en_s) 
                    wr_addr <=  (wr_addr + 1) ;
        end
    // generate rd fifo address
    always
        @(posedge clkr or 
            posedge rd_rst)
        begin
            if ((rd_rst == 1'b1)) 
                rd_addr <=  'b0 ;
            else
                if (rd_en_s) 
                    rd_addr <=  (rd_addr + 1) ;
        end
    always
        @(*)
        begin
            if ((ADDR_WIDTH_R >= ADDR_WIDTH_W)) 
                begin
                    shift_rdaddr = (rd_to_wr_addr >> (ADDR_WIDTH_R - ADDR_WIDTH_W)) ;
                    shift_wraddr = (wr_to_rd_addr << (ADDR_WIDTH_R - ADDR_WIDTH_W)) ;
                end
            else
                begin
                    shift_rdaddr = (rd_to_wr_addr << (ADDR_WIDTH_W - ADDR_WIDTH_R)) ;
                    shift_wraddr = (wr_to_rd_addr >> (ADDR_WIDTH_W - ADDR_WIDTH_R)) ;
                end
        end
    // two's complement format
    assign wr_addr_diff = (wr_addr - shift_rdaddr) ; // the count of data writen to fifo
    assign rd_addr_diff = (shift_wraddr - rd_addr) ; // the count of data available for read
    // =============================================
    // generate all output flag and count below;
    // ============================================= 
    // generate fifo full_flag indicator
    assign full_flag = ((wr_addr_diff >= FULL_NUM) ? 1'b1 : 1'b0) ; 
    // generate fifo afull indicator
    assign afull = ((wr_addr_diff >= AL_FULL_NUM) ? 1'b1 : 1'b0) ; 
    // generate fifo empty_flag indicator
    // Modular subtraction is zero exactly when these pointers are equal.
    // Compare directly so FIFO look-ahead never traverses a count subtractor.
    assign empty_flag = (shift_wraddr == rd_addr); 
    // generate fifo aempty indicator
    assign aempty = ((rd_addr_diff <= AL_EMPTY_NUM) ? 1'b1 : 1'b0) ; 
    // the count of data writen to fifo 
    assign wrusedw = wr_addr_diff ; 
    // the count of data available for read
    assign rdusedw = rd_addr_diff ; 
    // delay empty_flag for 2cycle
    always
        @(posedge clkr or 
            posedge rd_rst)
        begin
            if ((rd_rst == 1'b1)) 
                begin
                    empty_flag_r1 <=  1'b1 ;
                    empty_flag_r2 <=  1'b1 ;
                end
            else
                begin
                    empty_flag_r1 <=  empty_flag ;
                    empty_flag_r2 <=  empty_flag_r1 ;
                end
        end
    // delay rd_en_s for 2cycle
    always
        @(posedge clkr or 
            posedge rd_rst)
        begin
            if ((rd_rst == 1'b1)) 
                begin
                    re_r1 <=  1'b0 ;
                    re_r2 <=  1'b0 ;
                end
            else
                begin
                    re_r1 <=  rd_en_s ;
                    re_r2 <=  re_r1 ;
                end
        end
    // generate data output valid flag
    always
        @(*)
        begin
            if ((SHOW_AHEAD_EN && (OUTREG_EN == "NOREG"))) 
                valid = (!empty_flag) ;
            else
                if (((!SHOW_AHEAD_EN) && (OUTREG_EN == "OUTREG"))) 
                    valid = (re_r2 & (!empty_flag_r2)) ;
                else
                    valid = (re_r1 & (!empty_flag_r1)) ;
        end
    // =============================================
    // instance logic below;
    // =============================================
    // fifo read address synchronous to write clock domain using gray code
    fifo_cross_domain_addr_process_al_0322d65db018 #(.ADDR_WIDTH(ADDR_WIDTH_R)) rd_to_wr_cross_inst (.primary_asreset_i(rd_rst), 
                .secondary_asreset_i(wr_rst), 
                .primary_clk_i(clkr), 
                .secondary_clk_i(clkw), 
                .primary_addr_i(rd_addr), 
                .secondary_addr_o(rd_to_wr_addr)) ; 
    // fifo write address synchronous to read clock domain using gray code
    fifo_cross_domain_addr_process_al_0322d65db018 #(.ADDR_WIDTH(ADDR_WIDTH_W)) wr_to_rd_cross_inst (.primary_asreset_i(wr_rst), 
                .secondary_asreset_i(rd_rst), 
                .primary_clk_i(clkw), 
                .secondary_clk_i(clkr), 
                .primary_addr_i(wr_addr), 
                .secondary_addr_o(wr_to_rd_addr)) ; 
    ram_infer_0322d65db018 #(.DATAWIDTH_A(DATA_WIDTH_W),
            .ADDRWIDTH_A(ADDR_WIDTH_W),
            .DATAWIDTH_B(DATA_WIDTH_R),
            .ADDRWIDTH_B(ADDR_WIDTH_R),
            .MODE("SDP"),
            .REGMODE_B(OUTREG_EN)) ram_inst (.clka(clkw), 
                .rsta(wr_rst), 
                .cea(1'b1), 
                .wea(wr_en_s), 
                .ocea(1'b0), 
                .dia(di), 
                .addra(wr_addr), 
                .clkb(clkr), 
                .rstb(rd_rst), 
                .ceb((SHOW_AHEAD_EN | rd_en_s)), 
                .web(1'b0), 
                .oceb(1'b1), 
                .addrb((rd_addr + (SHOW_AHEAD_EN & rd_en_s))), 
                .dob(dout)) ; 
endmodule



`timescale 1ns/1ps
