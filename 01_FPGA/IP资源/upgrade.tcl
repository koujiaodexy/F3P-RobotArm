
proc report_ip_status { current_ip_version original_ip_version upgrade_result current_part recommended_part } {

    set $current_ip_version [string trim $current_ip_version]
    set $current_part   [string trim $current_part]
    set $recommended_part   [string trim $recommended_part]
    set $original_ip_version    [string trim $original_ip_version]
    set $upgrade_result     [string trim $upgrade_result]

    if {$current_part != $recommended_part } {
        set IP_Status 3
        set Recommendation 1
        set Lock 1
        set Upgradable 0
        puts "current_part is different from recommended_part"
        return [list $IP_Status $Recommendation $Lock $Upgradable ]
    }

    set recommend_version "1.0.1"
    set IP_comparibiliy_table [list "1.0.0" "1.0.1" ]
    #puts "IP_comparibiliy_table is $IP_comparibiliy_table"
    set comparibiliy_result [lsearch -exact $IP_comparibiliy_table $current_ip_version]
    set recommend_version_list [split $recommend_version "."]
    set current_version_list [split $current_ip_version "."]

    if {$comparibiliy_result == -1} {
        set IP_Status 3
        set Recommendation 1
        set Lock 1
        set Upgradable 0
        puts "version is no include"
        return [list $IP_Status $Recommendation $Lock $Upgradable]      
    } 

    if {[lindex $recommend_version_list 0] != [lindex $current_version_list 0]} {
        set IP_Status 0
        set Recommendation 0
        set Lock 1
        set Upgradable 1
        return [list $IP_Status $Recommendation $Lock $Upgradable]              
    } elseif {[lindex $recommend_version_list 1] != [lindex $current_version_list 1]} {
        set IP_Status 1 
        set Recommendation 0
        set Lock 1
        set Upgradable 1
        return [list $IP_Status $Recommendation $Lock $Upgradable]
    } elseif {[lindex $recommend_version_list 2] != [lindex $current_version_list 2]} {
        set IP_Status 2
        set Recommendation 0
        set Lock 1
        set Upgradable 1
        return [list $IP_Status $Recommendation $Lock $Upgradable]            
    } elseif {$current_ip_version == $recommend_version} {
        set IP_Status 4
        set Recommendation 2
        set Lock 0
        set Upgradable 0
        return [list $IP_Status $Recommendation $Lock $Upgradable]             
    } else {
        set IP_Status 3
        set Recommendation 1
        set Lock 1
        set Upgradable 0            
        return [list $IP_Status $Recommendation $Lock $Upgradable]
    }
}

proc upgrade_ip	{ param_txt_path port_txt_path current_ip_version } {
    if {([file exists $param_txt_path] == 0) || ([file exists $port_txt_path] == 0)} {
        puts "param_txt_path or port_txt_path is not exists, upgrade exit"
        return 0
    } else {
        puts "param_txt_path and port_txt_path is exists !!!!"
        set param_con [open "$param_txt_path" r ] 
        set port_con  [open "$port_txt_path" r ]
    }
    set protocol_us ""
    set protocol_ds ""
    set user_signal_enable ""
    set user_port_enable ""
    set a_content ""

while {[gets $param_con line ] >= 0} {
    #puts "line is $line \n"
    set input_file_line [split $line ":"]
    set input_file_line_index0 [lindex $input_file_line 0]
    set input_file_line_index1 [lindex $input_file_line 1]
    set input_file_line_index2 [lindex $input_file_line 2]
    set input_file_line_index3 [lindex $input_file_line 3]
    set input_file_line_index4 [lindex $input_file_line 4]
    set input_file_line_index5 [lindex $input_file_line 5]

    set input_file_line_index0 [string trim $input_file_line_index0]
    set input_file_line_index1 [string trim $input_file_line_index1]
    set input_file_line_index2 [string trim $input_file_line_index2]
    set input_file_line_index3 [string trim $input_file_line_index3]
    set input_file_line_index4 [string trim $input_file_line_index4]
    set input_file_line_index5 [string trim $input_file_line_index5]

    puts "input_file_line_index0 is $input_file_line_index0"
    puts "input_file_line_index1 is $input_file_line_index1"
    #puts "input_file_line_index2 is $input_file_line_index2"
    #puts "input_file_line_index3 is $input_file_line_index3"
    #puts "input_file_line_index4 is $input_file_line_index4"
    #puts "input_file_line_index5 is $input_file_line_index5"

    if {$input_file_line_index0 == "protocol_us_num"} {
        set protocol_us $input_file_line_index1        
    }

    if {$input_file_line_index0 == "protocol_ds_num"} {
        set protocol_ds $input_file_line_index1 
    }
 
## update protocol range of choice 
    if {$input_file_line_index0 == "protocol_ds_num"} {
        if {$protocol_us == "AXI4"} {
            set line "protocol_ds_num : $input_file_line_index1 : U : En : AXI4LITE;;AXI3 :  :"
        } elseif {$protocol_us == "AXI3"} {
            set line "protocol_ds_num : $input_file_line_index1 : U : En : AXI4LITE;;AXI4 :  :"
        } elseif {$protocol_us == "AXI4LITE"} {
            set line "protocol_ds_num : $input_file_line_index1 : U : En : AXI4;;AXI3 :  :"
        }
    }
## update protocol range of choice end

## one of protocol is axi4lite , user signal disable
    if {($protocol_us == "AXI4LITE") || ($protocol_ds == "AXI4LITE")} {
        set user_signal_enable 0
    } else {
        set user_signal_enable 1
    }

    if {($input_file_line_index0 == "AL_AXI_SUPPORTS_USER_SIGNALS")&&( $user_signal_enable == 0) } {
        set line "AL_AXI_SUPPORTS_USER_SIGNALS : 0 : U : Dis :  :  :"
    }

    if {$input_file_line_index0 == "AXI_SUPPORTS_USER_SIGNALS"} {
        if {$input_file_line_index1 == 1} {
            set user_port_enable 1
            break
        } else {
            set user_port_enable 0
            break
        }
    }

## one of protocol is axi4lite , user signal disable end

## user signal under the control of AL_AXI_SUPPORTS_USER_SIGNALS
    if {($input_file_line_index0 == "AL_AXI_AWUSER_WIDTH")&&( $user_signal_enable == 0)} {
        set line "AL_AXI_AWUSER_WIDTH : 1 : U : Dis :  : 1 : 1024"
    }

    if {($input_file_line_index0 == "AL_AXI_ARUSER_WIDTH")&&( $user_signal_enable == 0)} {
        set line "AL_AXI_ARUSER_WIDTH : 1 : U : Dis :  : 1 : 1024"
    }

    if {($input_file_line_index0 == "AL_AXI_WUSER_WIDTH")&&( $user_signal_enable == 0)} {
        set line "AL_AXI_WUSER_WIDTH : 1 : U : Dis :  : 1 : 1024"
    }

    if {($input_file_line_index0 == "AL_AXI_RUSER_WIDTH")&&( $user_signal_enable == 0)} {
        set line "AL_AXI_RUSER_WIDTH : 1 : U : Dis :  : 1 : 1024"
    }
## user signal under the control of AL_AXI_SUPPORTS_USER_SIGNALS end

## buser signal special control 
    if {($input_file_line_index0 == "AL_AXI_BUSER_WIDTH")} {
        if {$user_signal_enable == 0} {
            set line "AL_AXI_BUSER_WIDTH : 1 : U : Dis :  : 1 : 1024"
        } elseif {($protocol_us == "AXI4") && ($protocol_ds == "AXI3")} {
            set line "AL_AXI_BUSER_WIDTH : 1 : U : Dis :  : 1 : 1024"
        }
    }

## buser signal special control end

    append a_content "$line \n" 

}

close $param_con

set b_content ""

while {[gets $port_con line ] >= 0} {
   # puts ".ports_AXI_DATA_FIFO_0.txt is $line"
    if {[string first "us_axi_awuser" $line] != -1} {
        if {$user_signal_enable == 0} {
            set line "us_axi_awuser ; 0"
        } elseif {$user_port_enable == 0} {
            set line "us_axi_awuser ; 0"
        }
    }

    if {[string first "us_axi_wuser" $line] != -1} {
        if {$user_signal_enable == 0} {
            set line "us_axi_wuser; 0"
        } elseif {$user_port_enable == 0} {
            set line "us_axi_wuser; 0"
        }
    }

    if {[string first "us_axi_buser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "us_axi_buser; 0"
        } elseif {($protocol_us == "AXI4") && ($protocol_ds == "AXI3")} {
            set line "us_axi_buser; 0"
        } elseif {$user_port_enable == 0} {
            set line "us_axi_buser; 0"
        } 
    }

    if {[string first "us_axi_aruser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "us_axi_aruser; 0"
        } elseif {$user_port_enable == 0} {
            set line "us_axi_aruser; 0"
        }
    }

    if {[string first "us_axi_ruser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "us_axi_ruser; 0"
        } 
    }

    if {[string first "ds_axi_awuser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "ds_axi_awuser; 0"
        } elseif {$user_port_enable == 0} {
            set line "ds_axi_awuser; 0"
        }
    }

    if {[string first "ds_axi_wuser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "ds_axi_wuser; 0"
        } elseif {$user_port_enable == 0} {
            set line "ds_axi_wuser; 0"
        }

    }

    if {[string first "ds_axi_buser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "ds_axi_buser; 0"
        } elseif {($protocol_us == "AXI4") && ($protocol_ds == "AXI3")} {
            set line "ds_axi_buser; 0"
        } elseif {$user_port_enable == 0} {
            set line "ds_axi_buser; 0"
        }
    }

    if {[string first "ds_axi_aruser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "ds_axi_aruser; 0"
        } elseif {$user_port_enable == 0} {
            set line "ds_axi_aruser; 0"
        }
    }

    if {[string first "ds_axi_ruser" $line] != -1} {
        if {$user_signal_enable == 0} {            
            set line "ds_axi_ruser; 0"
        } elseif {$user_port_enable == 0} {
            set line "ds_axi_ruser; 0"
        }
    }

    append b_content "$line \n"
}

close $port_con

set new_handle [open "$param_txt_path" w]
puts -nonewline $new_handle $a_content
close $new_handle

set new_port_handle [open "$port_txt_path" w]
puts -nonewline $new_port_handle $b_content
close $new_port_handle
puts "protocol_us is $protocol_us; protocol_ds is $protocol_ds"
puts "user_signal_enable is $user_signal_enable"

    return 1
    
}

