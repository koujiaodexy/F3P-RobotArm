`timescale 1ns/1ps

// Runtime command engine for the ZDT X42S vendor CAN protocol.
//
// Commands are accepted only from an explicit cmd_pulse_i.  The engine never
// enables or moves the motor by itself.  While moving, a missing heartbeat for
// WATCHDOG_TICKS requests the vendor immediate-stop command (FE).  This is a
// functional stop and does not replace a hard-wired emergency stop.
module zdt_x42s_runtime #(
    parameter integer CLK_HZ = 50_000_000,
    parameter [7:0] NODE_ID = 8'd1,
    parameter [31:0] RESPONSE_TIMEOUT_TICKS = CLK_HZ / 2,
    parameter [31:0] ENABLE_GAP_TICKS = CLK_HZ / 2,
    parameter [31:0] DISABLE_GAP_TICKS = CLK_HZ / 20,
    parameter [31:0] WATCHDOG_TICKS = CLK_HZ / 4
) (
    input  wire        clk_i,
    input  wire        rst_ni,

    input  wire        cmd_pulse_i,
    input  wire [3:0]  cmd_opcode_i,
    input  wire [7:0]  node_i,
    input  wire [15:0] speed_rpm_i,
    input  wire [7:0]  acceleration_i,
    input  wire        direction_ccw_i,
    input  wire [31:0] target_pulses_i,
    input  wire        heartbeat_pulse_i,

    output wire        busy_o,
    output wire        enabled_o,
    output wire [7:0]  active_node_o,
    output wire        reply_valid_o,
    output wire        moving_o,
    output reg         error_o,
    output reg         watchdog_stop_o,
    output reg  [31:0] error_code_o,
    output wire [3:0]  state_o,

    output reg         tx_valid_o,
    input  wire        tx_ready_i,
    input  wire        tx_error_i,
    input  wire        tx_done_i,
    output wire        tx_extended_o,
    output wire [28:0] tx_id_o,
    output reg  [3:0]  tx_dlc_o,
    output reg  [63:0] tx_data_o,

    input  wire        rx_valid_i,
    input  wire        rx_extended_i,
    input  wire [28:0] rx_id_i,
    input  wire [3:0]  rx_dlc_i,
    input  wire [63:0] rx_data_i
);
    localparam [3:0] CMD_ENABLE = 4'd1;
    localparam [3:0] CMD_DISABLE = 4'd2;
    localparam [3:0] CMD_RUN = 4'd3;
    localparam [3:0] CMD_STOP = 4'd4;
    localparam [3:0] CMD_CLEAR_ERROR = 4'd5;
    localparam [3:0] CMD_QUERY = 4'd6;
    localparam [3:0] CMD_ZERO = 4'd7;
    localparam [3:0] CMD_POSITION = 4'd8;
    localparam [3:0] CMD_HOME_STATUS = 4'd9;
    localparam [3:0] CMD_HOME = 4'd10;
    localparam [3:0] CMD_MOTOR_STATUS = 4'd11;
    localparam [3:0] CMD_MARK_SESSION = 4'd12;
    localparam [3:0] CMD_ABSOLUTE = 4'd13;

    localparam [3:0] ST_IDLE = 4'd0;
    localparam [3:0] ST_ENABLE_SEND = 4'd1;
    localparam [3:0] ST_ENABLE_WAIT = 4'd2;
    localparam [3:0] ST_ENABLE_GAP = 4'd3;
    localparam [3:0] ST_RUN_SEND = 4'd4;
    localparam [3:0] ST_RUN_WAIT = 4'd5;
    localparam [3:0] ST_STOP_SEND = 4'd6;
    localparam [3:0] ST_STOP_WAIT = 4'd7;
    localparam [3:0] ST_DISABLE_GAP = 4'd8;
    localparam [3:0] ST_DISABLE_SEND = 4'd9;
    localparam [3:0] ST_DISABLE_WAIT = 4'd10;
    localparam [3:0] ST_QUERY_SEND = 4'd11;
    localparam [3:0] ST_QUERY_WAIT = 4'd12;
    localparam [3:0] ST_HOME_FIRST = 4'd13;
    localparam [3:0] ST_HOME_SECOND = 4'd14;
    localparam [3:0] ST_HOME_WAIT = 4'd15;
    localparam integer HOME_ACK_GRACE_TICKS = CLK_HZ / 50;

    localparam [31:0] ERR_BAD_COMMAND = 32'hFFFF_2001;
    localparam [31:0] ERR_BUSY = 32'hFFFF_2002;
    localparam [31:0] ERR_BAD_SPEED = 32'hFFFF_2003;
    localparam [31:0] ERR_CAN_TX = 32'hFFFF_2004;
    localparam [31:0] ERR_ENABLE_TIMEOUT = 32'hFFFF_2101;
    localparam [31:0] ERR_ENABLE_REJECTED = 32'hFFFF_2102;
    localparam [31:0] ERR_RUN_TIMEOUT = 32'hFFFF_2201;
    localparam [31:0] ERR_RUN_REJECTED = 32'hFFFF_2202;
    localparam [31:0] ERR_STOP_TIMEOUT = 32'hFFFF_2301;
    localparam [31:0] ERR_STOP_REJECTED = 32'hFFFF_2302;
    localparam [31:0] ERR_DISABLE_TIMEOUT = 32'hFFFF_2401;
    localparam [31:0] ERR_DISABLE_REJECTED = 32'hFFFF_2402;

    reg [7:0] node_q;
    reg [5:0] moving_mask_q;
    reg [5:0] watchdog_pending_q;
    wire [5:0] stop_remaining = watchdog_pending_q & ~(6'b000001 << (node_q-1'b1));
    assign moving_o = |moving_mask_q;
    function [7:0] first_moving_node;
        input [5:0] mask;
        begin
            if(mask[0]) first_moving_node=1;
            else if(mask[1]) first_moving_node=2;
            else if(mask[2]) first_moving_node=3;
            else if(mask[3]) first_moving_node=4;
            else if(mask[4]) first_moving_node=5;
            else first_moving_node=6;
        end
    endfunction
    reg [5:0] enabled_mask_q;
    wire [28:0] MOTOR_CAN_ID = {13'd0, node_q, 8'h00};
    wire valid_node = (node_i >= 1 && node_i <= 6);
    assign active_node_o = node_q;
    assign enabled_o = enabled_mask_q[node_q - 1'b1];

    reg [3:0] state_q;
    reg [31:0] timer_q;
    reg [31:0] watchdog_q;
    reg [15:0] speed_q;
    reg [7:0] acceleration_q;
    reg direction_q;
    reg [31:0] target_pulses_q;
    reg absolute_q;
    reg first_done_q, final_done_q;
    // FD has no transaction sequence. An uncertain previous FD cannot be
    // retried as a new absolute target, even after CMD_CLEAR_ERROR or FE.
    reg [5:0] absolute_uncertain_mask_q;
    wire fd_inflight = state_q == ST_HOME_FIRST || state_q == ST_HOME_SECOND || state_q == ST_HOME_WAIT;
    wire interrupting = (cmd_pulse_i && valid_node &&
        (cmd_opcode_i == CMD_STOP || cmd_opcode_i == CMD_DISABLE)) ||
        (moving_o && watchdog_q >= WATCHDOG_TICKS);
    wire absolute_reply_ready = !absolute_q || ((final_done_q || tx_done_i) &&
        !tx_error_i && timer_q < RESPONSE_TIMEOUT_TICKS && !interrupting);
    reg jog_active_q;
    wire jog_deceleration = moving_o && jog_active_q && valid_node &&
        moving_mask_q == (6'b000001 << (node_i-1'b1)) &&
        direction_ccw_i == direction_q && acceleration_i == acceleration_q &&
        speed_rpm_i != 0 && speed_rpm_i <= speed_q;
    reg run_after_enable_q;
    reg disable_after_stop_q;
    reg [7:0] query_function_q;

    assign busy_o = (state_q != ST_IDLE);
    assign state_o = state_q;
    assign tx_extended_o = 1'b1;
    assign tx_id_o = MOTOR_CAN_ID | ((state_q == ST_HOME_SECOND) ? 29'd1 : 29'd0);

    function [15:0] home_speed_limit;
        input [7:0] node;
        begin
            case (node)
                1, 2: home_speed_limit = 16'd2857;
                3: home_speed_limit = 16'd2500;
                4: home_speed_limit = 16'd420;
                5: home_speed_limit = 16'd224;
                6: home_speed_limit = 16'd10;
                default: home_speed_limit = 16'd0;
            endcase
        end
    endfunction

    function response_checksum_ok;
        input [3:0] dlc;
        input [63:0] data;
        begin
            case (dlc)
                4'd1: response_checksum_ok = (data[7:0] == 8'h6B);
                4'd2: response_checksum_ok = (data[15:8] == 8'h6B);
                4'd3: response_checksum_ok = (data[23:16] == 8'h6B);
                4'd4: response_checksum_ok = (data[31:24] == 8'h6B);
                4'd5: response_checksum_ok = (data[39:32] == 8'h6B);
                4'd6: response_checksum_ok = (data[47:40] == 8'h6B);
                4'd7: response_checksum_ok = (data[55:48] == 8'h6B);
                4'd8: response_checksum_ok = (data[63:56] == 8'h6B);
                default: response_checksum_ok = 1'b0;
            endcase
        end
    endfunction

    function response_matches;
        input [7:0] function_code;
        begin
            response_matches = rx_valid_i && rx_extended_i &&
                               (rx_id_i == MOTOR_CAN_ID) &&
                               (rx_dlc_i >= 3) &&
                               (rx_data_i[7:0] == function_code) &&
                               response_checksum_ok(rx_dlc_i, rx_data_i);
        end
    endfunction

    // Only transaction-matched replies enter the PS mailbox. Unrelated CAN
    // traffic cannot overwrite a reply before the slow Linux poll reads it.
    assign reply_valid_o = rx_valid_i && rx_extended_i &&
        (rx_id_i == MOTOR_CAN_ID) && (rx_dlc_i >= 3) &&
        response_checksum_ok(rx_dlc_i, rx_data_i) && (
        ((state_q == ST_ENABLE_WAIT || state_q == ST_DISABLE_WAIT) && rx_data_i[7:0] == 8'hF3) ||
        (state_q == ST_RUN_WAIT && rx_data_i[7:0] == 8'hF6) ||
        (state_q == ST_STOP_WAIT && rx_data_i[7:0] == 8'hFE) ||
        (state_q == ST_HOME_WAIT && rx_data_i[7:0] == 8'hFD && rx_dlc_i == 3 &&
          absolute_reply_ready && (!absolute_q || rx_data_i[15:8] != 8'h9F)) ||
        (state_q == ST_QUERY_WAIT && rx_data_i[7:0] == query_function_q &&
          ((query_function_q == 8'h36 && rx_dlc_i == 7 && rx_data_i[15:8] <= 1) ||
           (query_function_q == 8'h1A && (rx_dlc_i == 3 || rx_dlc_i == 4)) ||
           ((query_function_q == 8'h0A || query_function_q == 8'h50 || query_function_q == 8'h3A || query_function_q == 8'h3B) && rx_dlc_i == 3))));

    always @* begin
        tx_valid_o = 1'b0;
        tx_dlc_o = 4'd0;
        tx_data_o = 64'd0;
        case (state_q)
            ST_QUERY_SEND: begin
                tx_valid_o = 1'b1;
                tx_dlc_o = (query_function_q == 8'h0A || query_function_q == 8'h50) ? 4'd3 : 4'd2;
                tx_data_o = (query_function_q == 8'h0A) ? 64'h0000_0000_006B_6D0A :
                            (query_function_q == 8'h50) ? 64'h0000_0000_006B_0050 : {48'd0, 8'h6B, query_function_q};
            end
            ST_HOME_FIRST: begin
                tx_valid_o = 1'b1;
                tx_dlc_o = 4'd8;
                tx_data_o = {target_pulses_q[15:8], target_pulses_q[23:16], target_pulses_q[31:24],
                             acceleration_q, speed_q[7:0], speed_q[15:8],
                             (absolute_q && direction_q ? 8'h01 : 8'h00), 8'hFD};
            end
            ST_HOME_SECOND: begin
                tx_valid_o = !absolute_q || first_done_q;
                tx_dlc_o = 4'd5;
                tx_data_o = {24'd0, 8'h6B, 8'h00, 8'h01, target_pulses_q[7:0], 8'hFD};
            end
            ST_ENABLE_SEND: begin
                tx_valid_o = 1'b1;
                tx_dlc_o = 4'd5;
                tx_data_o = 64'h0000_006B_0001_ABF3;
            end
            ST_RUN_SEND: begin
                tx_valid_o = 1'b1;
                tx_dlc_o = 4'd7;
                tx_data_o = {8'h00, 8'h6B, 8'h00, acceleration_q,
                             speed_q[7:0], speed_q[15:8],
                             (direction_q ? 8'h01 : 8'h00), 8'hF6};
            end
            ST_STOP_SEND: begin
                tx_valid_o = 1'b1;
                tx_dlc_o = 4'd4;
                tx_data_o = 64'h0000_0000_6B00_98FE;
            end
            ST_DISABLE_SEND: begin
                tx_valid_o = 1'b1;
                tx_dlc_o = 4'd5;
                tx_data_o = 64'h0000_006B_0000_ABF3;
            end
            default: begin end
        endcase
    end

    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            state_q <= ST_IDLE;
            timer_q <= 0;
            watchdog_q <= 0;
            speed_q <= 16'd30;
            acceleration_q <= 8'd50;
            direction_q <= 1'b0;
            target_pulses_q <= 0; absolute_q <= 0;
            first_done_q <= 0; final_done_q <= 0;
            absolute_uncertain_mask_q <= 0;
            run_after_enable_q <= 1'b0;
            disable_after_stop_q <= 1'b0;
            query_function_q <= 8'h1A;
            enabled_mask_q <= 0;
            node_q <= NODE_ID;
            moving_mask_q <= 0;
            jog_active_q <= 0;
            watchdog_pending_q <= 0;
            error_o <= 1'b0;
            watchdog_stop_o <= 1'b0;
            error_code_o <= 0;
        end else begin
            if (fd_inflight && interrupting)
                absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
            if (state_q == ST_HOME_SECOND && tx_done_i) first_done_q <= 1'b1;
            if (state_q == ST_HOME_WAIT && tx_done_i) final_done_q <= 1'b1;
            if (heartbeat_pulse_i)
                watchdog_q <= 0;
            else if (moving_o && watchdog_q < WATCHDOG_TICKS)
                watchdog_q <= watchdog_q + 1'b1;
            else if (!moving_o)
                watchdog_q <= 0;

            // STOP and DISABLE may pre-empt a transaction.  The CAN core
            // completes any already-buffered frame before accepting FE.
            if (cmd_pulse_i && valid_node && (cmd_opcode_i == CMD_STOP)) begin
                node_q <= node_i;
                watchdog_pending_q <= 0;
                timer_q <= 0;
                disable_after_stop_q <= 1'b0;
                run_after_enable_q <= 1'b0;
                error_o <= 1'b0;
                error_code_o <= 0;
                state_q <= ST_STOP_SEND;
            end else if (cmd_pulse_i && valid_node && (cmd_opcode_i == CMD_DISABLE) && (!moving_o || moving_mask_q[node_i-1'b1])) begin
                node_q <= node_i;
                watchdog_pending_q <= 0;
                timer_q <= 0;
                run_after_enable_q <= 1'b0;
                error_o <= 1'b0;
                error_code_o <= 0;
                if (moving_mask_q[node_i-1'b1]) begin
                    disable_after_stop_q <= 1'b1;
                    state_q <= ST_STOP_SEND;
                end else begin
                    disable_after_stop_q <= 1'b0;
                    state_q <= ST_DISABLE_SEND;
                end
            end else if (moving_o && (watchdog_q >= WATCHDOG_TICKS) &&
                         state_q != ST_STOP_SEND && state_q != ST_STOP_WAIT) begin
                timer_q <= 0;
                disable_after_stop_q <= 1'b0;
                run_after_enable_q <= 1'b0;
                node_q <= first_moving_node(moving_mask_q);
                watchdog_pending_q <= moving_mask_q;
                watchdog_stop_o <= 1'b1;
                error_o <= 1'b1;
                error_code_o <= 32'hFFFF_25FE;
                state_q <= ST_STOP_SEND;
            end else begin
                case (state_q)
                    ST_IDLE: begin
                        timer_q <= 0;
                        if (cmd_pulse_i) begin
                            if (!valid_node || (moving_o && !(cmd_opcode_i == CMD_RUN && jog_deceleration) && cmd_opcode_i != CMD_HOME && cmd_opcode_i != CMD_ABSOLUTE && cmd_opcode_i != CMD_QUERY && cmd_opcode_i != CMD_POSITION && cmd_opcode_i != CMD_HOME_STATUS && cmd_opcode_i != CMD_MOTOR_STATUS && cmd_opcode_i != CMD_ZERO)) begin
                                error_o <= 1'b1;
                                error_code_o <= ERR_BAD_COMMAND;
                            end else begin
                            node_q <= node_i;
                            case (cmd_opcode_i)
                                CMD_QUERY, CMD_POSITION, CMD_HOME_STATUS, CMD_MOTOR_STATUS, CMD_ZERO, CMD_MARK_SESSION: begin
                                    if (cmd_opcode_i == CMD_ZERO && moving_o) begin
                                        error_o <= 1'b1;
                                        error_code_o <= ERR_BAD_COMMAND;
                                    end else begin
                                    case (cmd_opcode_i)
                                        CMD_ZERO: query_function_q <= 8'h0A;
                                        CMD_POSITION: query_function_q <= 8'h36;
                                        CMD_HOME_STATUS: query_function_q <= 8'h3B;
                                        CMD_MOTOR_STATUS: query_function_q <= 8'h3A;
                                        CMD_MARK_SESSION: query_function_q <= 8'h50;
                                        default: query_function_q <= 8'h1A;
                                    endcase
                                    error_o <= 1'b0;
                                    error_code_o <= 0;
                                    state_q <= ST_QUERY_SEND;
                                    end
                                end
                                CMD_HOME, CMD_ABSOLUTE: begin
                                    if (cmd_opcode_i == CMD_ABSOLUTE && absolute_uncertain_mask_q[node_i-1'b1]) begin
                                        error_o <= 1'b1;
                                        error_code_o <= 32'hFFFF_2701;
                                    end else if (moving_mask_q[node_i-1'b1] || !enabled_mask_q[node_i - 1'b1] || speed_rpm_i == 0 || speed_rpm_i > home_speed_limit(node_i) || (cmd_opcode_i == CMD_HOME && acceleration_i == 0)) begin
                                        error_o <= 1'b1;
                                        error_code_o <= ERR_BAD_COMMAND;
                                    end else begin
                                        speed_q <= speed_rpm_i;
                                        acceleration_q <= acceleration_i;
                                        absolute_q <= (cmd_opcode_i == CMD_ABSOLUTE);
                                        target_pulses_q <= (cmd_opcode_i == CMD_ABSOLUTE) ? target_pulses_i : 32'd0;
                                        direction_q <= (cmd_opcode_i == CMD_ABSOLUTE) ? direction_ccw_i : 1'b0;
                                        first_done_q <= 0; final_done_q <= 0;
                                        error_o <= 0; error_code_o <= 0;
                                        watchdog_stop_o <= 0; watchdog_q <= 0;
                                        state_q <= ST_HOME_FIRST;
                                    end
                                end
                                CMD_ENABLE: begin
                                    error_o <= 1'b0;
                                    error_code_o <= 0;
                                    watchdog_stop_o <= 1'b0;
                                    run_after_enable_q <= 1'b0;
                                    state_q <= ST_ENABLE_SEND;
                                end
                                CMD_RUN: begin
                                    if ((speed_rpm_i == 0) || (speed_rpm_i > 3000)) begin
                                        error_o <= 1'b1;
                                        error_code_o <= ERR_BAD_SPEED;
                                    end else if (!enabled_mask_q[node_i - 1'b1] || (moving_o && !jog_deceleration)) begin
                                        error_o <= 1'b1;
                                        error_code_o <= ERR_BAD_COMMAND;
                                    end else begin
                                        error_o <= 1'b0;
                                        error_code_o <= 0;
                                        watchdog_stop_o <= 1'b0;
                                        watchdog_q <= 0;
                                        speed_q <= speed_rpm_i;
                                        acceleration_q <= acceleration_i;
                                        direction_q <= direction_ccw_i;
                                        run_after_enable_q <= 1'b0;
                                        state_q <= ST_RUN_SEND;
                                    end
                                end
                                CMD_CLEAR_ERROR: begin
                                    error_o <= 1'b0;
                                    error_code_o <= 0;
                                    watchdog_stop_o <= 1'b0;
                                end
                                4'd0: begin end
                                default: begin
                                    error_o <= 1'b1;
                                    error_code_o <= ERR_BAD_COMMAND;
                                end
                            endcase
                            end
                        end
                    end

                    ST_QUERY_SEND: if (tx_valid_o && tx_ready_i) begin
                        timer_q <= 0;
                        state_q <= ST_QUERY_WAIT;
                    end
                    ST_QUERY_WAIT: begin
                        if (tx_error_i || timer_q >= RESPONSE_TIMEOUT_TICKS) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_CAN_TX;
                            state_q <= ST_IDLE;
                        end else if (reply_valid_o) begin
                            state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end
                    ST_HOME_FIRST: if (absolute_q && (tx_error_i || timer_q >= RESPONSE_TIMEOUT_TICKS)) begin
                        absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
                        error_o <= 1; error_code_o <= ERR_CAN_TX;
                        state_q <= ST_STOP_SEND; timer_q <= 0; disable_after_stop_q <= 0;
                    end else if (tx_valid_o && tx_ready_i) begin
                        jog_active_q <= 0;
                        moving_mask_q[node_q-1'b1] <= 1'b1;
                        watchdog_q <= 0; timer_q <= 0;
                        state_q <= ST_HOME_SECOND;
                    end else if (absolute_q) timer_q <= timer_q + 1'b1;
                    ST_HOME_SECOND: begin
                        if (tx_error_i || timer_q >= RESPONSE_TIMEOUT_TICKS) begin
                            absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
                            error_o <= 1; error_code_o <= ERR_CAN_TX;
                            state_q <= ST_STOP_SEND; timer_q <= 0;
                            disable_after_stop_q <= 0;
                        end else if (tx_valid_o && tx_ready_i) begin
                            timer_q <= 0; state_q <= ST_HOME_WAIT;
                        end else timer_q <= timer_q + 1'b1;
                    end
                    ST_HOME_WAIT: begin
                        if (tx_error_i || timer_q >= RESPONSE_TIMEOUT_TICKS) begin
                            absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
                            error_o <= 1; error_code_o <= ERR_RUN_TIMEOUT;
                            state_q <= ST_STOP_SEND; timer_q <= 0;
                            disable_after_stop_q <= 0;
                        end else if (reply_valid_o) begin
                            if (rx_data_i[15:8] == 8'h02 || (!absolute_q && rx_data_i[15:8] == 8'h9F)) begin
                                state_q <= ST_IDLE;
                                if (rx_data_i[15:8] == 8'h9F) absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
                            end
                            else begin
                                absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
                                error_o <= 1; error_code_o <= ERR_RUN_REJECTED;
                                state_q <= ST_STOP_SEND; timer_q <= 0;
                                disable_after_stop_q <= 0;
                            end
                        end else if (!absolute_q && tx_ready_i && timer_q >= HOME_ACK_GRACE_TICKS) begin
                            absolute_uncertain_mask_q[node_q-1'b1] <= 1'b1;
                            // Reached/Other firmware may omit the receive ACK.
                            // Release the mailbox after CAN transmission; retain
                            // motion/watchdog until PS verifies actual position.
                            state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end
                    ST_ENABLE_SEND: if (tx_valid_o && tx_ready_i) begin
                        timer_q <= 0;
                        state_q <= ST_ENABLE_WAIT;
                    end
                    ST_ENABLE_WAIT: begin
                        if (tx_error_i) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_CAN_TX;
                            state_q <= ST_IDLE;
                        end else if (response_matches(8'hF3)) begin
                            if (rx_data_i[15:8] == 8'h02) begin
                                enabled_mask_q[node_q - 1'b1] <= 1'b1;
                                timer_q <= 0;
                                state_q <= ST_ENABLE_GAP;
                            end else begin
                                error_o <= 1'b1;
                                error_code_o <= ERR_ENABLE_REJECTED;
                                state_q <= ST_IDLE;
                            end
                        end else if (timer_q >= RESPONSE_TIMEOUT_TICKS) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_ENABLE_TIMEOUT;
                            state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end
                    ST_ENABLE_GAP: begin
                        if (timer_q >= ENABLE_GAP_TICKS-1) begin
                            timer_q <= 0;
                            run_after_enable_q <= 1'b0;
                            state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end

                    ST_RUN_SEND: if (tx_valid_o && tx_ready_i) begin
                        jog_active_q <= 1;
                        // Arm watchdog on transmission, even if F6 reply is lost.
                        moving_mask_q[node_q-1'b1] <= 1'b1;
                        watchdog_q <= 0;
                        timer_q <= 0;
                        state_q <= ST_RUN_WAIT;
                    end
                    ST_RUN_WAIT: begin
                        if (tx_error_i) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_CAN_TX;
                            state_q <= ST_IDLE;
                        end else if (response_matches(8'hF6)) begin
                            if (rx_data_i[15:8] == 8'h02) begin
                                moving_mask_q[node_q-1'b1] <= 1'b1;
                                watchdog_q <= 0;
                                state_q <= ST_IDLE;
                            end else begin
                                error_o <= 1'b1;
                                error_code_o <= ERR_RUN_REJECTED;
                                state_q <= ST_IDLE;
                            end
                        end else if (timer_q >= RESPONSE_TIMEOUT_TICKS) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_RUN_TIMEOUT;
                            state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end

                    ST_STOP_SEND: if (tx_valid_o && tx_ready_i) begin
                        timer_q <= 0;
                        state_q <= ST_STOP_WAIT;
                    end
                    ST_STOP_WAIT: begin
                        if (tx_error_i || timer_q >= RESPONSE_TIMEOUT_TICKS || response_matches(8'hFE)) begin
                            timer_q <= 0;
                            if (!tx_error_i && response_matches(8'hFE) && rx_data_i[15:8] == 8'h02) begin
                                moving_mask_q[node_q-1'b1] <= 1'b0;
                                if (moving_mask_q == (6'b000001 << (node_q-1'b1))) jog_active_q <= 0;
                            end else begin
                                error_o <= 1'b1;
                                error_code_o <= tx_error_i ? ERR_CAN_TX :
                                    (response_matches(8'hFE) ? ERR_STOP_REJECTED : ERR_STOP_TIMEOUT);
                            end
                            watchdog_pending_q <= stop_remaining;
                            if (|stop_remaining) begin
                                node_q <= first_moving_node(stop_remaining);
                                state_q <= ST_STOP_SEND;
                            end else if (disable_after_stop_q && !tx_error_i &&
                                response_matches(8'hFE) && rx_data_i[15:8] == 8'h02)
                                state_q <= ST_DISABLE_GAP;
                            else state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end
                    ST_DISABLE_GAP: begin
                        if (timer_q >= DISABLE_GAP_TICKS-1) begin
                            timer_q <= 0;
                            disable_after_stop_q <= 1'b0;
                            state_q <= ST_DISABLE_SEND;
                        end else timer_q <= timer_q + 1'b1;
                    end

                    ST_DISABLE_SEND: if (tx_valid_o && tx_ready_i) begin
                        timer_q <= 0;
                        state_q <= ST_DISABLE_WAIT;
                    end
                    ST_DISABLE_WAIT: begin
                        if (tx_error_i) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_CAN_TX;
                            state_q <= ST_IDLE;
                        end else if (response_matches(8'hF3)) begin
                            if (rx_data_i[15:8] == 8'h02) begin
                                enabled_mask_q[node_q - 1'b1] <= 1'b0;
                                moving_mask_q[node_q-1'b1] <= 1'b0;
                                state_q <= ST_IDLE;
                            end else begin
                                error_o <= 1'b1;
                                error_code_o <= ERR_DISABLE_REJECTED;
                                state_q <= ST_IDLE;
                            end
                        end else if (timer_q >= RESPONSE_TIMEOUT_TICKS) begin
                            error_o <= 1'b1;
                            error_code_o <= ERR_DISABLE_TIMEOUT;
                            state_q <= ST_IDLE;
                        end else timer_q <= timer_q + 1'b1;
                    end
                    default: begin
                        error_o <= 1'b1;
                        error_code_o <= ERR_BUSY;
                        state_q <= ST_IDLE;
                    end
                endcase
            end
        end
    end
endmodule
