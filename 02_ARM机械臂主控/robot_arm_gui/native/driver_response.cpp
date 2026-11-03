// Same deterministic 5ms response model as driver_tracking.assess.
// Independent optional library: existing math ABI and firmware are untouched.
#include "arm_math.cpp"
#include <vector>
API int f3p_response_abi(){return 1;}
static std::vector<double> equivalents(double value,int axis,const double*seed,const double*limits,const double*rule,double q3){
 double lo=limits[2*axis],hi=limits[2*axis+1];
 if(axis==3&&rule[0]&&(q3-rule[9])*rule[3]>34){lo=rule[4]*rule[13]+rule[10];hi=rule[4]*rule[14]+rule[10];if(lo>hi)std::swap(lo,hi);}
 if(!std::isfinite(lo)||!std::isfinite(hi))return {value+360*std::nearbyint((seed[axis]-value)/360)};
 std::vector<double> result;double first=std::ceil((lo-value-1e-8)/360),last=std::floor((hi-value+1e-8)/360);
 if(last-first>1000)return result;
 for(double n=first;n<=last;n++)result.push_back(value+360*n);return result;
}
API int f3p_fixed_pose(const double*g,const double*xyz,const double*rotation,const double*seed,const double*limits,const double*rule,double*out){
 double wrist[3];for(int i=0;i<3;i++)wrist[i]=xyz[i]-39.5*rotation[i*3+2];
 double radius=std::hypot(wrist[0],wrist[1]);if(radius<1e-8)return 0;
 double length=std::hypot(142.3,15.),beta=std::atan2(142.3,15.)*180/PI;
 double az=std::atan2(wrist[1],wrist[0])*180/PI,z=wrist[2]-170,best=INFINITY;
 for(int shoulder:{1,-1}){
  double radial=shoulder*radius-37.5,cosine=(radial*radial+z*z-160*160-length*length)/(320*length);
  if(std::abs(cosine)>1+1e-10)continue;double bend=std::acos(std::max(-1.,std::min(1.,cosine)))*180/PI;
  for(double q1:equivalents(az+(shoulder<0?180:0),0,seed,limits,rule,0))for(int elbow:{1,-1})
   for(double q3:equivalents(elbow*bend-beta,2,seed,limits,rule,0)){
    double theta=deg(beta+q3),base=(std::atan2(radial,z)-std::atan2(length*std::sin(theta),160+length*std::cos(theta)))*180/PI;
    for(double q2:equivalents(base,1,seed,limits,rule,q3)){
     double q[6]={q1,q2,q3,0,0,0},a[16],n[3]={};chain(g,q,a,nullptr,nullptr,nullptr);
     for(int j=0;j<3;j++)for(int i=0;i<3;i++)n[j]+=a[4*i+j]*rotation[3*i+2];
     double angle=std::acos(std::max(-1.,std::min(1.,n[2])))*180/PI;
     for(int sign:{1,-1})for(double q5:equivalents(sign*angle,4,seed,limits,rule,q3)){
      double sn=std::sin(deg(q5));std::vector<double> rolls;
      if(std::abs(sn)<1e-6)rolls={seed[3],0,90,180};else rolls={std::atan2(-n[1]/sn,-n[0]/sn)*180/PI};
      for(double roll:rolls)for(double q4:equivalents(roll,3,seed,limits,rule,q3)){
       q[3]=q4;q[4]=q5;q[5]=0;double ref[16];chain(g,q,ref,nullptr,nullptr,nullptr);
       double y=0,x=0;for(int i=0;i<3;i++){y+=ref[4*i+1]*rotation[3*i];x+=ref[4*i]*rotation[3*i];}
       double yaw=std::atan2(y,x)*180/PI;
       for(double q6:equivalents(yaw,5,seed,limits,rule,q3)){
        q[5]=q6;double t[16];chain(g,q,t,nullptr,nullptr,nullptr);double pe=0,re=0;
        for(int i=0;i<3;i++){double d=xyz[i]-t[4*i+3];pe+=d*d;for(int j=0;j<3;j++)re=std::max(re,std::abs(t[4*i+j]-rotation[3*i+j]));}
        if(std::sqrt(pe)>.01||re>1e-6)continue;
        if(rule[0]&&(q3-rule[9])*rule[3]>34){double d=(q4-rule[10])*rule[4];if(d<rule[13]||d>rule[14])continue;}
        double score=0;for(int j=0;j<6;j++){double d=q[j]-seed[j];score+=d*d;}
        if(score<best){best=score;std::copy(q,q+6,out);}
       }
      }
     }
    }
   }
 }
 return std::isfinite(best)?1:0;
}
struct Interval{double lo,hi;};
static Interval add(Interval a,Interval b){return {a.lo+b.lo,a.hi+b.hi};}
static Interval scale(Interval a,double b){return {std::min(a.lo*b,a.hi*b),std::max(a.lo*b,a.hi*b)};}
static Interval mul(Interval a,Interval b){double v[]={a.lo*b.lo,a.lo*b.hi,a.hi*b.lo,a.hi*b.hi};return {*std::min_element(v,v+4),*std::max_element(v,v+4)};}
static Interval trig(Interval a,bool cosine=false){
 double lo=deg(a.lo),hi=deg(a.hi);if(cosine){lo+=PI/2;hi+=PI/2;}
 if(!std::isfinite(lo)||!std::isfinite(hi)||std::abs(lo)>1e12||std::abs(hi)>1e12)return {NAN,NAN};
 if(hi-lo>=2*PI)return {-1,1};Interval r={std::min(std::sin(lo),std::sin(hi)),std::max(std::sin(lo),std::sin(hi))};
 for(double n=std::ceil((lo-PI/2)/PI);n<=std::floor((hi-PI/2)/PI);n++){double v=std::fmod(std::abs(n),2)==0?1:-1;r.lo=std::min(r.lo,v);r.hi=std::max(r.hi,v);}return r;
}
static Interval height(const double*a,const double*b){
 Interval box[6];for(int i=0;i<6;i++)box[i]={std::min(a[i],b[i]),std::max(a[i],b[i])};
 Interval bend=add(box[1],box[2]),c=trig(bend,true),s=trig(bend);
 Interval z=add({170,170},scale(trig(box[1],true),160));z=add(z,add(scale(c,15),scale(s,-142.3)));
 return add(z,scale(add(mul(s,trig(box[4],true)),mul(mul(c,trig(box[3],true)),trig(box[4]))),-39.5));
}
API double f3p_box_height(const double*a,const double*b){return height(a,b).lo;}
API int f3p_rule_box(const double*r,const double*a,const double*b){
 if(!r[0])return 1;
 for(int i=0;i<6;i++)if(!std::isfinite(a[i])||!std::isfinite(b[i]))return 0;
 double j3=std::max((a[2]-r[9])*r[3],(b[2]-r[9])*r[3]);
 double x=(a[3]-r[10])*r[4],y=(b[3]-r[10])*r[4];
 return j3<=34||(std::min(x,y)>=r[13]&&std::max(x,y)<=r[14]);
}
// On any unproved condition return 0 and let the original Python checks run.
// cfg: PPR, nominal RPM, acceleration RPM/s, wire RPM, limits pairs.
API int f3p_curve_frames(const double*g,const double*m,const double*origin,const double*rows,
 const double*points,const double*budgets,const double*cfg,int total,int count,int ahead,double tick,
 int strict,double*out){
 if(total!=count+ahead||count<1||ahead<1||tick<=0)return 0;
 // Each output scratch row has motor[6], quantized motor[6], pulses[6], speed[6].
 for(int k=0;k<total;k++){
  const double*q=rows+10*k;double*o=out+24*k,qq[6],error[2];
  for(int i=0;i<10;i++)if(!std::isfinite(q[i]))return 0;
  for(int j=0;j<6;j++){
   o[j]=m[j]+m[12+j]*m[18+j]*(q[j]-m[6+j]);
   o[12+j]=std::nearbyint(o[j]*cfg[j]/360);o[6+j]=o[12+j]*360/cfg[j];
   if(o[12+j]<-2147483648.||o[12+j]>2147483647.||std::abs(o[j])*65536/360>4294967295.||std::abs(o[6+j])*65536/360>4294967295.)return 0;
   qq[j]=m[6+j]+m[12+j]*(o[6+j]-m[j])/m[18+j];
   double lo=cfg[24+2*j],hi=cfg[25+2*j];
   if(q[j]<lo-1e-9||q[j]>hi+1e-9||qq[j]<lo-1e-9||qq[j]>hi+1e-9)return 0;
  }
  f3p_q_pose_norms(g,q,origin,q+6,error);if(!std::isfinite(error[0])||!std::isfinite(error[1])||error[0]>budgets[k]||error[1]>.12)return 0;
  if(strict&&(error[0]>.01||error[1]>.02))return 0;
  f3p_q_pose_norms(g,qq,origin,q+6,error);if(!std::isfinite(error[0])||!std::isfinite(error[1])||error[0]>budgets[k]||error[1]>.12)return 0;
 }
 for(int k=0;k<total-1;k++)for(int j=0;j<6;j++){
  if(std::abs(rows[(k+1)*10+j]-rows[k*10+j])>5)return 0;
  double v=(out[(k+1)*24+j]-out[k*24+j])/(6*tick);if(std::abs(v)>cfg[6+j]*1.015)return 0;
  if(k<total-2){double next=(out[(k+2)*24+j]-out[(k+1)*24+j])/(6*tick);if(std::abs(next-v)/tick>cfg[12+j]*.7*1.015)return 0;}
 }
 for(int k=0;k<count;k++){
  const double*q=rows+10*k,*cq=rows+10*(k+ahead);double qq[6];
  for(int j=0;j<6;j++)qq[j]=m[6+j]+m[12+j]*(out[(k+ahead)*24+6+j]-m[j])/m[18+j];
  if(!f3p_rule_box(cfg+36,q,qq))return 0;
  // Conservative fast proof; near-table cases use Python subdivision.
  if(!(height(q,qq).lo>1e-8))return 0;
  for(int i=0;i<3;i++){
   double fraction=(i+1)*.25,iq[6],error[2];for(int j=0;j<6;j++)iq[j]=q[j]+fraction*(cq[j]-q[j]);
   f3p_q_pose_norms(g,iq,origin,points+9*k+3*i,error);
   if(!std::isfinite(error[0])||!std::isfinite(error[1])||error[0]>budgets[total+3*k+i]||error[1]>.2)return 0;
  }
  for(int j=0;j<6;j++){
   double speed=0;for(int x=k;x<std::min(total-1,std::max(k+ahead,k+1));x++)speed=std::max(speed,std::abs(out[(x+1)*24+j]-out[x*24+j])/(6*tick));
   out[k*24+18+j]=std::min(cfg[18+j],std::max(1.,std::ceil(speed*1.1)));
  }
 }
 return 1;
}
// Restored guide Q, command Q, original path XYZ, command XYZ, three chord XYZ.
API int f3p_restore_frames(const double*g,const double*m,const double*origin,const double*rows,
 const double*cfg,int count,double*out){
 for(int k=0;k<count;k++){
  const double*q=rows+27*k,*cq=q+6;double*o=out+20*k,qq[6],errors[2];
  for(int i=0;i<27;i++)if(!std::isfinite(q[i]))return 0;
  if(q[14]<=0||q[17]<=0)return 0;
  for(int j=0;j<6;j++){
   o[j]=m[j]+m[12+j]*m[18+j]*(q[j]-m[6+j]);
   double cm=m[j]+m[12+j]*m[18+j]*(cq[j]-m[6+j]);
   o[12+j]=std::nearbyint(cm*cfg[j]/360);o[6+j]=o[12+j]*360/cfg[j];
   qq[j]=m[6+j]+m[12+j]*(o[6+j]-m[j])/m[18+j];
   if(o[12+j]<-2147483648.||o[12+j]>2147483647.||std::abs(o[j])*65536/360>4294967295.||std::abs(cm)*65536/360>4294967295.||std::abs(o[6+j])*65536/360>4294967295.)return 0;
   if(q[j]<cfg[6+2*j]-1e-9||q[j]>cfg[7+2*j]+1e-9||cq[j]<cfg[6+2*j]-1e-9||cq[j]>cfg[7+2*j]+1e-9||qq[j]<cfg[6+2*j]-1e-9||qq[j]>cfg[7+2*j]+1e-9)return 0;
  }
  if(!(height(q,qq).lo>1e-8))return 0;
  if(!f3p_rule_box(cfg+18,q,cq)||!f3p_rule_box(cfg+18,q,qq))return 0;
  if(k){
   double previous[6];for(int j=0;j<6;j++)previous[j]=m[6+j]+m[12+j]*(out[(k-1)*20+6+j]-m[j])/m[18+j];
   if(!f3p_rule_box(cfg+18,rows+(k-1)*27,q)||!f3p_rule_box(cfg+18,previous,qq))return 0;
  }
  o[18]=o[19]=0;
  for(int i=0;i<2;i++){
   f3p_q_pose_norms(g,i?cq:q,origin,q+12+3*i,errors);
   if(!std::isfinite(errors[0])||!std::isfinite(errors[1])||errors[0]>.01||errors[1]>.02)return 0;
   o[18]=std::max(o[18],errors[0]);o[19]=std::max(o[19],errors[1]);
  }
  f3p_q_pose_norms(g,qq,origin,q+15,errors);
  if(!std::isfinite(errors[0])||!std::isfinite(errors[1])||errors[0]>.1||errors[1]>.12)return 0;
  for(int i=0;i<3;i++){
   double fraction=(i+1)*.25,iq[6];for(int j=0;j<6;j++)iq[j]=q[j]+fraction*(cq[j]-q[j]);
   f3p_q_pose_norms(g,iq,origin,q+18+3*i,errors);
   if(!std::isfinite(errors[0])||!std::isfinite(errors[1])||errors[0]>.1||errors[1]>.2)return 0;
  }
 }
 return 1;
}
static double segment_distance(const double*p,const double*a,const double*b){
 double d[3],size=0,dot=0;for(int i=0;i<3;i++){d[i]=b[i]-a[i];size+=d[i]*d[i];dot+=(p[i]-a[i])*d[i];}
 double u=size?std::max(0.,std::min(1.,dot/size)):0.,s=0;
 for(int i=0;i<3;i++){double e=p[i]-a[i]-u*d[i];s+=e*e;}return std::sqrt(s);
}
static double orientation(const double*t,const double*origin){
 double trace=0;for(int i=0;i<3;i++)for(int j=0;j<3;j++)trace+=t[4*i+j]*origin[4*i+j];
 double c=std::max(-1.,std::min(1.,(trace-1.)/2));return c>=1.-1e-15?0.:std::acos(c)*180./PI;
}
// State: motor[6], velocity[6], chronological history[9][6], maxima[4].
// Row: motor target[6], RPM[6], ACC[6], reference XYZ[3], command XYZ[3], prep flag.
API int f3p_response_block(const double*g,const double*mapping,const double*origin,
 const double*rows,int total,int begin,int count,double factor,const double*skew,
 int arc,double*state){
 if(total<1||begin<0||count<0||begin+count>total||factor<=0)return -1;
 double*motor=state,*velocity=state+6,*history=state+12,*worst=state+66;
 for(int index=begin;index<begin+count;index++){
  const double*row=rows+25*index;double rates[6];
  for(int i=0;i<25;i++)if(!std::isfinite(row[i]))return -1;
  for(int i=0;i<6;i++){if(row[6+i]<1||row[12+i]<1||row[12+i]>255)return -1;rates[i]=6/((256-row[12+i])*50e-6)*factor;}
  for(int sub=0;sub<8;sub++){
   for(int i=0;i<6;i++){
    double delta=row[i]-motor[i],direction=delta>=0?1:-1;
    double desired=direction*std::min(6*row[6+i],std::sqrt(2*rates[i]*std::abs(delta)));
    double change=std::max(-rates[i]*.005,std::min(rates[i]*.005,desired-velocity[i]));
    double old=velocity[i];velocity[i]+=change;double step=(old+velocity[i])*.0025;
    if(step*delta>=0&&std::abs(step)>=std::abs(delta)){motor[i]=row[i];velocity[i]=0;}else motor[i]+=step;
   }
   std::memmove(history,history+6,48*sizeof(double));std::copy(motor,motor+6,history+48);
  }
  double q[6],t[16],sq[6],st[16],xyz[3],start[3];
  for(int i=0;i<6;i++){
   q[i]=mapping[6+i]+mapping[12+i]*(motor[i]-mapping[i])/mapping[18+i];
   int back=int(skew[i]);if(back<0||back>8)return -1;
   sq[i]=mapping[6+i]+mapping[12+i]*(history[(8-back)*6+i]-mapping[i])/mapping[18+i];
  }
  chain(g,q,t,nullptr,nullptr,nullptr);chain(g,sq,st,nullptr,nullptr,nullptr);
  for(int i=0;i<16;i++)if(!std::isfinite(t[i])||!std::isfinite(st[i]))return -1;
  worst[0]=std::max(worst[0],orientation(t,origin));worst[1]=std::max(worst[1],orientation(st,origin));
  for(int i=0;i<3;i++){xyz[i]=t[4*i+3];start[i]=origin[4*i+3];}
  double error;
  if(row[24]){double v[3];for(int i=0;i<3;i++)v[i]=xyz[i]-start[i];worst[2]=std::max(worst[2],norm(v,3));}
  else{
   if(!arc)error=segment_distance(xyz,start,rows+25*(total-1)+21);
   else{
    error=std::numeric_limits<double>::infinity();int lo=std::max(0,index-30),hi=std::min(total,index+31);
    for(int j=lo;j<hi;j++)error=std::min(error,segment_distance(xyz,rows+25*j+18,rows+25*j+(j+1<hi?43:21)));
   }
   worst[3]=std::max(worst[3],error);
  }
 }
 return 0;
}
