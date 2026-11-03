#define _GNU_SOURCE
#include "parking_core.h"
#include "mission_core.h"
#include "mission_protocol.h"
#include "jy61p_linux.h"
#include "jy61p_protocol.h"
#include "console_wiring.h"
#include "console_gripper.h"
#include "board_linux.h"
#include "board.h"
#include "oled_linux.h"
#include "oled_display.h"
void Oled_GetGlyph(char,uint8_t[5]);
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <poll.h>
#include <sched.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/un.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#define PARK_ENDPOINT "/run/f3p-drive174-grasp.sock"
#define GRIP_ENDPOINT "/run/f3p-key-console.sock"
static unsigned route_mode=2;
static const char *status_path(void){return "/run/f3p-drive174-grasp-status.json";}
static const char *status_tmp(void){return "/run/f3p-drive174-grasp-status.tmp";}
typedef struct {ParkingState state;ConsoleView grip;uint32_t remote_active,lease_remaining_ms,complete;} ParkingPacket;
static volatile sig_atomic_t done;
static uint64_t service_generation;
static void stop_signal(int n){(void)n;done=1;}
static uint64_t ns(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static void pause_us(unsigned us){struct timespec t={0,(long)us*1000};nanosleep(&t,NULL);}
static int valid(const ParkingState *s){
 if(s->magic!=PARKING_MAGIC||s->phase>PARK_FAULT||s->step>=Parking_StepCount(s)||s->page>1||s->fault>23||!Parking_ConfigValid(&s->config))return 0;
 if(!isfinite(s->yaw_deg)||!isfinite(s->yaw_unwrapped)||!isfinite(s->gyro_z_dps))return 0;
 for(unsigned i=0;i<2;i++){if(!isfinite(s->pwm[i])||fabsf(s->pwm[i])>800||!isfinite(s->step_mm[i])||fabs(s->step_mm[i])>1e10)return 0;}
 return 1;
}
static void atomic_text(const char *path,const char *tmp,const char *text,size_t n,int persist){
 int fd=open(tmp,O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW|O_CLOEXEC,0644);if(fd<0)return;
 ssize_t z=write(fd,text,n);if(persist)(void)fsync(fd);close(fd);
 if(z==(ssize_t)n){if(!rename(tmp,path)&&persist){int d=open("/var/lib/f3p-drive174-grasp",O_RDONLY|O_DIRECTORY|O_CLOEXEC);if(d>=0){(void)fsync(d);close(d);}}}
}
static void status(const ParkingPacket *p,int ready,int lost){
 const ParkingState *s=&p->state;const ConsoleView *v=&p->grip;static unsigned saved_run,saved_complete,saved_phase;char text[1800];
 int n=snprintf(text,sizeof(text),"{\"version\":\"shelf-package-car-v1\",\"phase\":\"%s\",\"fault\":%u,\"grip_fault\":%u,\"run_id\":%u,\"complete\":%s,\"armed\":%s,\"target\":%.3f,\"target_unit\":\"%s\",\"route_mode\":%u,\"turn_pwm\":%u,\"counts_lr\":[%" PRId64 ",%" PRId64 "],\"mm_lr\":[%.3f,%.3f],\"pwm_lr\":[%.1f,%.1f],\"elapsed_ms\":%u,\"oled_ready\":%s,\"imu_ready\":%s,\"data_stale\":%s,\"grip_owner\":%s,\"grip_pulse_us\":%u,\"grip_phase\":%u,\"distance_calibrated\":%s,\"wheel_start\":\"touch_start_KEY2_trim_up_KEY3_trim_down\",\"touch_control_version\":1,\"oled_optional\":true,\"encoder_sign_check\":true,\"wiring\":\"handoff_new_front\",\"grip_open_wait_ms\":%u,\"right_trim_percent\":%.3f,\"yaw_progress_deg\":%.3f,\"gyro_z_dps\":%.3f}\n",
 Parking_Phase(s->phase),s->fault,v->fault,s->run_id,p->complete?"true":"false",p->remote_active?"true":"false",Parking_Target(s),Parking_IsTurn(s)?"deg":"mm",s->config.route_mode,s->config.turn_pwm,s->step_counts[0],s->step_counts[1],s->step_mm[0],s->step_mm[1],(double)s->pwm[0],(double)s->pwm[1],s->total_ms,ready?"true":"false",s->imu_ready?"true":"false",lost?"true":"false",v->remote_active?"true":"false",v->grip_pulse,v->grip_phase,s->config.calibrated?"true":"false",GRIP_OPEN_HOLD_TICKS*10U,s->config.right_trim_percent,s->yaw_progress,s->gyro_z_dps);
 if(n<=0||(size_t)n>=sizeof(text))return;
 atomic_text(status_path(),status_tmp(),text,(size_t)n,0);
 /* Non-real-time display worker persists trim only while wheels are idle. */
 static double saved_trim=999.;
 if(s->config.trim_keys_enabled&&s->phase!=PARK_RUN&&s->phase!=PARK_SETTLE&&s->config.right_trim_percent!=saved_trim){
  char value[32];int len=snprintf(value,sizeof(value),"%.2f\n",s->config.right_trim_percent);
  mkdir("/var/lib/f3p-drive174-grasp",0755);
  atomic_text("/var/lib/f3p-drive174-grasp/right-trim-percent.txt","/var/lib/f3p-drive174-grasp/right-trim-percent.tmp",value,(size_t)len,1);
  FILE *check=fopen("/var/lib/f3p-drive174-grasp/right-trim-percent.txt","rb");double readback;
  if(check){if(fscanf(check,"%lf",&readback)==1&&readback==s->config.right_trim_percent)saved_trim=readback;fclose(check);}
 }
 if(s->run_id&&(s->phase==PARK_DONE||s->phase==PARK_STOP||s->phase==PARK_FAULT)&&(saved_run!=s->run_id||saved_complete!=p->complete||saved_phase!=s->phase)){
  mkdir("/var/lib/f3p-drive174-grasp",0755);atomic_text("/var/lib/f3p-drive174-grasp/last-run.json","/var/lib/f3p-drive174-grasp/last-run.tmp",text,(size_t)n,1);saved_run=s->run_id;saved_complete=p->complete;saved_phase=s->phase;
 }
 n=snprintf(text,sizeof(text),"{\"version\":\"shelf-package-car-v1\",\"touch_control_version\":1,\"mode\":2,\"running\":0,\"fault\":%u,\"oled_ready\":%s,\"oled_optional\":true,\"control_link_lost\":%s,\"remote_active\":%s,\"grip_phase\":%u,\"grip_command_us\":%u,\"grip_remaining_ms\":%u}\n",v->fault,ready?"true":"false",lost?"true":"false",v->remote_active?"true":"false",v->grip_phase,v->grip_pulse,v->grip_remaining_ms);
 if(n>0&&(size_t)n<sizeof(text))atomic_text("/run/f3p-key-console-status.json","/run/f3p-key-console-status.tmp",text,(size_t)n,0);
}
static void mission_frame(const ParkingPacket *p,int lost,uint8_t frame[1024],char lines[4][22]){
 memset(frame,0,1024);memset(lines,0,88);const ParkingState *s=&p->state;
 snprintf(lines[0],22,"%s %s F:%u",s->config.route_mode==3?"SHELF":"174",lost?"LINK LOST":p->complete?"COMPLETE":s->phase==PARK_DONE?"GRASP":s->phase==PARK_READY?(p->remote_active?"ARMED":"WAIT GUI"):Parking_Phase(s->phase),s->fault?s->fault:p->grip.fault);
 if(s->page){snprintf(lines[1],22,"L:%lld R:%lld",(long long)s->step_counts[0],(long long)s->step_counts[1]);snprintf(lines[2],22,"PWM:%d/%d",(int)s->pwm[0],(int)s->pwm[1]);}
 else{snprintf(lines[1],22,"%s:%.0f/%.0f",Parking_IsTurn(s)?"DEG":"MM",Parking_IsTurn(s)?s->yaw_progress:.5*(s->step_mm[0]+s->step_mm[1]),Parking_Target(s));snprintf(lines[2],22,"L:%lld R:%lld",(long long)s->step_counts[0],(long long)s->step_counts[1]);}
 snprintf(lines[3],22,"1RST 2GO 3PG 4STOP");
 for(unsigned r=0;r<4;r++)for(unsigned c=0;c<21&&lines[r][c];c++){uint8_t g[5];Oled_GetGlyph(lines[r][c],g);for(unsigned x=0;x<5;x++)for(unsigned y=0;y<8;y++)if(g[x]&(1U<<y))for(unsigned k=0;k<2;k++){unsigned py=r*16+y*2+k;frame[(py/8)*128+c*6+x]|=(uint8_t)(1U<<(py%8));}}
}
static void health(int fd,int ready){ConsoleHealth h={HEALTH_MAGIC,(uint32_t)ready};ssize_t n=write(fd,&h,sizeof(h));(void)n;}
static int display_worker(int input,int output){
 (void)setpriority(PRIO_PROCESS,0,10);if(Oled_Open(1))return 1;
 ParkingPacket p={0};unsigned char buffer[sizeof(p)];size_t used=0;int valid_packet=0,eof=0,ready=0;uint64_t last_rx=ns(),last_draw=0,next_retry=0,last_health=0;uint8_t frame[1024];char lines[4][22];
 while(!done&&!eof){
  struct pollfd pf={input,POLLIN,0};int pr=poll(&pf,1,20);if(pr<0&&errno!=EINTR)break;
  if(pr>0&&(pf.revents&(POLLIN|POLLHUP|POLLERR)))for(unsigned i=0;i<32;i++){
   ssize_t n=read(input,buffer+used,sizeof(buffer)-used);if(!n){eof=1;break;}
   if(n<0){if(errno==EINTR)continue;if(errno!=EAGAIN)eof=1;break;}
   used+=(size_t)n;if(used==sizeof(buffer)){ParkingPacket next;memcpy(&next,buffer,sizeof(next));used=0;if(valid(&next.state)&&next.remote_active<=1){p=next;valid_packet=1;last_rx=ns();}}
  }
  uint64_t now=ns();int lost=!valid_packet||now-last_rx>500000000ULL;
  if(now>=next_retry&&!ready){ready=Oled_InitPanel()==0;if(!ready)next_retry=ns()+2000000000ULL;}
  if(ready&&now-last_draw>=200000000ULL){mission_frame(&p,lost,frame,lines);ready=Oled_SendFrame(frame)==0;last_draw=ns();if(!ready)next_retry=last_draw+2000000000ULL;}
  now=ns();if(now-last_health>=100000000ULL){int ok=ready&&!lost;health(output,ok);last_health=now;}
 }
 p.state.pwm[0]=p.state.pwm[1]=0;if(p.state.phase==PARK_RUN||p.state.phase==PARK_SETTLE)p.state.phase=PARK_STOP;
 health(output,0);Oled_Close();return 0;
}
static int load_config(ParkingConfig *c){
 DistanceConfig d;Distance_DefaultConfig(&d);const char *path=getenv("F3P_DISTANCE_PROFILE");if(!path)path="/var/lib/f3p-distance/calibration.json";
 FILE *f=fopen(path,"rb");if(!f)return -1;char text[512];size_t n=fread(text,1,sizeof(text)-1,f);int bad=ferror(f)||!feof(f);fclose(f);text[n]=0;int used=0;
 int fields=sscanf(text,"{\"schema\":1,\"left_mm_per_count\":%lf,\"right_mm_per_count\":%lf,\"target_mm\":%lf,\"calibrated\":%u}%n",&d.mm_per_count[0],&d.mm_per_count[1],&d.target_mm,&d.calibrated,&used);
 if(bad||fields!=4||used<=0||strspn(text+used," \t\r\n")!=strlen(text+used)||!Distance_ConfigValid(&d))return -1;
 Parking_DefaultConfig(c,&d);path=getenv("F3P_SHELF_TURN_PROFILE");if(!path)path="/var/lib/f3p-shelf/car-turn.json";f=fopen(path,"rb");if(!f)return -1;
 n=fread(text,1,sizeof(text)-1,f);bad=ferror(f)||!feof(f);fclose(f);text[n]=0;used=0;
 fields=sscanf(text,"{\"schema\":1,\"turn_pwm\":%u,\"left_yaw_sign\":%d}%n",&c->turn_pwm,&c->yaw_sign,&used);
 if(bad||fields!=2||used<=0||strspn(text+used," \t\r\n")!=strlen(text+used))return -1;
 c->trim_keys_enabled=1;
 f=fopen("/var/lib/f3p-drive174-grasp/right-trim-percent.txt","rb");
 if(f){char extra;int count=fscanf(f,"%lf %c",&c->right_trim_percent,&extra);bad=ferror(f);fclose(f);if(bad||count!=1)return -1;}
 else if(errno!=ENOENT)return -1;
 return Parking_ConfigValid(c)?0:-1;
}
static int input_read(ConsoleInput *in,uint32_t *seq){
 if(Hardware_Snapshot(seq))return -1;
 uint32_t raw[2]={Board_Count(0),Board_Count(1)};Console_MapEncoderCounts(raw,in->counts);in->keys=Board_Keys();in->motor_status=Hardware_Status();in->grip_status=Gripper_Status();in->grip_active_us=Gripper_ActiveUs();in->arm_idle=Hardware_ArmIdle();in->motor_max_pwm=Hardware_MaxMotorPwm();return 0;
}
static int publish(int fd,const MissionState *s,uint64_t now,int ready){
 ParkingPacket p={.state=s->drive,.remote_active=s->owner[0]!=0,.lease_remaining_ms=(uint32_t)(s->deadline_ms>now?s->deadline_ms-now:0),.complete=s->complete};Console_View(&s->grip,&p.grip);
 /* Parent owns telemetry even if the optional OLED process is absent. */
 status(&p,ready,0);
 if(fd<0)return 0;
 ssize_t n=write(fd,&p,sizeof(p));return n==(ssize_t)sizeof(p)||(n<0&&(errno==EAGAIN||errno==EINTR))?0:-1;
}
static int socket_open(const char *endpoint){
 int fd=socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK|SOCK_CLOEXEC,0);if(fd<0)return -1;
 struct sockaddr_un address={.sun_family=AF_UNIX};strcpy(address.sun_path,endpoint);unlink(endpoint);mode_t old=umask(0077);int rc=bind(fd,(void*)&address,sizeof(address));umask(old);if(rc){close(fd);return -1;}return fd;
}
static void socket_poll(int fd,MissionState *s,const ConsoleInput *in,uint64_t now,int grip){
 for(unsigned i=0;i<8;i++){
  char request[256],token[65],cmd[17],reply[1200];struct sockaddr_un peer={0};socklen_t length=sizeof(peer);ssize_t n=recvfrom(fd,request,sizeof(request)-1,MSG_TRUNC,(void*)&peer,&length);if(n<0)return;
  if(n>=(ssize_t)sizeof(request)||memchr(request,0,(size_t)n))continue;
  request[n]=0;
  int head=0,ok=sscanf(request,"%64s %16s%n",token,cmd,&head)==2;char *args=request+head;
  if(ok&&!grip&&(!strcmp(cmd,"shelf")||!strcmp(cmd,"status")||!strcmp(cmd,"stop")||!strcmp(cmd,"reset"))){
   int size=Mission_Protocol(s,in,now,service_generation,request,(size_t)n,reply,sizeof(reply));
   if(size>0)(void)sendto(fd,reply,(size_t)size,MSG_DONTWAIT|MSG_NOSIGNAL,(void*)&peer,length);
   continue;
  }
  if(ok){
   ok=strspn(args," \t\r\n")==strlen(args);
   if(!grip&&s->shelf_mode)ok=0; /* New owner must use generation-bound requests. */
   if(ok)ok=(grip?Mission_GripCommand(s,in,token,cmd,now):Mission_Command(s,in,token,cmd,now))==0;
  }
  int size=grip?snprintf(reply,sizeof(reply),"%s %u %u %u",ok?"OK":"ERROR",s->grip.fault,s->grip_lease.phase,s->grip_lease.settled):snprintf(reply,sizeof(reply),"{\"ok\":%s,\"phase\":\"%s\",\"fault\":%u,\"grip_fault\":%u,\"armed\":%s,\"complete\":%s,\"run_id\":%u,\"generation\":\"%" PRIu64 "\",\"shelf_mode\":%s,\"shelf_started\":%s,\"shelf_command_id\":%u,\"shelf_arm_lock\":%s,\"odo_counts_lr\":[%" PRId64 ",%" PRId64 "],\"odo_mm_lr\":[%.4f,%.4f],\"measured_ms\":%" PRIu64 ",\"imu_ready\":%s,\"gripper_active\":%s}",ok?"true":"false",Parking_Phase(s->drive.phase),s->drive.fault,s->grip.fault,s->owner[0]?"true":"false",s->complete?"true":"false",s->drive.run_id,service_generation,s->shelf_mode?"true":"false",s->shelf_started?"true":"false",s->shelf_command_id,s->shelf_arm_lock?"true":"false",s->shelf_net_counts[0],s->shelf_net_counts[1],s->shelf_net_counts[0]*s->drive.config.mm_per_count[0],s->shelf_net_counts[1]*s->drive.config.mm_per_count[1],s->shelf_measured_ms,s->drive.imu_ready?"true":"false",(in->grip_status&31)?"true":"false");
  if(size>0&&(size_t)size<sizeof(reply))(void)sendto(fd,reply,(size_t)size,MSG_DONTWAIT|MSG_NOSIGNAL,(void*)&peer,length);
 }
}
static void finish_child(pid_t child){
 int result;for(unsigned i=0;i<100;i++){pid_t p=waitpid(child,&result,WNOHANG);if(p==child||p<0)return;if(i==50)(void)kill(child,SIGTERM);pause_us(10000);}kill(child,SIGKILL);(void)waitpid(child,&result,0);
}
int Mission_Run(unsigned smoke_seconds){
 service_generation=ns();
 ParkingConfig cfg;if(load_config(&cfg)){fputs("Invalid parking/distance profile; no outputs enabled.\n",stderr);return 2;}
 cfg.route_mode=route_mode;
 int tx[2],rx[2];if(pipe2(tx,O_NONBLOCK|O_CLOEXEC)||pipe2(rx,O_NONBLOCK|O_CLOEXEC))return 1;
 signal(SIGINT,stop_signal);signal(SIGTERM,stop_signal);signal(SIGPIPE,SIG_IGN);pid_t child=fork();if(child<0)return 1;
 if(!child){close(tx[1]);close(rx[0]);int result=display_worker(tx[0],rx[1]);close(tx[0]);close(rx[1]);_exit(result);}
 close(tx[0]);close(rx[1]);int rc=1,motor=0,grip=0,imu_open=0,socket_fd=-1,grip_fd=-1;
 if(Hardware_Open(1)){goto cleanup;}
 motor=1;Hardware_Disarm();
 if(Gripper_Open(1)){goto cleanup;}
 grip=1;if(Gripper_Stop()||Gripper_Limits(GRIP_MIN_US,GRIP_MAX_US)){goto cleanup;}
 Hardware_ClearStopped();
 if(ImuHardware_Open(1)){goto cleanup;}
 imu_open=1;if(ImuHardware_Configure(9600)){goto cleanup;}
 ImuHardware_Flush();
 if(!smoke_seconds){socket_fd=socket_open(PARK_ENDPOINT);grip_fd=socket_open(GRIP_ENDPOINT);if(socket_fd<0||grip_fd<0)goto cleanup;}
 if(mlockall(MCL_CURRENT|MCL_FUTURE)){perror("parking mlockall");goto cleanup;}
 struct sched_param priority={.sched_priority=30};if(sched_setscheduler(0,SCHED_FIFO,&priority)){perror("parking FIFO");goto cleanup;}
 ConsoleInput in={0};uint32_t seq,last=0;MissionState mission;ImuState imu;Imu_Init(&imu);
 if(input_read(&in,&last)){goto cleanup;}
 Mission_Init(&mission,&in,&cfg);ParkingState *state=&mission.drive;
 int display_connected=1;
 if(publish(tx[1],&mission,ns()/1000000,0))display_connected=0;
 uint64_t started=ns(),last_sample=started,last_pub=0,last_health=0;unsigned char hb[sizeof(ConsoleHealth)];size_t hu=0;int ready=0;rc=0;
 while(!done){
  uint64_t now=ns();
  for(unsigned i=0;display_connected&&i<16;i++){
   ssize_t n=read(rx[0],hb+hu,sizeof(hb)-hu);if(!n){display_connected=ready=0;break;}
   if(n<0){if(errno==EINTR)continue;if(errno!=EAGAIN)display_connected=ready=0;break;}
   hu+=(size_t)n;if(hu==sizeof(hb)){ConsoleHealth h;memcpy(&h,hb,sizeof(h));hu=0;if(h.magic==HEALTH_MAGIC&&h.ready<=1){ready=h.ready;last_health=now;}}
  }
  if(done)break;
  if(ImuHardware_Status()&28){ImuHardware_Flush();Imu_Invalidate(&imu);}
  uint8_t bytes[128];int n=ImuHardware_Read(bytes,sizeof(bytes));for(int i=0;i<n;i++)(void)Imu_Feed(&imu,bytes[i],now/1000000);
  int fresh=Imu_Fresh(&imu,1,now/1000000,300)&&Imu_Fresh(&imu,2,now/1000000,300);Parking_ImuSample(state,fresh,imu.angle_deg[2],imu.gyro_dps[2]);
  in.oled_ready=display_connected&&ready&&last_health&&now-last_health<=750000000ULL;
  if(input_read(&in,&seq)){Hardware_Disarm();Gripper_RequestStop();rc=1;break;}
  if(seq!=last){
   uint32_t d=seq-last;last=seq;last_sample=now;
   if(d!=1){if(state->phase==PARK_RUN||state->phase==PARK_SETTLE||mission.grip_lease.owner[0])Mission_Fault(&mission,CF_SAMPLE);state->counts[0]=in.counts[0];state->counts[1]=in.counts[1];}
   if(smoke_seconds)in.keys=0;else{socket_poll(socket_fd,&mission,&in,now/1000000,0);socket_poll(grip_fd,&mission,&in,now/1000000,1);}
   MissionOutput out;Mission_Tick(&mission,&in,&out,now/1000000);
   if(smoke_seconds){out.drive.enable=0;out.drive.pwm[0]=out.drive.pwm[1]=0;out.grip.grip_action=GA_STOP;out.grip.grip_heartbeat=0;}
   int hw[2];Console_MapMotorCommands(out.drive.pwm,hw);Board_SetMotor(0,hw[0]);Board_SetMotor(1,hw[1]);Hardware_Flush(out.drive.enable&&!state->fault);
   if(out.grip.grip_action==GA_STOP)Gripper_RequestStop();
   if(out.drive.clear_stopped||out.grip.clear_stopped){Hardware_ClearStopped();if(Gripper_ClearStopped())Mission_Fault(&mission,CF_GRIP);}
   if(out.grip.grip_action==GA_COMMAND&&Gripper_QueuePulse(out.grip.grip_pulse)){Hardware_Disarm();Gripper_RequestStop();Mission_Fault(&mission,CF_GRIP);}
   if(out.grip.grip_heartbeat)Gripper_Heartbeat();
  }else if(now-last_sample>30000000ULL){Hardware_Disarm();Gripper_RequestStop();Mission_Fault(&mission,CF_SAMPLE);last_sample=now;}
  if(now-last_pub>=100000000ULL){if(publish(display_connected?tx[1]:-1,&mission,now/1000000,in.oled_ready))display_connected=ready=0;last_pub=now;}
  if(smoke_seconds&&now-started>=(uint64_t)smoke_seconds*1000000000ULL){break;}
  pause_us(500);
 }
 Hardware_Disarm();Gripper_RequestStop();Parking_Stop(state);Console_Fault(&mission.grip,0);(void)publish(display_connected?tx[1]:-1,&mission,ns()/1000000,in.oled_ready);
cleanup:
 if(socket_fd>=0){close(socket_fd);unlink(PARK_ENDPOINT);}if(grip_fd>=0){close(grip_fd);unlink(GRIP_ENDPOINT);}if(imu_open)ImuHardware_Close();if(grip){(void)Gripper_Stop();Gripper_Close();}if(motor)Hardware_Close();close(tx[1]);close(rx[0]);finish_child(child);return rc;
}
int Mission_Render(const char *path){
 DistanceConfig d;Distance_DefaultConfig(&d);ParkingConfig cfg;Parking_DefaultConfig(&cfg,&d);ConsoleInput in={0};MissionState s;Mission_Init(&s,&in,&cfg);ParkingPacket p={.state=s.drive};Console_View(&s.grip,&p.grip);uint8_t frame[1024];char lines[4][22];mission_frame(&p,0,frame,lines);for(unsigned i=0;i<4;i++)puts(lines[i]);return Oled_WritePbm(path,frame)?1:0;
}
