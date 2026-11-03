`timescale 1ns/1ps

// Minimal synthesizable Classic-CAN 2.0B controller for the stage-0 bench.
//
// Scope:
//   * standard (11-bit) and extended (29-bit) data frames, DLC 0..8;
//   * CRC-15, bit stuffing/de-stuffing and ACK generation/checking;
//   * buffered transmit with bounded automatic retry;
//   * complete-frame ready/valid interface.
//
// This is deliberately not presented as a production safety-certified CAN
// controller.  It is intended for the read-only CANopen preflight image.  A
// commercial or independently verified controller shall replace it before the
// robot is allowed to move.
//
// Data layout: byte 0 is data[7:0], byte 7 is data[63:56].
module can_classic_core #(
    parameter integer CLK_HZ       = 100_000_000,
    parameter integer CAN_BITRATE  = 500_000,
    parameter integer SAMPLE_NUM   = 3,
    parameter integer SAMPLE_DEN   = 4,
    parameter integer MAX_RETRIES  = 3
) (
    input  wire        clk_i,
    input  wire        rst_ni,

    input  wire        can_rx_i,
    output wire        can_tx_o,

    input  wire        tx_valid_i,
    input  wire        tx_abort_i,
    output wire        tx_ready_o,
    input  wire        tx_extended_i,
    input  wire [28:0] tx_id_i,
    input  wire [3:0]  tx_dlc_i,
    input  wire [63:0] tx_data_i,
    output reg         tx_done_o,
    output reg         tx_error_o,
    output reg         tx_no_ack_o,

    output reg         rx_valid_o,
    output reg         rx_extended_o,
    output reg  [28:0] rx_id_o,
    output reg  [3:0]  rx_dlc_o,
    output reg  [63:0] rx_data_o,
    output reg         rx_crc_error_o,
    output reg         rx_stuff_error_o,

    output wire        bus_active_o
);

    localparam integer BIT_CLKS = CLK_HZ / CAN_BITRATE;
    localparam integer SAMPLE_CLKS = (BIT_CLKS * SAMPLE_NUM) / SAMPLE_DEN;
    localparam integer IDLE_CLKS = BIT_CLKS * 3;

    localparam [2:0] TX_IDLE       = 3'd0;
    localparam [2:0] TX_PREP       = 3'd1;
    localparam [2:0] TX_WAIT_BUS   = 3'd2;
    localparam [2:0] TX_STUFFED    = 3'd3;
    localparam [2:0] TX_CRC_DELIM  = 3'd4;
    localparam [2:0] TX_ACK        = 3'd5;
    localparam [2:0] TX_ACK_DELIM  = 3'd6;
    localparam [2:0] TX_EOF        = 3'd7;

    localparam [2:0] RX_STUFFED    = 3'd0;
    localparam [2:0] RX_CRC_DELIM  = 3'd1;
    localparam [2:0] RX_ACK        = 3'd2;
    localparam [2:0] RX_ACK_DELIM  = 3'd3;
    localparam [2:0] RX_EOF        = 3'd4;

    reg rx_meta_q, rx_sync_q, rx_prev_q;
    wire rx_falling = rx_prev_q && !rx_sync_q;

    reg [2:0]  tx_state_q;
    reg        tx_pending_q;
    reg        tx_abort_latched_q;
    wire abort_requested=(tx_abort_i === 1'b1);
    reg        tx_extended_q;
    reg [28:0] tx_id_q;
    reg [3:0]  tx_dlc_q;
    reg [63:0] tx_data_q;
    reg [7:0]  tx_base_len_q;
    reg [7:0]  tx_total_len_q;
    reg [7:0]  tx_prep_pos_q;
    reg [14:0] tx_crc_work_q;
    reg [14:0] tx_crc_q;
    reg [7:0]  tx_logical_pos_q;
    reg [2:0]  tx_run_q;
    reg        tx_last_q;
    reg        tx_bit_q;
    reg        tx_stuff_q;
    reg        tx_after_stuff_delim_q;
    reg [15:0] tx_clk_count_q;
    reg [3:0]  tx_eof_count_q;
    reg        tx_ack_seen_q;
    reg [3:0]  tx_retry_q;

    reg [31:0] idle_count_q;

    reg        rx_active_q;
    reg [2:0]  rx_phase_q;
    reg [15:0] rx_clk_count_q;
    reg [7:0]  rx_logical_pos_q;
    reg [7:0]  rx_base_len_q;
    reg [2:0]  rx_run_q;
    reg        rx_last_bit_q;
    reg        rx_crc_logic_done_q;
    reg        rx_stuffed_complete_q;
    reg [14:0] rx_crc_work_q;
    reg [14:0] rx_crc_field_q;
    reg        rx_crc_good_q;
    reg        rx_extended_work_q;
    reg        rx_srr_rtr_q;
    reg [28:0] rx_id_work_q;
    reg [3:0]  rx_dlc_work_q;
    reg [63:0] rx_data_work_q;
    reg [3:0]  rx_eof_count_q;
    reg        rx_frame_good_q;
    reg        ack_drive_q;

    wire tx_active = (tx_state_q == TX_STUFFED) ||
                     (tx_state_q == TX_CRC_DELIM) ||
                     (tx_state_q == TX_ACK) ||
                     (tx_state_q == TX_ACK_DELIM) ||
                     (tx_state_q == TX_EOF);

    assign can_tx_o = ack_drive_q ? 1'b0 :
                      (tx_active ? tx_bit_q : 1'b1);
    assign tx_ready_o = !tx_pending_q && !abort_requested;
    assign bus_active_o = tx_active || rx_active_q || tx_pending_q;

    function [14:0] crc15_next;
        input [14:0] crc;
        input        bit_in;
        reg          feedback;
        reg [14:0]   shifted;
        begin
            feedback = crc[14] ^ bit_in;
            shifted = {crc[13:0], 1'b0};
            if (feedback)
                shifted = shifted ^ 15'h4599;
            crc15_next = shifted;
        end
    endfunction

    function tx_base_bit;
        input [7:0] pos;
        integer data_pos;
        integer byte_num;
        integer bit_num;
        begin
            if (pos == 0) begin
                tx_base_bit = 1'b0;                       // SOF
            end else if (pos <= 11) begin
                tx_base_bit = tx_extended_q ?
                              tx_id_q[29-pos] : tx_id_q[11-pos];
            end else if (tx_extended_q) begin
                if (pos == 12 || pos == 13)
                    tx_base_bit = 1'b1;                   // SRR, IDE
                else if (pos <= 31)
                    tx_base_bit = tx_id_q[31-pos];        // ID[17:0]
                else if (pos <= 34)
                    tx_base_bit = 1'b0;                   // RTR, r1, r0
                else if (pos <= 38)
                    tx_base_bit = tx_dlc_q[38-pos];       // DLC MSB first
                else begin
                    data_pos = pos - 39;
                    byte_num = data_pos >> 3;
                    bit_num = data_pos & 7;
                    tx_base_bit = tx_data_q[(byte_num*8)+(7-bit_num)];
                end
            end else begin
                if (pos <= 14)
                    tx_base_bit = 1'b0;                   // RTR, IDE, r0
                else if (pos <= 18)
                    tx_base_bit = tx_dlc_q[18-pos];       // DLC MSB first
                else begin
                    data_pos = pos - 19;
                    byte_num = data_pos >> 3;
                    bit_num = data_pos & 7;
                    tx_base_bit = tx_data_q[(byte_num*8)+(7-bit_num)];
                end
            end
        end
    endfunction

    function tx_logical_bit;
        input [7:0] pos;
        begin
            if (pos < tx_base_len_q)
                tx_logical_bit = tx_base_bit(pos);
            else
                tx_logical_bit = tx_crc_q[14-(pos-tx_base_len_q)];
        end
    endfunction

    task tx_schedule_logical;
        input [7:0] next_pos;
        reg next_bit;
        begin
            next_bit = tx_logical_bit(next_pos);
            tx_logical_pos_q <= next_pos;
            tx_bit_q <= next_bit;
            tx_stuff_q <= 1'b0;
            if (next_bit == tx_last_q)
                tx_run_q <= tx_run_q + 1'b1;
            else begin
                tx_run_q <= 3'd1;
                tx_last_q <= next_bit;
            end
        end
    endtask

    // Input synchronizer and bus-idle detector.
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            rx_meta_q   <= 1'b1;
            rx_sync_q   <= 1'b1;
            rx_prev_q   <= 1'b1;
            idle_count_q <= IDLE_CLKS;
        end else begin
            rx_meta_q <= can_rx_i;
            rx_sync_q <= rx_meta_q;
            rx_prev_q <= rx_sync_q;
            // EOF recessive bits are part of the current frame, not the
            // three-bit intermission required before the next SOF.
            if (!rx_sync_q || tx_active || rx_active_q)
                idle_count_q <= 0;
            else if (idle_count_q < IDLE_CLKS)
                idle_count_q <= idle_count_q + 1'b1;
        end
    end

    // Transmitter and CRC preparation.
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            tx_state_q       <= TX_IDLE;
            tx_pending_q     <= 1'b0;
            tx_abort_latched_q <= 1'b0;
            tx_extended_q    <= 1'b0;
            tx_id_q          <= 0;
            tx_dlc_q         <= 0;
            tx_data_q        <= 0;
            tx_base_len_q    <= 0;
            tx_total_len_q   <= 0;
            tx_prep_pos_q    <= 0;
            tx_crc_work_q    <= 0;
            tx_crc_q         <= 0;
            tx_logical_pos_q <= 0;
            tx_run_q         <= 0;
            tx_last_q        <= 1'b1;
            tx_bit_q         <= 1'b1;
            tx_stuff_q       <= 1'b0;
            tx_after_stuff_delim_q <= 1'b0;
            tx_clk_count_q   <= 0;
            tx_eof_count_q   <= 0;
            tx_ack_seen_q    <= 1'b0;
            tx_retry_q       <= 0;
            tx_done_o        <= 1'b0;
            tx_error_o       <= 1'b0;
            tx_no_ack_o      <= 1'b0;
        end else begin
            tx_done_o   <= 1'b0;
            tx_error_o  <= 1'b0;
            tx_no_ack_o <= 1'b0;

            if(abort_requested && tx_pending_q)tx_abort_latched_q<=1'b1;
            if (tx_valid_i && tx_ready_o) begin
                if (tx_dlc_i > 8) begin
                    tx_error_o <= 1'b1;
                end else begin
                    tx_pending_q   <= 1'b1;
                    tx_abort_latched_q <= 1'b0;
                    tx_extended_q  <= tx_extended_i;
                    tx_id_q        <= tx_id_i;
                    tx_dlc_q       <= tx_dlc_i;
                    tx_data_q      <= tx_data_i;
                    tx_base_len_q  <= (tx_extended_i ? 39 : 19) +
                                      (tx_dlc_i << 3);
                    tx_total_len_q <= (tx_extended_i ? 54 : 34) +
                                      (tx_dlc_i << 3);
                    tx_prep_pos_q  <= 0;
                    tx_crc_work_q  <= 0;
                    tx_retry_q     <= 0;
                    tx_state_q     <= TX_PREP;
                end
            end

            case (tx_state_q)
                TX_IDLE: begin
                    tx_bit_q <= 1'b1;
                end

                TX_PREP: begin
                    tx_crc_work_q <= crc15_next(tx_crc_work_q,
                                                tx_base_bit(tx_prep_pos_q));
                    if (tx_prep_pos_q == (tx_base_len_q - 1'b1)) begin
                        tx_crc_q <= crc15_next(tx_crc_work_q,
                                              tx_base_bit(tx_prep_pos_q));
                        tx_state_q <= TX_WAIT_BUS;
                    end else begin
                        tx_prep_pos_q <= tx_prep_pos_q + 1'b1;
                    end
                end

                TX_WAIT_BUS: begin
                    tx_bit_q <= 1'b1;
                    if (!rx_active_q && (idle_count_q >= IDLE_CLKS)) begin
                        tx_logical_pos_q <= 0;
                        tx_bit_q         <= 1'b0;
                        tx_last_q        <= 1'b0;
                        tx_run_q         <= 3'd1;
                        tx_stuff_q       <= 1'b0;
                        tx_after_stuff_delim_q <= 1'b0;
                        tx_clk_count_q   <= 0;
                        tx_ack_seen_q    <= 1'b0;
                        tx_state_q       <= TX_STUFFED;
                    end
                end

                TX_STUFFED: begin
                    if (tx_clk_count_q == BIT_CLKS-1) begin
                        tx_clk_count_q <= 0;
                        if (tx_stuff_q) begin
                            if (tx_after_stuff_delim_q) begin
                                tx_bit_q <= 1'b1;
                                tx_state_q <= TX_CRC_DELIM;
                                tx_after_stuff_delim_q <= 1'b0;
                            end else begin
                                tx_schedule_logical(tx_logical_pos_q + 1'b1);
                            end
                        end else if (tx_run_q == 5) begin
                            tx_bit_q   <= ~tx_last_q;
                            tx_last_q  <= ~tx_last_q;
                            tx_run_q   <= 3'd1;
                            tx_stuff_q <= 1'b1;
                            if (tx_logical_pos_q == tx_total_len_q-1'b1)
                                tx_after_stuff_delim_q <= 1'b1;
                        end else if (tx_logical_pos_q == tx_total_len_q-1'b1) begin
                            tx_bit_q   <= 1'b1;
                            tx_state_q <= TX_CRC_DELIM;
                        end else begin
                            tx_schedule_logical(tx_logical_pos_q + 1'b1);
                        end
                    end else begin
                        tx_clk_count_q <= tx_clk_count_q + 1'b1;
                    end
                end

                TX_CRC_DELIM: begin
                    if (tx_clk_count_q == BIT_CLKS-1) begin
                        tx_clk_count_q <= 0;
                        tx_bit_q <= 1'b1;
                        tx_state_q <= TX_ACK;
                    end else tx_clk_count_q <= tx_clk_count_q + 1'b1;
                end

                TX_ACK: begin
                    if (tx_clk_count_q == SAMPLE_CLKS-1 && !rx_sync_q)
                        tx_ack_seen_q <= 1'b1;
                    if (tx_clk_count_q == BIT_CLKS-1) begin
                        tx_clk_count_q <= 0;
                        tx_bit_q <= 1'b1;
                        tx_state_q <= TX_ACK_DELIM;
                    end else tx_clk_count_q <= tx_clk_count_q + 1'b1;
                end

                TX_ACK_DELIM: begin
                    if (tx_clk_count_q == BIT_CLKS-1) begin
                        tx_clk_count_q <= 0;
                        tx_eof_count_q <= 0;
                        tx_bit_q <= 1'b1;
                        tx_state_q <= TX_EOF;
                    end else tx_clk_count_q <= tx_clk_count_q + 1'b1;
                end

                TX_EOF: begin
                    if (tx_clk_count_q == BIT_CLKS-1) begin
                        tx_clk_count_q <= 0;
                        if (tx_eof_count_q == 6) begin
                            tx_bit_q <= 1'b1;
                            if (tx_ack_seen_q) begin
                                tx_pending_q <= 1'b0;
                                tx_done_o <= 1'b1;
                                tx_state_q <= TX_IDLE;
                            end else if (!tx_abort_latched_q && !abort_requested && tx_retry_q < MAX_RETRIES) begin
                                tx_retry_q <= tx_retry_q + 1'b1;
                                tx_state_q <= TX_WAIT_BUS;
                            end else begin
                                tx_pending_q <= 1'b0;
                                tx_error_o <= 1'b1;
                                tx_no_ack_o <= 1'b1;
                                tx_state_q <= TX_IDLE;
                            end
                        end else begin
                            tx_eof_count_q <= tx_eof_count_q + 1'b1;
                        end
                    end else tx_clk_count_q <= tx_clk_count_q + 1'b1;
                end

                default: tx_state_q <= TX_IDLE;
            endcase
            // A not-yet-started frame must never survive cancellation and later
            // launch when a blocked bus recovers. An active frame finishes its
            // current wire transmission, but abort disables every retry.
            if(abort_requested && tx_pending_q && !tx_active)begin
                tx_pending_q<=0;tx_state_q<=TX_IDLE;tx_bit_q<=1;tx_clk_count_q<=0;
                tx_error_o<=1;tx_abort_latched_q<=0;
            end
        end
    end

    // Receiver.  It is disabled while this node transmits, preventing self-ACK.
    always @(posedge clk_i or negedge rst_ni) begin
        if (!rst_ni) begin
            rx_active_q          <= 1'b0;
            rx_phase_q           <= RX_STUFFED;
            rx_clk_count_q       <= 0;
            rx_logical_pos_q     <= 0;
            rx_base_len_q        <= 19;
            rx_run_q             <= 0;
            rx_last_bit_q        <= 1'b1;
            rx_crc_logic_done_q  <= 1'b0;
            rx_stuffed_complete_q <= 1'b0;
            rx_crc_work_q        <= 0;
            rx_crc_field_q       <= 0;
            rx_crc_good_q        <= 1'b0;
            rx_extended_work_q   <= 1'b0;
            rx_srr_rtr_q         <= 1'b0;
            rx_id_work_q         <= 0;
            rx_dlc_work_q        <= 0;
            rx_data_work_q       <= 0;
            rx_eof_count_q       <= 0;
            rx_frame_good_q      <= 1'b0;
            ack_drive_q          <= 1'b0;
            rx_valid_o           <= 1'b0;
            rx_extended_o        <= 1'b0;
            rx_id_o              <= 0;
            rx_dlc_o             <= 0;
            rx_data_o            <= 0;
            rx_crc_error_o       <= 1'b0;
            rx_stuff_error_o     <= 1'b0;
        end else begin
            rx_valid_o       <= 1'b0;
            rx_crc_error_o   <= 1'b0;
            rx_stuff_error_o <= 1'b0;

            if (!rx_active_q && !tx_active && rx_falling) begin
                rx_active_q          <= 1'b1;
                rx_phase_q           <= RX_STUFFED;
                rx_clk_count_q       <= 0;
                rx_logical_pos_q     <= 0;
                rx_base_len_q        <= 19;
                rx_run_q             <= 0;
                rx_last_bit_q        <= 1'b1;
                rx_crc_logic_done_q  <= 1'b0;
                rx_stuffed_complete_q <= 1'b0;
                rx_crc_work_q        <= 0;
                rx_crc_field_q       <= 0;
                rx_crc_good_q        <= 1'b0;
                rx_extended_work_q   <= 1'b0;
                rx_srr_rtr_q         <= 1'b0;
                rx_id_work_q         <= 0;
                rx_dlc_work_q        <= 0;
                rx_data_work_q       <= 0;
                rx_eof_count_q       <= 0;
                rx_frame_good_q      <= 1'b1;
                ack_drive_q          <= 1'b0;
            end else if (rx_active_q) begin
                if (rx_clk_count_q == SAMPLE_CLKS-1) begin
                    case (rx_phase_q)
                        RX_STUFFED: begin
                            if (rx_run_q == 5) begin
                                if (rx_sync_q == rx_last_bit_q) begin
                                    rx_stuff_error_o <= 1'b1;
                                    rx_frame_good_q <= 1'b0;
                                    rx_active_q <= 1'b0;
                                end else begin
                                    rx_last_bit_q <= rx_sync_q;
                                    rx_run_q <= 1;
                                    if (rx_crc_logic_done_q)
                                        rx_stuffed_complete_q <= 1'b1;
                                end
                            end else begin
                                if (rx_sync_q == rx_last_bit_q)
                                    rx_run_q <= rx_run_q + 1'b1;
                                else begin
                                    rx_run_q <= 1;
                                    rx_last_bit_q <= rx_sync_q;
                                end

                                if (rx_logical_pos_q == 0 && rx_sync_q != 1'b0)
                                    rx_frame_good_q <= 1'b0;
                                if (rx_logical_pos_q >= 1 && rx_logical_pos_q <= 11)
                                    rx_id_work_q[29-rx_logical_pos_q] <= rx_sync_q;
                                if (rx_logical_pos_q == 12)
                                    rx_srr_rtr_q <= rx_sync_q;
                                if (rx_logical_pos_q == 13) begin
                                    rx_extended_work_q <= rx_sync_q;
                                    if (!rx_sync_q) begin
                                        rx_id_work_q <= {18'd0, rx_id_work_q[28:18]};
                                        if (rx_srr_rtr_q)
                                            rx_frame_good_q <= 1'b0;
                                    end else begin
                                        rx_base_len_q <= 39;
                                        if (!rx_srr_rtr_q)
                                            rx_frame_good_q <= 1'b0;
                                    end
                                end
                                if (!rx_extended_work_q &&
                                    rx_logical_pos_q == 14 && rx_sync_q)
                                    rx_frame_good_q <= 1'b0; // standard-frame r0

                                if (rx_extended_work_q &&
                                    rx_logical_pos_q >= 14 && rx_logical_pos_q <= 31)
                                    rx_id_work_q[31-rx_logical_pos_q] <= rx_sync_q;
                                if (rx_extended_work_q &&
                                    rx_logical_pos_q >= 32 && rx_logical_pos_q <= 34 &&
                                    rx_sync_q)
                                    rx_frame_good_q <= 1'b0; // RTR/r1/r0 must be dominant

                                if (!rx_extended_work_q &&
                                    rx_logical_pos_q >= 15 && rx_logical_pos_q <= 18) begin
                                    rx_dlc_work_q <= {rx_dlc_work_q[2:0], rx_sync_q};
                                    if (rx_logical_pos_q == 18) begin
                                        if ({rx_dlc_work_q[2:0],rx_sync_q} > 8)
                                            rx_frame_good_q <= 1'b0;
                                        else
                                            rx_base_len_q <= 19 +
                                                ({4'd0,rx_dlc_work_q[2:0],rx_sync_q} << 3);
                                    end
                                end

                                if (rx_extended_work_q &&
                                    rx_logical_pos_q >= 35 && rx_logical_pos_q <= 38) begin
                                    rx_dlc_work_q <= {rx_dlc_work_q[2:0], rx_sync_q};
                                    if (rx_logical_pos_q == 38) begin
                                        if ({rx_dlc_work_q[2:0],rx_sync_q} > 8)
                                            rx_frame_good_q <= 1'b0;
                                        else
                                            rx_base_len_q <= 39 +
                                                ({4'd0,rx_dlc_work_q[2:0],rx_sync_q} << 3);
                                    end
                                end

                                if (!rx_extended_work_q && rx_logical_pos_q >= 19 &&
                                    rx_logical_pos_q < rx_base_len_q)
                                    rx_data_work_q[((rx_logical_pos_q-19)>>3)*8 +
                                                   (7-((rx_logical_pos_q-19)&7))] <= rx_sync_q;
                                if (rx_extended_work_q && rx_logical_pos_q >= 39 &&
                                    rx_logical_pos_q < rx_base_len_q)
                                    rx_data_work_q[((rx_logical_pos_q-39)>>3)*8 +
                                                   (7-((rx_logical_pos_q-39)&7))] <= rx_sync_q;

                                if (rx_logical_pos_q < rx_base_len_q)
                                    rx_crc_work_q <= crc15_next(rx_crc_work_q, rx_sync_q);
                                else
                                    rx_crc_field_q <= {rx_crc_field_q[13:0], rx_sync_q};

                                if (rx_logical_pos_q == rx_base_len_q + 14) begin
                                    rx_crc_good_q <=
                                        ({rx_crc_field_q[13:0],rx_sync_q} == rx_crc_work_q);
                                    if ({rx_crc_field_q[13:0],rx_sync_q} != rx_crc_work_q)
                                        rx_crc_error_o <= 1'b1;
                                    rx_crc_logic_done_q <= 1'b1;
                                    if (!((rx_sync_q == rx_last_bit_q) &&
                                          (rx_run_q == 4)))
                                        rx_stuffed_complete_q <= 1'b1;
                                end

                                rx_logical_pos_q <= rx_logical_pos_q + 1'b1;
                            end
                        end

                        RX_CRC_DELIM: begin
                            if (!rx_sync_q)
                                rx_frame_good_q <= 1'b0;
                        end
                        RX_ACK: begin end
                        RX_ACK_DELIM: begin
                            if (!rx_sync_q)
                                rx_frame_good_q <= 1'b0;
                        end
                        RX_EOF: begin
                            if (!rx_sync_q)
                                rx_frame_good_q <= 1'b0;
                        end
                        default: begin end
                    endcase
                end

                if (rx_clk_count_q == BIT_CLKS-1) begin
                    rx_clk_count_q <= 0;
                    case (rx_phase_q)
                        RX_STUFFED: begin
                            if (rx_stuffed_complete_q) begin
                                rx_stuffed_complete_q <= 1'b0;
                                rx_phase_q <= RX_CRC_DELIM;
                            end
                        end
                        RX_CRC_DELIM: begin
                            if (rx_crc_good_q && rx_frame_good_q)
                                ack_drive_q <= 1'b1;
                            rx_phase_q <= RX_ACK;
                        end
                        RX_ACK: begin
                            ack_drive_q <= 1'b0;
                            rx_phase_q <= RX_ACK_DELIM;
                        end
                        RX_ACK_DELIM: begin
                            rx_eof_count_q <= 0;
                            rx_phase_q <= RX_EOF;
                        end
                        RX_EOF: begin
                            if (rx_eof_count_q == 6) begin
                                rx_active_q <= 1'b0;
                                if (rx_crc_good_q && rx_frame_good_q) begin
                                    rx_extended_o <= rx_extended_work_q;
                                    rx_id_o <= rx_id_work_q;
                                    rx_dlc_o <= rx_dlc_work_q;
                                    rx_data_o <= rx_data_work_q;
                                    rx_valid_o <= 1'b1;
                                end
                            end else begin
                                rx_eof_count_q <= rx_eof_count_q + 1'b1;
                            end
                        end
                        default: rx_active_q <= 1'b0;
                    endcase
                end else begin
                    rx_clk_count_q <= rx_clk_count_q + 1'b1;
                end
            end
        end
    end

    initial begin
        if ((CLK_HZ % CAN_BITRATE) != 0)
            $error("CLK_HZ must be an integer multiple of CAN_BITRATE");
        if (BIT_CLKS < 16)
            $error("CAN controller requires at least 16 clocks per CAN bit");
    end

endmodule
