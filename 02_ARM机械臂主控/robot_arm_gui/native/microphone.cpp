// aarch64-linux-gnu-g++ -O2 -std=c++17 -Wall -Wextra microphone.cpp -o microphone_capture
// Input-only ES8388 FIFO at 0xa0000200; never writes a motor register.
#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <unistd.h>

static volatile sig_atomic_t stopped=0;
static void stop_signal(int){stopped=1;}
static void barrier(){
#ifdef __aarch64__
  asm volatile("dsb sy" ::: "memory");
#else
  __sync_synchronize();
#endif
}
struct Device {
  int fd=-1,lock=-1;void* mapped=MAP_FAILED;volatile uint32_t* regs=nullptr;bool active=false;
  Device(bool capture){
    if(capture){
      lock=open("/run/f3p-microphone.lock",O_CREAT|O_RDWR|O_CLOEXEC,0600);
      if(lock<0||flock(lock,LOCK_EX|LOCK_NB))throw std::runtime_error("microphone already in use");
    }
    fd=open("/dev/mem",O_RDWR|O_SYNC|O_CLOEXEC);
    if(fd<0)throw std::runtime_error("/dev/mem access failed");
    mapped=mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0xa0000000);
    if(mapped==MAP_FAILED)throw std::runtime_error("microphone MMIO mapping failed");
    regs=reinterpret_cast<volatile uint32_t*>(mapped);
    if(read(0)!=0x52414331||read(0x200)!=0x41554431||read(0x22c)!=0x00010000){
      munmap(mapped,4096);mapped=MAP_FAILED;
      throw std::runtime_error("board microphone capture firmware is not installed");
    }
    if(read(0x21c)!=50000000||read(0x220)!=3072)throw std::runtime_error("unexpected audio clock ratio");
  }
  uint32_t read(unsigned off){if(off&3||off>0xffc)throw std::runtime_error("invalid MMIO read");barrier();return regs[off/4];}
  void write(unsigned off,uint32_t value){
    if(off!=0x204&&off!=0x20c&&off!=0x214)throw std::runtime_error("write outside microphone registers refused");
    regs[off/4]=value;barrier();
  }
  void start(unsigned gain){
    write(0x204,0);usleep(2000);write(0x20c,gain);write(0x204,2);usleep(20000);
    for(int i=0;i<1500&&!stopped;i++){
      uint32_t status=read(0x208);
      if(status&(1u<<17))throw std::runtime_error("ES8388 I2C NACK; inspect codec wiring/firmware");
      if(status&(1u<<16)){write(0x204,1);active=true;return;}
      usleep(1000);
    }
    throw std::runtime_error("ES8388 configuration timeout");
  }
  ~Device(){if(mapped!=MAP_FAILED){if(active)write(0x204,0);munmap(mapped,4096);}if(fd>=0)close(fd);if(lock>=0)close(lock);}
};

// Exact source/output ratio: (50MHz / 3072) / 16kHz = 3125 / 3072.
// A 32-tap fractional-delay low-pass avoids merely relabeling the sample rate.
struct Resampler {
  static constexpr int phases=3072,taps=32,left=15,right=16;
  std::vector<std::array<float,taps>> weights;
  std::vector<int16_t> input;uint64_t origin=0,next=0;
  Resampler():weights(phases){
    constexpr double pi=3.14159265358979323846,cutoff=.44;
    for(int phase=0;phase<phases;phase++){
      double frac=double(phase)/phases,total=0;
      for(int j=0;j<taps;j++){
        double x=j-left-frac;
        double sinc=std::abs(x)<1e-12?2*cutoff:std::sin(2*pi*cutoff*x)/(pi*x);
        double window=.5+.5*std::cos(pi*x/17.0);
        weights[phase][j]=float(sinc*window);total+=sinc*window;
      }
      for(float& v:weights[phase])v=float(v/total);
    }
    input.reserve(8192);
  }
  template<class Output>void push(int16_t value,Output output){
    input.push_back(value);
    while(next/phases+right<origin+input.size()){
      int64_t center=next/phases;int phase=next%phases;double sum=0;
      for(int j=0;j<taps;j++){
        int64_t index=center+j-left;
        if(index>=0&&uint64_t(index)>=origin)sum+=input[size_t(index-origin)]*weights[phase][j];
      }
      output(int16_t(std::max(-32768.0,std::min(32767.0,std::round(sum)))));next+=3125;
    }
    int64_t discard=int64_t(next/phases)-left-int64_t(origin);
    if(discard>4096){input.erase(input.begin(),input.begin()+discard);origin+=discard;}
  }
};
static void write_all(const void* data,size_t size){
  auto* bytes=static_cast<const unsigned char*>(data);
  while(size&&!stopped){ssize_t n=::write(STDOUT_FILENO,bytes,size);
    if(n<0){if(errno==EINTR)continue;throw std::runtime_error("audio output pipe closed");}
    bytes+=n;size-=size_t(n);
  }
}
static void le16(std::ostream& s,uint16_t n){s.put(char(n));s.put(char(n>>8));}
static void le32(std::ostream& s,uint32_t n){le16(s,n&65535);le16(s,n>>16);}
static void wav(const std::string& path,const std::vector<int16_t>& samples){
  std::ofstream f(path,std::ios::binary);if(!f)throw std::runtime_error("cannot open recording output");
  f.write("RIFF",4);le32(f,36+samples.size()*2);f.write("WAVEfmt ",8);le32(f,16);le16(f,1);le16(f,1);
  le32(f,16000);le32(f,32000);le16(f,2);le16(f,16);f.write("data",4);le32(f,samples.size()*2);
  for(int16_t n:samples)le16(f,uint16_t(n));
  if(!f)throw std::runtime_error("recording write failed");
}
int main(int argc,char** argv){
  try{
    std::signal(SIGTERM,stop_signal);std::signal(SIGINT,stop_signal);std::signal(SIGPIPE,stop_signal);
    std::string mode=argc>1?argv[1]:"";unsigned gain=6;
    for(int i=2;i+1<argc;i++)if(std::string(argv[i])=="--gain"){
      char* end=nullptr;long n=strtol(argv[i+1],&end,10);if(*end||n<0||n>8)throw std::runtime_error("gain must be 0..8");gain=unsigned(n);
    }
    if(mode=="--resample"&&argc==4){
      std::ifstream source(argv[2],std::ios::binary);if(!source)throw std::runtime_error("cannot open raw input");
      Resampler converter;std::vector<int16_t> samples;char bytes[2];
      while(source.read(bytes,2))converter.push(int16_t(uint16_t(uint8_t(bytes[0]))|(uint16_t(uint8_t(bytes[1]))<<8)),[&](int16_t s){samples.push_back(s);});
      if(source.gcount())throw std::runtime_error("odd PCM input size");
      wav(argv[3],samples);return 0;
    }
    bool stream=mode=="--stream",record=mode=="--record";
    if(!stream&&!record&&mode!="--probe")throw std::runtime_error("use --probe, --stream [--gain 0..8], --record seconds output.wav [--gain 0..8]");
    double seconds=0;
    if(record){
      if(argc<4)throw std::runtime_error("record requires duration and output path");
      char* end=nullptr;seconds=strtod(argv[2],&end);if(*end||!std::isfinite(seconds)||seconds<=0||seconds>120)throw std::runtime_error("record duration must be 0..120 seconds");
    }
    Device device(stream||record);
    if(mode=="--probe"){
      std::cout<<"{\"source\":\"board_mic_es8388\",\"status\":"<<device.read(0x208)<<",\"source_rate_num\":50000000,\"source_rate_den\":3072,\"output_rate\":16000}"<<std::endl;return 0;
    }
    device.start(gain);
    std::cerr<<"{\"source\":\"board_mic_es8388\",\"sample_rate\":16000,\"gain_db\":"<<gain*3<<"}"<<std::endl;
    Resampler converter;std::vector<int16_t> samples,block;block.reserve(320);
    size_t out_count=0,wanted=record?size_t(seconds*16000):0;uint32_t pop=0;
    auto output=[&](int16_t s){
      if(record&&out_count<wanted)samples.push_back(s);
      else if(stream){block.push_back(s);if(block.size()==320){write_all(block.data(),block.size()*2);block.clear();}}
      ++out_count;
    };
    unsigned empty_waits=0;
    while(!stopped&&(!record||out_count<wanted)){
      uint32_t status=device.read(0x208);
      if(status&(1u<<18))throw std::runtime_error("microphone FIFO overflow; recording discarded");
      if(!(status&(1u<<16))||(status&(1u<<17)))throw std::runtime_error("microphone codec is not ready");
      unsigned count=std::min(status&65535u,512u);
      if(!count){if(++empty_waits>3000)throw std::runtime_error("no microphone sample clock");usleep(1000);continue;}
      empty_waits=0;
      for(unsigned i=0;i<count&&!stopped;i++){
        int16_t sample=int16_t(device.read(0x210)&65535u);
        device.write(0x214,++pop);
        unsigned attempts=0;while(device.read(0x218)!=pop){if(++attempts>5000)throw std::runtime_error("microphone FIFO acknowledgement timeout");}
        converter.push(sample,output);
        if(record&&out_count>=wanted)break;
      }
    }
    if(record){wav(argv[3],samples);std::cout<<"{\"samples\":"<<samples.size()<<",\"sample_rate\":16000}"<<std::endl;}
    return 0;
  }catch(const std::exception& e){std::cerr<<"microphone: "<<e.what()<<std::endl;return 2;}
}
