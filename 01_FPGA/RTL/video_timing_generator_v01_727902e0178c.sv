

// 使用axi lite接口配置显示时序参数，生成hs、vs等信号，一般用于对接vdma和axi stream to video out实现显示器显示
// 20250810 初始版本
// 20250910 增加axi lite接口，实现动态配置视频时序参数和像素时钟
// 20250919 支持通过参数设置视频时序、帧率，以支持非动态调整的模式
// 20250919 新增vtg_ce信号，以和axis to video out ip 配合使用
// 20250919 更改ip名称为video 提名 generator，暂不支持vtc的视频时序检测功能

/* 寄存器分布
index addr    purpose
0     0x00    h_front      (reg0[15:0])
1     0x04    h_action     (reg1[15:0])
2     0x08    h_sync       (reg2[15:0])
3     0x0c    h_back       (reg3[15:0])
4     0x10    v_front      (reg4[15:0])
5     0x14    v_action     (reg5[15:0])
6     0x18    v_sync       (reg6[15:0])
7     0x1c    v_back       (reg7[15:0])
8     0x20    [0] : rstn   (reg8[15:0])

...

16    0x1000  pll drp [7:0] write data, [15:8] write addr
17    0x1004  pll drp [7:0] read  data, [15:8] read addr
18    0x1008  pll lock  [0] pll lock status
*/


`timescale 1 ns / 1 ps
module video_timing_generator_v01_727902e0178c #(
    // 时钟参数
    parameter REF_CLK_FREQ = 50,      // ref clock时钟频率,用于计算pll的分频系数, 仅支持50和100两个频率，且输入必须为整数
    parameter integer FPS  = 60,      // 帧率(Frames Per Second)
    // 默认时序参数 - 1920x1080@60Hz
    parameter H_FRONT  = 16'd88,     // 水平前肩
    parameter H_ACTIVE = 16'd1920,   // 水平有效区
    parameter H_SYNC   = 16'd44,     // 水平同步
    parameter H_BACK   = 16'd148,    // 水平后肩
    parameter V_FRONT  = 16'd4,      // 垂直前肩
    parameter V_ACTIVE = 16'd1080,   // 垂直有效区
    parameter V_SYNC   = 16'd5,      // 垂直同步
    parameter V_BACK   = 16'd36      // 垂直后肩
   
)(
    input  wire                 aclk,            // 时钟信号
    input  wire                 arst_n,          // 异步复位，低有效

    // AXI Lite 接口信号
    input  wire [12:0]           s_axi_awaddr  ,  // 写地址
    input  wire                  s_axi_awvalid ,  // 写地址有效
    output wire                  s_axi_awready ,  // 写地址准备好  
    input  wire [31:0]           s_axi_wdata   ,  // 写数据
    input  wire [3:0]            s_axi_wstrb   ,  // 写字节使能
    input  wire                  s_axi_wvalid  ,  // 写数据有效
    output wire                  s_axi_wready  ,  // 写数据准备好 
    output wire [1:0]            s_axi_bresp   ,  // 写响应
    output wire                  s_axi_bvalid  ,  // 写响应有效
    input  wire                  s_axi_bready  ,  // 写响应准备好 
    input  wire [12:0]           s_axi_araddr  ,  // 读地址
    input  wire                  s_axi_arvalid ,  // 读地址有效
    output wire                  s_axi_arready ,  // 读地址准备好 
    output wire [31:0]           s_axi_rdata   ,  // 读数据
    output wire [1:0]            s_axi_rresp   ,  // 读响应
    output wire                  s_axi_rvalid  ,  // 读数据有效
    input  wire                  s_axi_rready  ,  // 读数据准备好 
    // 这里添加用户端口
    // ....
    input  wire                  ref_clk       ,  // 输入到PLL的参考时钟，需要与驱动中保持一致 
    input  wire                  vtg_ce        ,
     // 时序信号输出接口
    output wire                      vtg_pclk_locked,      // 像素时钟锁定状态
    output wire                      vtg_pclk,
    output wire                      vtg_hsync,            // 水平同步信号
    output wire                      vtg_vsync,            // 垂直同步信号
    output wire                      vtg_hblank,           // 水平消隐信号
    output wire                      vtg_vblank,           // 垂直消隐信号
    output wire                      vtg_active_video      // 数据使能信号
    
    // 用户端口添加结束
);
 
    
localparam REG_NUM    = 32;                   // 寄存器数量
localparam DATA_WIDTH = 32;                   // 数据宽度
localparam ADDR_WIDTH = 13;                   // 地址宽度

//==============================================================================
// PLL配置参数自动计算
//==============================================================================

localparam real REF_CLK_REAL = REF_CLK_FREQ;
localparam FIN = (REF_CLK_FREQ == 50)? "50":(REF_CLK_FREQ == 100)? "100":"50" ;

// 根据时序参数和FPS计算像素时钟 (MHz)
// Pixel Clock = (H_TOTAL * V_TOTAL * FPS) / 1_000_000
localparam integer H_TOTAL = H_FRONT + H_ACTIVE + H_SYNC + H_BACK;
localparam integer V_TOTAL = V_FRONT + V_ACTIVE + V_SYNC + V_BACK;
localparam integer TOTAL_PIXELS_PER_FRAME = H_TOTAL * V_TOTAL; // 可能较大, 对1080p约 2200*1125=2,475,000
localparam real PIXEL_CLK_REAL = (TOTAL_PIXELS_PER_FRAME * 1.0 * FPS) / 1_000_000.0; // MHz

// PLL VCO频率范围约束 (MHz)
localparam real VCO_MIN = 800.0;
localparam real VCO_MAX = 2000.0;

// 计算最优PLL参数的函数
`pragma protect begin_protected
`pragma protect version = 1
`pragma protect encrypt_agent = "Anlogic"
`pragma protect encrypt_agent_info = "Anlogic Encryption Tool anlogic_2019"
`pragma protect key_keyowner = "Cadence Design Systems.", key_keyname = "CDS_RSA_KEY_VER_1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 256)
`pragma protect key_block
iGDe174QOvlGg6aywFQXo7uWAhN4/9k0obvYWOWGusqCpX9dMpkOLvV7wn9pURJJ
SVc/k6ZrdDNN54sV3nhuoebBnew1pJT7xrjeSzcFzxk5klM/XPFpyB0LuSobaLEt
AH29AJGazQi9huI94TG7Uid9Arrcpb8c8zYWSAU51rNwORcwx6yzeWBNnYzBaEIW
3Pdv72fMiZwPyCaHLc6l4VLbXh7eqhvCUUDZ6vVDVPZdRmqR04y3M3R8e1LIzaqU
WT1w8/ICWtGI1T1T5KAUprM9gvKBqTlxa/shvKs5Iou0UTuWvWaWHONuz5HY/E/i
WjSC4J10hdZZX/ROXMGQ9g==
`pragma protect key_keyowner = "Mentor Graphics Corporation", key_keyname = "MGC-VERIF-SIM-RSA-1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
l0h7NRg/On5Dx1GbkkoiNzM4bC+6eT9ViAio4lpYNxma0uN6wih4hhZ6FxApwRvD
/2z+8eIPycdOWy0UQi8jO7G1vIsxHrh/drjoKGuNW/afFzmuH6+W8erpvHj6o1vc
P6gVW6u0emiyfnga4TCrq4yZyriMaa8UdwM5pNVqnog=
`pragma protect key_keyowner = "Mentor Graphics Corporation", key_keyname = "MGC-VERIF-SIM-RSA-2"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 256)
`pragma protect key_block
pz7npZw50nuSMdaeJCryzai6+SiicxpMF1Qh+kW4+9sOm2ud1QLskWgZuzOP3Zld
eDRuqoVvyHOrKEnNLe/UOn47reHUx9Yko7viXaJ3jVCCclgNCvPfR1XXCt9SX9pW
TCYnseV/NK2Hc9FTVJXaGNS1uzzpZu38P0xSq4q91NJ610RD/y544HU7C6MVDl2G
ZCMhdFsoCkzX9kbgj+iDM/UVbXpbDQNmBsYjF7MPr4c2LFDBfE4jIGcS+jPPOnbY
O/cTt3YySriwPCkHTrl/pbxcveVfetL15rgrUhbGnmCaiRIoykVRdxAr/DtrmB37
JaEHfnO18/zyeqy0WB9XVw==
`pragma protect key_keyowner = "Synopsys", key_keyname = "SNPS-VCS-RSA-1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
1uCh/WCyGsSf/cIm05faD9XOK4wtO53xOv7TPpCsbJehpJAk+BM2vlto80OkCl+g
30rCL4ZAUisOCxASlNIX1GApgHFDx2eA47XkjmaX6gxjAIw1OFxTfX1MLmEhqZ8a
plbMWGsLxzRQWtzXt6aj0cAlDiHsN0t+w4H/qDZnpCA=
`pragma protect key_keyowner = "Synopsys", key_keyname = "SNPS-VCS-RSA-2"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
mVQwPFmqTyJ2Oii57G06nfEQmH03W2WbdlFr608tBLW3BrwGiZwaHyWMGX6kaUae
Kcc9fIH4x+HLZoFxEf65kWfFxrod45JDOd86Y/vNIq3anZ4smHca5j+E7DtqOfzu
mufzbJLWYC+i8+moWMoXRW9Lx7YtLkO/ne/dy5PEG4M=
`pragma protect key_keyowner = "Anlogic", key_keyname = "anlogic-rsa-009"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
m9qcOt5lHUz/F+lrpf6AiPTCWKXE3qqNfJG/HFNRiZ0nckVPx97nc4RMEMTbPAlf
9JGllIgoMFJ7ZH7Ezb7aOPNJkSQm4Bk5XljwMlN4C3xCMI0ALM9VstD55LiHiPF+
RlscFeoorMmSjhfzHHXPzK4LuaUOKjgOInTrRS6PuTI=
`pragma protect data_method = "AES128-CBC"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 1840)
`pragma protect data_block
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
gmSYQXZBTp7sHj9ytxzMYA==
`pragma protect end_protected

// 计算PLL参数
localparam [20:0] PLL_PARAMS = calculate_pll_params(REF_CLK_REAL, PIXEL_CLK_REAL);
localparam  FBCLK_DIV  = int'(PLL_PARAMS[20:14]);    // m值 (3~126)
localparam  REFCLK_DIV = int'(PLL_PARAMS[13:7]);     // n值 (1~127)
localparam  CLKC0_DIV  = int'(PLL_PARAMS[6:0]);      // c值 (1~127)
localparam  CLKC0_DUTY_INT = (CLKC0_DIV > 1) ? ((CLKC0_DIV+1)/2) : 1; // 简单偶数/奇数占空比近似

// axi lite bus  start 
// 时钟和复位信号
wire clk   = aclk;
wire rst_n = arst_n;
// 写通道状态机
localparam [1:0] WRITE_IDLE = 2'b00,
                 WRITE_ADDR = 2'b01,
                 WRITE_DATA = 2'b10,
                 WRITE_RESP = 2'b11;

reg [1:0] write_state;

// 参数化的寄存器数组
reg [DATA_WIDTH-1:0] reg0;
reg [DATA_WIDTH-1:0] reg1;
reg [DATA_WIDTH-1:0] reg2;
reg [DATA_WIDTH-1:0] reg3;
reg [DATA_WIDTH-1:0] reg4;
reg [DATA_WIDTH-1:0] reg5;
reg [DATA_WIDTH-1:0] reg6;
reg [DATA_WIDTH-1:0] reg7;
reg [DATA_WIDTH-1:0] reg8;

reg [DATA_WIDTH-1:0] reg400;
reg [DATA_WIDTH-1:0] reg401;
reg [DATA_WIDTH-1:0] reg402;

// 写通道寄存器 , 确保数据缓存
reg [ADDR_WIDTH-1:0] write_addr;
reg [DATA_WIDTH-1:0] write_data;     // 缓存写数据
reg [3:0]            write_strb;     // 缓存写字节使能
reg                  bvalid;

// 读通道状态寄存器
reg [DATA_WIDTH-1:0] rdata;
reg rvalid;

// 声明变量
integer j;

// 输出信号连接
assign s_axi_awready = (write_state == WRITE_IDLE) || (write_state == WRITE_ADDR);
assign s_axi_wready  = (write_state == WRITE_IDLE) || (write_state == WRITE_DATA);

assign s_axi_bvalid  = bvalid;
assign s_axi_bresp   = 2'b00;

// 优化的读通道信号连接 
assign s_axi_arready = (!rvalid || s_axi_rready);
assign s_axi_rdata   = rdata;
assign s_axi_rvalid  = rvalid;
assign s_axi_rresp   = 2'b00;

`pragma protect begin_protected
`pragma protect version = 1
`pragma protect encrypt_agent = "Anlogic"
`pragma protect encrypt_agent_info = "Anlogic Encryption Tool anlogic_2019"
`pragma protect key_keyowner = "Cadence Design Systems.", key_keyname = "CDS_RSA_KEY_VER_1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 256)
`pragma protect key_block
iGDe174QOvlGg6aywFQXo7uWAhN4/9k0obvYWOWGusqCpX9dMpkOLvV7wn9pURJJ
SVc/k6ZrdDNN54sV3nhuoebBnew1pJT7xrjeSzcFzxk5klM/XPFpyB0LuSobaLEt
AH29AJGazQi9huI94TG7Uid9Arrcpb8c8zYWSAU51rNwORcwx6yzeWBNnYzBaEIW
3Pdv72fMiZwPyCaHLc6l4VLbXh7eqhvCUUDZ6vVDVPZdRmqR04y3M3R8e1LIzaqU
WT1w8/ICWtGI1T1T5KAUprM9gvKBqTlxa/shvKs5Iou0UTuWvWaWHONuz5HY/E/i
WjSC4J10hdZZX/ROXMGQ9g==
`pragma protect key_keyowner = "Mentor Graphics Corporation", key_keyname = "MGC-VERIF-SIM-RSA-1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
l0h7NRg/On5Dx1GbkkoiNzM4bC+6eT9ViAio4lpYNxma0uN6wih4hhZ6FxApwRvD
/2z+8eIPycdOWy0UQi8jO7G1vIsxHrh/drjoKGuNW/afFzmuH6+W8erpvHj6o1vc
P6gVW6u0emiyfnga4TCrq4yZyriMaa8UdwM5pNVqnog=
`pragma protect key_keyowner = "Mentor Graphics Corporation", key_keyname = "MGC-VERIF-SIM-RSA-2"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 256)
`pragma protect key_block
pz7npZw50nuSMdaeJCryzai6+SiicxpMF1Qh+kW4+9sOm2ud1QLskWgZuzOP3Zld
eDRuqoVvyHOrKEnNLe/UOn47reHUx9Yko7viXaJ3jVCCclgNCvPfR1XXCt9SX9pW
TCYnseV/NK2Hc9FTVJXaGNS1uzzpZu38P0xSq4q91NJ610RD/y544HU7C6MVDl2G
ZCMhdFsoCkzX9kbgj+iDM/UVbXpbDQNmBsYjF7MPr4c2LFDBfE4jIGcS+jPPOnbY
O/cTt3YySriwPCkHTrl/pbxcveVfetL15rgrUhbGnmCaiRIoykVRdxAr/DtrmB37
JaEHfnO18/zyeqy0WB9XVw==
`pragma protect key_keyowner = "Synopsys", key_keyname = "SNPS-VCS-RSA-1"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
1uCh/WCyGsSf/cIm05faD9XOK4wtO53xOv7TPpCsbJehpJAk+BM2vlto80OkCl+g
30rCL4ZAUisOCxASlNIX1GApgHFDx2eA47XkjmaX6gxjAIw1OFxTfX1MLmEhqZ8a
plbMWGsLxzRQWtzXt6aj0cAlDiHsN0t+w4H/qDZnpCA=
`pragma protect key_keyowner = "Synopsys", key_keyname = "SNPS-VCS-RSA-2"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
mVQwPFmqTyJ2Oii57G06nfEQmH03W2WbdlFr608tBLW3BrwGiZwaHyWMGX6kaUae
Kcc9fIH4x+HLZoFxEf65kWfFxrod45JDOd86Y/vNIq3anZ4smHca5j+E7DtqOfzu
mufzbJLWYC+i8+moWMoXRW9Lx7YtLkO/ne/dy5PEG4M=
`pragma protect key_keyowner = "Anlogic", key_keyname = "anlogic-rsa-009"
`pragma protect key_method = "rsa"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 128)
`pragma protect key_block
m9qcOt5lHUz/F+lrpf6AiPTCWKXE3qqNfJG/HFNRiZ0nckVPx97nc4RMEMTbPAlf
9JGllIgoMFJ7ZH7Ezb7aOPNJkSQm4Bk5XljwMlN4C3xCMI0ALM9VstD55LiHiPF+
RlscFeoorMmSjhfzHHXPzK4LuaUOKjgOInTrRS6PuTI=
`pragma protect data_method = "AES128-CBC"
`pragma protect encoding = (enctype = "BASE64", line_length = 64, bytes = 688)
`pragma protect data_block
cUizKmd7oPh2xiQZDVcoDe+eMNMtvgvtYtYJfswKoyG7ZDOgwYney/7Vrkb9HC84
jdye6ZEndsc4RtWmVKYTjyj3b39UtuvSeQ4IjkBPLsKnfprAqoq0g+upSBZDjiBH
ebLu/vblEAP7nMlHg2FDaFYJVLxaEkeRI2/9hiRzpzIvMew9GbkoeAjwyiC62Y3c
IyBjXrN4zpSQX/fyBG1+Q+9AKA6KB/uQayUk46FiSPnhfJ3tNmuCb5PUqJ3g3h9W
VZ9TGxAZVlS+9hWjDS4khaXTokwt1y+LNOLAjzyoZdJNJlcEkpRnQtHCqyk4uKgo
Em02cRzfsacS/dgIfq2B4cZrNxl55AI7ZlADJnNjXglGAuzFyqUNT1dPYvogH+U5
XpLfmjU0dt70Hmgd5PZTqUY7epqM2f+XR+TqykfKAHhMts3SxPAjp967olvSXcqQ
UpEgRF4St9IIT1Xnabe6EdTgb23cc4j4e2sRH1MrLGTnegKRcgChogCP2n+ND4mG
sJeIeg1F4jt1T9znqzxJPWZlTXboirCYiMqIV2Tshh8e6E1YI+QrQkI/gCcop/9U
7EzeipuKi40CjbGnpRVSeu9Ko1b03sZsEJv/KkQvjkqq2GidSjKclnS3aXgvO0no
mrWzh1cD7QJL1v+gKCdeJg20j4Dt2rq95oFCyQsHINmE8CG46KkDav2OWicRbCvX
Jp3yht2ZxvNjRaWAGk8LUybl+lLKG6teUiY9vRGeI0WodXyxyrxy23MAewY/Sad0
9UVDpsv4irfk9w4ZavnclhioHHmCkdz19rXtZB42K3tGKIQXB6+5RdFa1NOU7kTD
4/qmywKWjG7V7Ign5WAFQCs9NP3w4JoAMPE943B2ETmzeHwIVybUOepJzGSFNAre
Mhp7Rfvun0jspXoWTtFz9g==
`pragma protect end_protected

// 写通道状态机
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        write_state <= WRITE_IDLE;
        write_addr  <= {ADDR_WIDTH{1'b0}};
        write_data  <= {DATA_WIDTH{1'b0}};
        write_strb  <= 4'b0000;
        bvalid      <= 1'b0;
        // 初始化寄存器数组 - 使用默认时序参数
        reg0  <= {16'd0, H_FRONT};   // h_front
        reg1  <= {16'd0, H_ACTIVE};  // h_action  
        reg2  <= {16'd0, H_SYNC};    // h_sync
        reg3  <= {16'd0, H_BACK};    // h_back
        reg4  <= {16'd0, V_FRONT};   // v_front
        reg5  <= {16'd0, V_ACTIVE};  // v_action
        reg6  <= {16'd0, V_SYNC};    // v_sync
        reg7  <= {16'd0, V_BACK};    // v_back
        reg8  <= {32'd1};            // 默认使能视频时序输出
        
        reg400  <= {DATA_WIDTH{1'b0}};
        reg401  <= {DATA_WIDTH{1'b0}};
        reg402  <= {DATA_WIDTH{1'b0}};
        
        
    end else begin
        case (write_state)
            WRITE_IDLE: begin
                if (s_axi_awvalid && s_axi_wvalid) begin
                    // 地址和数据同时到达，直接执行写操作
                    execute_write_operation(s_axi_awaddr, s_axi_wdata, s_axi_wstrb);
                    write_state <= WRITE_RESP;
                    bvalid <= 1'b1;
                end else if (s_axi_awvalid) begin
                    // 只有地址到达，缓存地址
                    write_addr <= s_axi_awaddr;
                    write_state <= WRITE_DATA;
                end else if (s_axi_wvalid) begin
                    // 只有数据到达，缓存数据
                    write_data <= s_axi_wdata;
                    write_strb <= s_axi_wstrb;
                    write_state <= WRITE_ADDR;
                end
            end
            
            WRITE_ADDR: begin
                // 等待地址，数据已缓存
                if (s_axi_awvalid) begin
                    // 使用缓存的数据和当前地址执行写操作
                    execute_write_operation(s_axi_awaddr, write_data, write_strb);
                    write_state <= WRITE_RESP;
                    bvalid <= 1'b1;
                end
            end
            
            WRITE_DATA: begin
                // 等待数据，地址已缓存
                if (s_axi_wvalid) begin
                    // 使用缓存的地址和当前数据执行写操作
                    execute_write_operation(write_addr, s_axi_wdata, s_axi_wstrb);
                    write_state <= WRITE_RESP;
                    bvalid <= 1'b1;
                end
            end
            
            WRITE_RESP: begin
                // 等待响应被接收
                if (s_axi_bready) begin
                    bvalid <= 1'b0;
                    write_state <= WRITE_IDLE;
                end
                // 关键：在RESP状态下，bvalid必须保持为1直到被接收
            end
            
            default: begin
                write_state <= WRITE_IDLE;
                bvalid <= 1'b0;
            end
        endcase
    end
end

// 优化的读操作处理
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        rvalid <= 1'b0;
        rdata  <= {DATA_WIDTH{1'b0}};
    end else begin
        if (s_axi_arvalid && (!rvalid || s_axi_rready)) begin
            // 可以在以下情况接收新的读地址：
            // 1. rvalid为0（没有待处理的读数据）
            // 2. rvalid为1但master准备好接收数据
    
            case (s_axi_araddr[ADDR_WIDTH-1:2]) 
                11'h0  : rdata    <= reg0;
                11'h1  : rdata    <= reg1;
                11'h2  : rdata    <= reg2;
                11'h3  : rdata    <= reg3;
                11'h4  : rdata    <= reg4;
                11'h5  : rdata    <= reg5;
                11'h6  : rdata    <= reg6;
                11'h7  : rdata    <= reg7;
                11'h8  : rdata    <= reg8;
                
                11'h400: rdata    <= reg400;
                11'h401: rdata    <= {24'd0,drp_rdata};
                11'h402: rdata    <= {30'd0,drp_status[1], vtg_pclk_locked }; 
                default: rdata    <= {DATA_WIDTH{1'b0}};      
            endcase
        
            rvalid <= 1'b1;                   // 标记读数据有效
        end else if (rvalid && s_axi_rready) begin
            // 当前读数据被接收，但没有新的读请求
            rvalid <= 1'b0;
        end
    end
end

// axi lite bus end 

// 添加用户逻辑
// ...
// axi pll 数据处理,实现通过总线动态配置axi pll
wire    [7:0]     drp_addr;
wire    [7:0]     drp_wdata;
wire    [7:0]     drp_rdata;
wire              drp_w_enable;

// drp_rst_n must be 1
wire              drp_rst_n = 1'b1;
assign drp_w_enable = drp_w_t;
wire   [31:0]     drp_status;  

reg [15:0] drp_w_temp1;
reg [15:0] drp_w_temp2;
reg  drp_w_t;
always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
        drp_w_t <= 1'b0;
        drp_w_temp1  <= {16{1'b0}};
    
    end else begin
        drp_w_temp1 <= reg400[15:0];
        drp_w_temp2 <= drp_w_temp1;
        if ( reg400[15:0] != drp_w_temp2)
           drp_w_t <= 1;
         else 
           drp_w_t <= 0;  
    end
end

assign drp_addr     = drp_w_enable ? reg400[15:8]:reg401[15:8];
assign drp_wdata    = drp_w_enable ? reg400[7:0]: 8'd0;

dr1_phy_pll_vtc_727902e0178c
  #(
      .FBKCLK("VCO_PHASE0"),
      .FBKCLK_INT("VCO_PHASE0"),
      .REFCLK_DIV(REFCLK_DIV),          // 使用计算得到的n值
      .FBCLK_DIV(FBCLK_DIV),            // 使用计算得到的m值
      .CLKC0_FPHASE(0),
      .CLKC0_CPHASE(29),             
      .CLKC0_DIV(CLKC0_DIV),            // 使用计算得到的c值
      .CLKC0_DUTY_INT(CLKC0_DUTY_INT),  // 使用计算得到的占空比
      .CLKC0_ENABLE("ENABLE"),
      .FIN(FIN),                        // 使用参数化的输入频率
      .FEEDBK_MODE("NOCOMP"),
      .PLL_USR_RST("DISABLE"),
      .PLL_FEED_TYPE("INTERNAL"),
      .LPF_RES(2),
      .LPF_CAP(2),
      .ICP_CUR(12),
      .GMC_GAIN(2),
      .FRAC_ENABLE("DISABLE"),
      .DITHER_ENABLE("DISABLE"),
      .SDM_FRAC(0),
      .SSC_AMP(0.0000),
      .MPHASE_ENABLE("DISABLE"),
      .DYN_PHASE_PATH_SEL("DISABLE"),
      .DYN_FPHASE_EN("DISABLE"),
      .CLKC0_FPHASE_RSTSEL(0),
      .CLKC0_DUTY50("ENABLE"),
      .INTPI(0),
      .SSC_ENABLE("DISABLE"),
      .SSC_MODE("DOWN"),
      .SSC_FREQ_DIV(0),
      .SSC_RNGE(0),
      .HIGH_SPEED_EN("DISABLE")
  )dr1_pll_vtc_Inst
  (
      .clk1_en(1'b1),
      .clk1_out(),
      .clkb1_out(),
      .clk2_en(1'b0),
      .clk2_out(),
      .clkb2_out(),
      .clk3_en(1'b0),
      .clk3_out(),
      .clkb3_out(),
      .clk4_en(1'b0),
      .clk4_out(),
      .clkb4_out(),
      .clk5_en(1'b0),
      .clk5_out(),
      .clkb5_out(),
      .clk6_en(1'b0),
      .clk6_out(),
      .clkb6_out(),
      .refclk(ref_clk),
      .ssc_en(1'b0),
      .ext_freq_mod_val(17'b00000000000000000),
      .ext_freq_mod_en(1'b0),
      .ext_freq_mod_clk(1'b0),
	  .clkc_rst(2'b00),
      .fbclk(1'b0),
      .cps_step(2'b00),
      .psclksel(3'b000),
      .psdone(),
      .psstep(1'b0),
      .psdown(1'b0),
      .psclk(1'b0),
      .pllpd(1'b0),
      .lock(vtg_pclk_locked),
      .reset(1'b0),
      .wakeup(1'b0),
      .refclk_rst(1'b0),
      .clk0_en(1'b1),
      .clkb0_out(), 
      .clk0_out(pixel_clk), 
      .drp_clk(clk),
      .drp_rstn(drp_rst_n),
      .drp_sel(1'b1),
      .drp_rd(drp_r_enable),
      .drp_wr(drp_w_enable),
      .drp_addr(drp_addr),
      .drp_wdata(drp_wdata),
      .drp_err(),
      .drp_rdy(drp_status[0]),
      .drp_rdata(drp_rdata)
  );
  
    
    
assign vtg_pclk = pixel_clk;
wire  pixel_rst_n = rst_n & reg8[0];
    
 // 实例化修改后的VTG模块
vtg_v01_727902e0178c #(
    .COUNTER_WIDTH(12)
) vtg_v01_inst (
    .clk(pixel_clk),
    .rst_n(pixel_rst_n),
    .vtg_ce(vtg_ce),         // vtg使能信号
    
    // 时序参数配置
    .h_active(reg1[15:0]), 
    .h_front(reg0[15:0]), 
    .h_sync(reg2[15:0]), 
    .h_back(reg3[15:0]),
    .v_active(reg5[15:0]), 
    .v_front(reg4[15:0]),  
    .v_sync(reg6[15:0]),  
    .v_back(reg7[15:0]),
    
    // 修改后的时序输出信号
    .vtg_hsync(vtg_hsync), 
    .vtg_vsync(vtg_vsync),
    .vtg_hblank(vtg_hblank), 
    .vtg_vblank(vtg_vblank),
    .vtg_de(vtg_active_video),
    .vtg_h_count(), 
    .vtg_v_count(),
    .vtg_frame_start(), 
    .vtg_line_start()
);

 // 用户逻辑添加结束
endmodule



