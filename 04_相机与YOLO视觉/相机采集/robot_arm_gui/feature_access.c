#include <stdint.h>
#include <stddef.h>
#include <string.h>
#ifdef __aarch64__
#include <arm_neon.h>
#endif
/* Used only for aligned reserved DDR. Never use SIMD loads for camera CSRs. */
static inline void load_ddr128(const volatile uint32_t *src,uint64_t *low,uint64_t *high) {
#ifdef __aarch64__
 uint64x2_t value;
 __asm__ __volatile__("ldr %q0, [%1]" : "=w"(value) : "r"(src) : "memory");
 *low=vgetq_lane_u64(value,0);*high=vgetq_lane_u64(value,1);
#else
 *low=*(volatile const uint64_t *)src;*high=*((volatile const uint64_t *)src+1);
#endif
}
/* Camera CSR accesses remain 32-bit. Reserved DDR uses proven aligned 64-bit reads where possible. */
int f3p_unpack_masks(const uint32_t *base,uint8_t *planes,int width,int height,int stride,int mask_offset,int32_t *bounds) {
 if(!base||!planes||!bounds||((uintptr_t)base&3)||width<=0||width>480||(width&7)||height<=0||height>270||stride<width||mask_offset<width||mask_offset+width/8>stride)return -1;
 volatile const uint32_t *src=base;size_t area=(size_t)width*height;
 int wide=!((uintptr_t)base&7)&&!(stride&1)&&!(mask_offset&1)&&!(width&15);int quad=!((uintptr_t)base&15)&&!(stride&3)&&!(mask_offset&3)&&!(width&31);int group=quad?32:wide?16:8;
 for(int c=0;c<4;c++){bounds[c*4]=width;bounds[c*4+1]=height;bounds[c*4+2]=0;bounds[c*4+3]=0;}
 for(int y=0;y<height;y++)for(int x=0;x<width;x+=group){
  size_t position=(size_t)y*stride+mask_offset+x/8;
  uint64_t halves64[2]={0,0};
  if(quad)load_ddr128(src+position,&halves64[0],&halves64[1]);
  else halves64[0]=wide?*(volatile const uint64_t *)(src+position):src[position];
  uint64_t pattern=wide?UINT64_C(0x1111111111111111):UINT64_C(0x11111111);
  for(int c=0;c<4;c++)if((halves64[0]&(pattern<<c))||(quad&&(halves64[1]&(pattern<<c)))){
   if(x<bounds[c*4])bounds[c*4]=x;
   if(y<bounds[c*4+1])bounds[c*4+1]=y;
   if(x+group>bounds[c*4+2])bounds[c*4+2]=x+group;
   if(y+1>bounds[c*4+3])bounds[c*4+3]=y+1;
  }
#ifdef __aarch64__
  if(quad){
   /* DDR has already been read exactly once above. Unzip the low/high
    * nibble of each byte into32 consecutive pixels, then materialize
    * the four original binary planes using full-width SIMD. */
   uint64x2_t packed=vcombine_u64(vcreate_u64(halves64[0]),vcreate_u64(halves64[1]));
   uint8x16_t bytes=vreinterpretq_u8_u64(packed);
   uint8x16x2_t nibbles=vzipq_u8(vandq_u8(bytes,vdupq_n_u8(15)),vshrq_n_u8(bytes,4));
   for(int c=0;c<4;c++){
    uint8x16_t bit=vdupq_n_u8((uint8_t)(1u<<c)),zero=vdupq_n_u8(0);
    uint8_t *dst=planes+c*area+(size_t)y*width+x;
    vst1q_u8(dst,vcgtq_u8(vandq_u8(nibbles.val[0],bit),zero));
    vst1q_u8(dst+16,vcgtq_u8(vandq_u8(nibbles.val[1],bit),zero));
   }
   continue;
  }
#endif
  for(int half=0;half<(quad?4:wide?2:1);half++){
   uint32_t word=(uint32_t)(halves64[half/2]>>((half%2)*32));int start=x+half*8;
#ifdef __aarch64__
   const int32_t shifts0[4]={0,-4,-8,-12},shifts1[4]={-16,-20,-24,-28};
   uint32x4_t value=vdupq_n_u32(word);
   uint16x8_t halves=vcombine_u16(vmovn_u32(vshlq_u32(value,vld1q_s32(shifts0))),vmovn_u32(vshlq_u32(value,vld1q_s32(shifts1))));
   uint8x8_t nib=vmovn_u16(halves);
   for(int c=0;c<4;c++)vst1_u8(planes+c*area+(size_t)y*width+start,vcgt_u8(vand_u8(nib,vdup_n_u8((uint8_t)(1u<<c))),vdup_n_u8(0)));
#else
   for(int i=0;i<8;i++)for(int c=0;c<4;c++)planes[c*area+(size_t)y*width+start+i]=((word>>(4*i+c))&1)?255:0;
#endif
  }
 }
 return 0;
}
int f3p_confidence_stats(const uint32_t *base,int stride,int x,int y,int width,int height,const uint8_t *object,int object_stride,const uint8_t *mask,int mask_stride,const float *costs,const uint8_t *order,double *out) {
 if(!base||!object||!mask||!costs||!order||!out||((uintptr_t)base&3)||stride<480||x<0||y<0||width<=0||height<=0||x+width>480||y+height>270||object_stride<width||mask_stride<width)return -1;
 uint32_t hue[180],sat[256];memset(hue,0,sizeof(hue));memset(sat,0,sizeof(sat));uint32_t count=0;
 volatile const uint32_t *src=base;
 int wide=!((uintptr_t)base&7)&&!(stride&1);
 int quad=!((uintptr_t)base&15)&&!(stride&3);
 if(quad){
  for(int row=0;row<height;row++)for(int gx=(x&~7);gx<x+width;gx+=8){
   unsigned use=0;
   if(gx>=x&&gx+8<=x+width){
    uint64_t a,b;memcpy(&a,object+(size_t)row*object_stride+gx-x,8);memcpy(&b,mask+(size_t)row*mask_stride+gx-x,8);
    if(a==UINT64_MAX&&b==UINT64_MAX)use=255;
    else if(a&&b)for(int i=0;i<8;i++)if(((a>>(8*i))&255)&&((b>>(8*i))&255))use|=1u<<i;
   }else for(int i=0;i<8;i++){int local=gx+i-x;if(local>=0&&local<width&&object[(size_t)row*object_stride+local]&&mask[(size_t)row*mask_stride+local])use|=1u<<i;}
   if(use){
    uint64_t pair[2];load_ddr128(src+(size_t)(y+row)*stride+gx/2,&pair[0],&pair[1]);
    /* Identical selected HS values contribute the same eight histogram
     * votes. Keep the original medians and invalid-hue checks exact. */
    if(use==255&&pair[0]==pair[1]&&pair[0]==(uint64_t)(uint16_t)pair[0]*UINT64_C(0x0001000100010001)){
     unsigned h=(unsigned)pair[0]&255u,ss=((unsigned)pair[0]>>8)&255u;if(h>=180)return -2;hue[h]+=8;sat[ss]+=8;count+=8;continue;
    }
    for(int i=0;i<8;i++)if(use&(1u<<i)){uint32_t pixel=(uint32_t)(pair[i/4]>>((i%4)*16));uint32_t h=pixel&255u,ss=(pixel>>8)&255u;if(h>=180)return -2;hue[h]++;sat[ss]++;count++;}
   }
  }
 }else if(wide){
  for(int row=0;row<height;row++)for(int gx=(x&~3);gx<x+width;gx+=4){
   unsigned use=0;
   for(int i=0;i<4;i++){int local=gx+i-x;if(local>=0&&local<width&&object[(size_t)row*object_stride+local]&&mask[(size_t)row*mask_stride+local])use|=1u<<i;}
   if(use){
    uint64_t quad=*(volatile const uint64_t *)(src+(size_t)(y+row)*stride+gx/2);
    for(int i=0;i<4;i++)if(use&(1u<<i)){uint32_t pixel=(uint32_t)(quad>>(i*16));uint32_t h=pixel&255u,ss=(pixel>>8)&255u;if(h>=180)return -2;hue[h]++;sat[ss]++;count++;}
   }
  }
 }else{
 for(int row=0;row<height;row++)for(int gx=(x&~1);gx<x+width;gx+=2){
  int i0=gx-x,i1=i0+1;
  int use0=i0>=0&&i0<width&&object[(size_t)row*object_stride+i0]&&mask[(size_t)row*mask_stride+i0];
  int use1=i1>=0&&i1<width&&object[(size_t)row*object_stride+i1]&&mask[(size_t)row*mask_stride+i1];
  if(use0||use1){
   uint32_t pair=src[(size_t)(y+row)*stride+gx/2];
   if(use0){uint32_t h=pair&255u,s=(pair>>8)&255u;if(h>=180)return -2;hue[h]++;sat[s]++;count++;}
   if(use1){uint32_t h=(pair>>16)&255u,s=(pair>>24)&255u;if(h>=180)return -2;hue[h]++;sat[s]++;count++;}
  }
 }
 }
 if(!count)return -3;
 uint32_t left=(count-1)/2,right=count/2,sum=0;float cost_a=0,cost_b=0;int have_a=0;
 for(int i=0;i<180;i++){uint32_t h=order[i];if(h>=180)return -4;sum+=hue[h];if(!have_a&&sum>left){cost_a=costs[h];have_a=1;}if(sum>right){cost_b=costs[h];break;}}
 double s_a=0,s_b=0;sum=0;have_a=0;
 for(int i=0;i<256;i++){sum+=sat[i];if(!have_a&&sum>left){s_a=i;have_a=1;}if(sum>right){s_b=i;break;}}
 out[0]=(double)((cost_a+cost_b)*0.5f);out[1]=(s_a+s_b)*0.5;out[2]=count;return 0;
}
/* Compact-camera register writes are restricted to this capability aperture. */
static void barrier(void) {
#ifdef __aarch64__
 __asm__ __volatile__("dsb sy" ::: "memory");
#else
 __sync_synchronize();
#endif
}
int f3p_color_write(uint32_t *base,unsigned offset,uint32_t value) {
 if(!base||((uintptr_t)base&3))return -1;
 volatile uint32_t *r=base;
 if(r[0x300/4]!=0x43414d31u||r[0x3e0/4]!=0x56494431u||r[0x380/4]!=0x434c5231u)return -2;
 if(offset==0x384){if((value&0xfffffffcU)!=0x434c0000u)return -3;}
 else {
  if((r[0x384/4]&1)||(r[0x390/4]&8))return -4;
  switch(offset){
   case 0x39c:if((value&65535)>=(value>>16)||(value>>16)>480)return -5;break;
   case 0x3a0:if((value&65535)>=(value>>16)||(value>>16)>270)return -5;break;
   case 0x3a4:if(value>65535)return -5;break;
   case 0x3a8:if((value>>16)!=0x4c55||((value>>8)&255)>=180||(value&255)>15)return -5;break;
   case 0x3ac:break;
   default:return -3;
  }
 }
 barrier();r[offset/4]=value;barrier();(void)r[offset/4];return 0;
}
int f3p_copy_words(const uint32_t *base,uint32_t *out,size_t count) {
 if(!base||!out||((uintptr_t)base&3)||count>32)return -1;
 volatile const uint32_t *src=base;barrier();for(size_t i=0;i<count;i++)out[i]=src[i];barrier();return 0;
}
int f3p_copy_rgb(const uint32_t *base,uint32_t *out,int width,int height,int stride,int rgb_offset,uint32_t frame_id,uint32_t expected_hash) {
 if(!base||!out||((uintptr_t)base&3)||width!=480||height!=270||stride!=780||rgb_offset!=240)return -1;
 volatile const uint32_t *src=base;uint32_t hash=0;barrier();
 if(!((uintptr_t)base&15)){
  for(int y=0;y<height;y++)for(int x=0;x<width;x+=4){
   uint64_t pair[2];load_ddr128(src+(size_t)y*stride+rgb_offset+x,&pair[0],&pair[1]);
   for(int i=0;i<4;i++){
    uint32_t word=(uint32_t)(pair[i/2]>>((i%2)*32));if((word>>24)!=(frame_id&255))return -2;
    out[(size_t)y*width+x+i]=word;hash=((hash<<5)|(hash>>27))^(word&0xffffffu);
   }
  }
 }else if(!((uintptr_t)base&7)){
  for(int y=0;y<height;y++)for(int x=0;x<width;x+=2){
   uint64_t pair=*(volatile const uint64_t *)(src+(size_t)y*stride+rgb_offset+x);uint32_t low=(uint32_t)pair,high=(uint32_t)(pair>>32);
   if((low>>24)!=(frame_id&255)||(high>>24)!=(frame_id&255))return -2;
   out[(size_t)y*width+x]=low;out[(size_t)y*width+x+1]=high;
   hash=((hash<<5)|(hash>>27))^(low&0xffffffu);hash=((hash<<5)|(hash>>27))^(high&0xffffffu);
  }
 }else{
 for(int y=0;y<height;y++)for(int x=0;x<width;x++){
  uint32_t word=src[(size_t)y*stride+rgb_offset+x];if((word>>24)!=(frame_id&255))return -2;
  out[(size_t)y*width+x]=word;hash=((hash<<5)|(hash>>27))^(word&0xffffffu);
 }
 }
 barrier();return hash==expected_hash?0:-3;
}

/* Cached CPU images only: canonical OpenCV integer HSV, independent of HAL. */
static const int32_t hsv_sdiv[256]={0,1044480,522240,348160,261120,208896,174080,149211,130560,116053,104448,94953,87040,80345,74606,69632,65280,61440,58027,54973,52224,49737,47476,45412,43520,41779,40172,38684,37303,36017,34816,33693,32640,31651,30720,29842,29013,28229,27486,26782,26112,25475,24869,24290,23738,23211,22706,22223,21760,21316,20890,20480,20086,19707,19342,18991,18651,18324,18008,17703,17408,17123,16846,16579,16320,16069,15825,15589,15360,15137,14921,14711,14507,14308,14115,13926,13743,13565,13391,13221,13056,12895,12738,12584,12434,12288,12145,12006,11869,11736,11605,11478,11353,11231,11111,10995,10880,10768,10658,10550,10445,10341,10240,10141,10043,9947,9854,9761,9671,9582,9495,9410,9326,9243,9162,9082,9004,8927,8852,8777,8704,8632,8561,8492,8423,8356,8290,8224,8160,8097,8034,7973,7913,7853,7795,7737,7680,7624,7569,7514,7461,7408,7355,7304,7253,7203,7154,7105,7057,7010,6963,6917,6872,6827,6782,6739,6695,6653,6611,6569,6528,6487,6447,6408,6369,6330,6292,6254,6217,6180,6144,6108,6073,6037,6003,5968,5935,5901,5868,5835,5803,5771,5739,5708,5677,5646,5615,5585,5556,5526,5497,5468,5440,5412,5384,5356,5329,5302,5275,5249,5222,5196,5171,5145,5120,5095,5070,5046,5022,4998,4974,4950,4927,4904,4881,4858,4836,4813,4791,4769,4748,4726,4705,4684,4663,4642,4622,4601,4581,4561,4541,4522,4502,4483,4464,4445,4426,4407,4389,4370,4352,4334,4316,4298,4281,4263,4246,4229,4212,4195,4178,4161,4145,4128,4112,4096};
static const int32_t hsv_hdiv[256]={0,122880,61440,40960,30720,24576,20480,17554,15360,13653,12288,11171,10240,9452,8777,8192,7680,7228,6827,6467,6144,5851,5585,5343,5120,4915,4726,4551,4389,4237,4096,3964,3840,3724,3614,3511,3413,3321,3234,3151,3072,2997,2926,2858,2793,2731,2671,2614,2560,2508,2458,2409,2363,2318,2276,2234,2194,2156,2119,2083,2048,2014,1982,1950,1920,1890,1862,1834,1807,1781,1755,1731,1707,1683,1661,1638,1617,1596,1575,1555,1536,1517,1499,1480,1463,1446,1429,1412,1396,1381,1365,1350,1336,1321,1307,1293,1280,1267,1254,1241,1229,1217,1205,1193,1182,1170,1159,1148,1138,1127,1117,1107,1097,1087,1078,1069,1059,1050,1041,1033,1024,1016,1007,999,991,983,975,968,960,953,945,938,931,924,917,910,904,897,890,884,878,871,865,859,853,847,842,836,830,825,819,814,808,803,798,793,788,783,778,773,768,763,759,754,749,745,740,736,731,727,723,719,714,710,706,702,698,694,690,686,683,679,675,671,668,664,661,657,654,650,647,643,640,637,633,630,627,624,621,617,614,611,608,605,602,599,597,594,591,588,585,582,580,577,574,572,569,566,564,561,559,556,554,551,549,546,544,541,539,537,534,532,530,527,525,523,521,518,516,514,512,510,508,506,504,502,500,497,495,493,492,490,488,486,484,482};
int f3p_bgr_to_hsv(const uint8_t *src,uint8_t *dst,int width,int height,size_t src_stride,size_t dst_stride) {
 if(!src||!dst||width<1||width>8192||height<1||height>8192||src_stride<(size_t)width*3||dst_stride<(size_t)width*3)return -1;
 for(int y=0;y<height;y++) {
  const uint8_t *in=src+(size_t)y*src_stride;uint8_t *out=dst+(size_t)y*dst_stride;
  for(int x=0;x<width;x++,in+=3,out+=3) {
   int b=in[0],g=in[1],r=in[2];int maximum=r>g?r:g;maximum=maximum>b?maximum:b;
   int minimum=r<g?r:g;minimum=minimum<b?minimum:b;int difference=maximum-minimum;
   int numerator=maximum==r?g-b:maximum==g?b-r+2*difference:r-g+4*difference;
   int scaled=numerator*hsv_hdiv[difference]+2048;
   int hue=scaled>=0?scaled/4096:-((-scaled+4095)/4096);if(hue<0)hue+=180;
   out[0]=(uint8_t)hue;out[1]=(uint8_t)((difference*hsv_sdiv[maximum]+2048)>>12);out[2]=(uint8_t)maximum;
  }
 }
 return 0;
}

#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdlib.h>
typedef struct {int x0,x1,y,parent,size,lx,rx,ly,ry;} Run;
static int root_of(Run *runs,int id) {
 int root=id;while(runs[root].parent!=root)root=runs[root].parent;
 while(runs[id].parent!=id){int next=runs[id].parent;runs[id].parent=root;id=next;}
 return root;
}
static void join_runs(Run *runs,int a,int b) {
 a=root_of(runs,a);b=root_of(runs,b);if(a==b)return;
 if(runs[a].size<runs[b].size){int tmp=a;a=b;b=tmp;}
 runs[b].parent=a;runs[a].size+=runs[b].size;
 if(runs[b].lx<runs[a].lx)runs[a].lx=runs[b].lx;
 if(runs[b].rx>runs[a].rx)runs[a].rx=runs[b].rx;
 if(runs[b].ly<runs[a].ly)runs[a].ly=runs[b].ly;
 if(runs[b].ry>runs[a].ry)runs[a].ry=runs[b].ry;
}
/* An external contour fits its 8-connected component's pixel-center bounding
 * rectangle. Remove only components with (max_x-min_x)*(max_y-min_y)<min_area.
 * Scan horizontal runs to avoid per-foreground-pixel queue and divisions. */
int f3p_contour_candidates(const uint8_t *src,int stride,uint8_t *dst,int width,int height,double min_area,uint32_t *workspace,size_t capacity) {
 if(!src||!dst||!workspace||((uintptr_t)workspace&3)||width<1||width>480||height<1||height>270||stride<width||capacity<(size_t)width*height||!(min_area>=0))return -1;
 size_t cap=capacity*sizeof(uint32_t)/sizeof(Run);Run *runs=(Run *)workspace;int owned=0,count=0,prev_start=0,prev_end=0;
 memset(dst,0,(size_t)width*height);
 for(int y=0;y<height;y++){
  const uint8_t *row=src+(size_t)y*stride;int start=count,previous=prev_start;
  for(int x=0;x<width;){
   /* These are ordinary cached mask bytes, never device/register memory.
    * Skip homogeneous eight-byte runs without crossing a row boundary. */
   while(x+8<=width){uint64_t word;memcpy(&word,row+x,8);if(word)break;x+=8;}
   while(x<width&&!row[x])x++;
   if(x==width)break;
   int x0=x;
   while(x+8<=width){uint64_t word;memcpy(&word,row+x,8);if(word!=UINT64_MAX)break;x+=8;}
   while(x<width&&row[x]){x++;}
   int x1=x-1;
   if((size_t)count==cap){
    size_t next=cap?cap*2:8;Run *grown=malloc(next*sizeof(Run));
    if(!grown){if(owned)free(runs);return -2;}
    memcpy(grown,runs,(size_t)count*sizeof(Run));if(owned)free(runs);runs=grown;cap=next;owned=1;
   }
   int id=count++;Run current={x0,x1,y,id,1,x0,x1,y,y};runs[id]=current;
   while(previous<prev_end&&runs[previous].x1<x0-1)previous++;
   for(int j=previous;j<prev_end&&runs[j].x0<=x1+1;j++)join_runs(runs,id,j);
  }
  prev_start=start;prev_end=count;
 }
 int removed=0;
 /* The external contour is inside the horizontal envelope of its component
  * on every integer row. Its area cannot exceed the sum of row spans.
  * This tightens the bounding-box proof without removing a valid contour. */
 for(int i=0;i<count;i++)if(runs[i].parent==i){
  int keep=(double)((runs[i].rx-runs[i].lx)*(runs[i].ry-runs[i].ly))>=min_area;
  runs[i].size=0;runs[i].lx=width;runs[i].rx=0;runs[i].ly=-1;runs[i].ry=keep;
 }
 for(int i=0;i<count;i++){
  int root=root_of(runs,i);Run *r=&runs[root];
  if(!r->ry)continue;
  if(r->ly!=runs[i].y){
   if(r->ly>=0)r->size+=r->rx-r->lx;
   r->ly=runs[i].y;r->lx=runs[i].x0;r->rx=runs[i].x1;
  }else{
   if(runs[i].x0<r->lx)r->lx=runs[i].x0;
   if(runs[i].x1>r->rx)r->rx=runs[i].x1;
  }
 }
 for(int i=0;i<count;i++)if(runs[i].parent==i){
  if(runs[i].ry&&(double)(runs[i].size+runs[i].rx-runs[i].lx)<min_area)runs[i].ry=0;
  if(!runs[i].ry)removed++;
 }
 for(int i=0;i<count;i++){
  int root=root_of(runs,i);
  if(runs[root].ry)memset(dst+(size_t)runs[i].y*width+runs[i].x0,255,(size_t)(runs[i].x1-runs[i].x0+1));
 }
 if(owned)free(runs);
 return removed;
}

/* Copy only HS16 and colour masks to ordinary cached CPU memory. RGB stays in
 * the guarded hardware slot and is read/hashed separately for a fresh preview. */
int f3p_copy_features(const uint32_t *base,uint32_t *out,int width,int height,int stride) {
 if(!base||!out||((uintptr_t)base&3)||((uintptr_t)out&3)||width!=480||height!=270||stride!=780)return -1;
 volatile const uint32_t *src=base;int group=!((uintptr_t)base&15)?4:!((uintptr_t)base&7)?2:1;barrier();
 for(int y=0;y<height;y++)for(int section=0;section<2;section++) {
  int start=section?720:0,count=section?60:240;
  for(int i=0;i<count;i+=group){
   size_t pos=(size_t)y*stride+start+i;
   if(group==4){uint64_t lo,hi;load_ddr128(src+pos,&lo,&hi);out[pos]=(uint32_t)lo;out[pos+1]=(uint32_t)(lo>>32);out[pos+2]=(uint32_t)hi;out[pos+3]=(uint32_t)(hi>>32);}
   else if(group==2){uint64_t pair=*(volatile const uint64_t *)(src+pos);out[pos]=(uint32_t)pair;out[pos+1]=(uint32_t)(pair>>32);}
   else out[pos]=src[pos];
  }
 }
 barrier();return 0;
}

/* A confidence sample is used only where a final colour mask is nonzero.
 * Copy every mask, then copy each HS16 load group iff any of its pixels is
 * classified. Zero unused HS groups. Full-copy ABI remains available above.
 * Both copies still require the caller's physical header/age verification. */
int f3p_copy_classified_features(const uint32_t *base,uint32_t *out,int width,int height,int stride) {
 if(!base||!out||((uintptr_t)base&3)||((uintptr_t)out&3)||width!=480||height!=270||stride!=780)return -1;
 volatile const uint32_t *src=base;
 int group=!((uintptr_t)base&15)?4:!((uintptr_t)base&7)?2:1;barrier();
 for(int y=0;y<height;y++) {
  size_t row=(size_t)y*stride;
  for(int i=0;i<60;i+=group) {
   size_t pos=row+720+i;
   if(group==4){uint64_t lo,hi;load_ddr128(src+pos,&lo,&hi);out[pos]=(uint32_t)lo;out[pos+1]=(uint32_t)(lo>>32);out[pos+2]=(uint32_t)hi;out[pos+3]=(uint32_t)(hi>>32);}
   else if(group==2){uint64_t pair=*(volatile const uint64_t *)(src+pos);out[pos]=(uint32_t)pair;out[pos+1]=(uint32_t)(pair>>32);}
   else out[pos]=src[pos];
  }
  for(int i=0;i<240;i+=group) {
   uint32_t active=out[row+720+i/4]>>((i&3)*8);
   if(group==2)active&=65535u;
   if(group==1)active&=255u;
   size_t pos=row+i;
   if(!active){for(int j=0;j<group;j++)out[pos+j]=0;continue;}
   if(group==4){uint64_t lo,hi;load_ddr128(src+pos,&lo,&hi);out[pos]=(uint32_t)lo;out[pos+1]=(uint32_t)(lo>>32);out[pos+2]=(uint32_t)hi;out[pos+3]=(uint32_t)(hi>>32);}
   else if(group==2){uint64_t pair=*(volatile const uint64_t *)(src+pos);out[pos]=(uint32_t)pair;out[pos+1]=(uint32_t)(pair>>32);}
   else out[pos]=src[pos];
  }
 }
 barrier();return 0;
}

/* Apply independent saturation floors to unpacked masks. Read only HS16
 * groups containing a stricter colour, directly from the retained slot.
 * No full feature copy, RGB access, or per-pixel Python arrays are needed. */
int f3p_filter_saturation(const uint32_t *base,uint8_t *planes,int width,int height,int stride,const uint8_t *floors) {
 if(!base||!planes||!floors||((uintptr_t)base&3)||width!=480||height!=270||stride!=780)return -1;
 unsigned minimum=255;size_t area=(size_t)width*height;
 for(int c=0;c<4;c++){if(floors[c]<10||floors[c]>240)return -2;if(floors[c]<minimum)minimum=floors[c];}
 volatile const uint32_t *src=base;barrier();
 for(int y=0;y<height;y++)for(int x=0;x<width;x+=8){
  size_t pixel=(size_t)y*width+x;int active=0;
  for(int c=0;c<4;c++)if(floors[c]>minimum){uint64_t bits;memcpy(&bits,planes+c*area+pixel,8);active|=bits!=0;}
  if(!active)continue;
  uint64_t hs[2];size_t pos=(size_t)y*stride+x/2;
  if(!((uintptr_t)(src+pos)&15))load_ddr128(src+pos,&hs[0],&hs[1]);
  else{hs[0]=(uint64_t)src[pos]|((uint64_t)src[pos+1]<<32);hs[1]=(uint64_t)src[pos+2]|((uint64_t)src[pos+3]<<32);}
#ifdef __aarch64__
  uint8x16_t bytes=vreinterpretq_u8_u64(vcombine_u64(vcreate_u64(hs[0]),vcreate_u64(hs[1])));
  uint8x8_t saturation=vuzp_u8(vget_low_u8(bytes),vget_high_u8(bytes)).val[1];
  for(int c=0;c<4;c++)if(floors[c]>minimum){uint8_t *dst=planes+c*area+pixel;vst1_u8(dst,vand_u8(vld1_u8(dst),vcge_u8(saturation,vdup_n_u8(floors[c]))));}
#else
  for(int i=0;i<8;i++){unsigned saturation=(unsigned)(hs[i/4]>>((i%4)*16+8))&255u;for(int c=0;c<4;c++)if(floors[c]>minimum&&saturation<floors[c])planes[c*area+pixel+i]=0;}
#endif
 }
 barrier();return 0;
}
