// Independent optional accelerator; keep the installed math library untouched.
#include "arm_math.cpp"

API int f3p_finite_timing_abi(){return 1;}
API void f3p_guide_max_rates(const double*guide,int count,const double*ratios,double*out){
 std::fill(out,out+12,0.);
 for(int k=0;k<count;k++){
  const double*g=guide+26*k;double span=g[1]-g[0];
  for(int j=0;j<6;j++){
   const double*q=g+2+4*j;double c[4]={q[3],q[2],q[1],q[0]};
   out[j]=std::max(out[j],polynomial_bound(c,4,0.,1.,1)/span*std::abs(ratios[j]));
   out[j+6]=std::max(out[j+6],polynomial_bound(c,4,0.,1.,2)/(span*span)*std::abs(ratios[j]));
  }
 }
}
API int f3p_guide_samples(const double*geometry,const double*origin,const double*coeff,
 const double*xyz,const double*limits,double*out){
 for(int k=0;k<4;k++){
  double x=(k+1)/4.,q[6];for(int j=0;j<6;j++){const double*c=coeff+4*j;q[j]=((c[0]*x+c[1])*x+c[2])*x+c[3];}
  f3p_q_pose_norms(geometry,q,origin,xyz+k*3,out);
  if(!std::isfinite(out[0])||!std::isfinite(out[1])||out[0]>.05||out[1]>.05)return 1;
  for(int j=0;j<6;j++)if(q[j]<limits[j*2]||q[j]>limits[j*2+1])return 2;
 }
 return 0;
}
API double f3p_timing_peak(const double*schedule,int count){
 double peak=0;
 for(int j=0;j<count;j++){
  const double*s=schedule+7*j;double d[5];for(int i=0;i<5;i++)d[i]=(i+1)*s[i+2];
  for(int k=0;k<=256;k++)peak=std::max(peak,polynomial_value(d,5,k/256.)/s[0]);
 }
 return peak;
}
API int f3p_timing_samples(const double*c,double begin,double end,double duration,double cap){
 double d[5];for(int i=0;i<5;i++)d[i]=(i+1)*c[i+1];
 double peak=-INFINITY;
 for(int k=0;k<=100;k++){
  double x=k/100.,u=polynomial_value(c,6,x),v=polynomial_value(d,5,x);
  if(!std::isfinite(u)||!std::isfinite(v)||v < -1e-10||u<begin-1e-9||u>end+1e-9)return 1;
  peak=std::max(peak,v/duration);
 }
 return peak>cap*1.001?2:0;
}

// Guide rows: [left, right, six cubic coefficient vectors (a,b,c,d)].
API int f3p_timing_envelope(const double*c,double duration,double begin,double end,
 const double*guide,int count,const double*ratios,const double*nominal,const double*rates,int preview){
 for(int k=0;k<count;k++){
  const double*g=guide+26*k;double left=g[0],right=g[1],lo=std::max(left,begin),hi=std::min(right,end);
  if(hi<=lo)continue;
  double xl=(lo-left)/(right-left),xh=(hi-left)/(right-left),velocity,acceleration=0;
  if(preview)velocity=duration;
  else{
   double a=f3p_inverse_u(c,lo,begin,end,32),b=f3p_inverse_u(c,hi,begin,end,32);
   velocity=polynomial_bound(c,6,a,b,1)/duration;
   acceleration=polynomial_bound(c,6,a,b,2)/(duration*duration);
  }
  for(int j=0;j<6;j++){
   const double*q=g+2+4*j;double coefficients[4]={q[3],q[2],q[1],q[0]};
   double first=polynomial_bound(coefficients,4,xl,xh,1)/(right-left);
   double second=polynomial_bound(coefficients,4,xl,xh,2)/((right-left)*(right-left));
   double scale=std::abs(ratios[j])/6;
   if(first*velocity*scale>nominal[j]*(preview?.7:.9))return 1;
   if((second*velocity*velocity+first*acceleration)*scale>rates[j]*(preview?.5:.7))return 2;
  }
 }
 return 0;
}

static bool guide_q(const double*guide,int count,double u,double*out){
 if(count<1||!std::isfinite(u))return false;
 u=std::max(0.,std::min(1.,u));int lo=0,hi=count;
 while(lo<hi){int mid=(lo+hi)/2;if(guide[mid*26+1]<u)lo=mid+1;else hi=mid;}
 if(lo==count)lo=count-1;
 const double*g=guide+lo*26;if(u>g[1]+1e-12)return false;
 double x=(u-g[0])/(g[1]-g[0]);
 for(int j=0;j<6;j++){const double*q=g+2+j*4;out[j]=((q[0]*x+q[1])*x+q[2])*x+q[3];}
 return true;
}

API int f3p_timing_q_batch(const double*guide,int count,const double*values,int size,double*out){
 for(int k=0;k<size;k++)if(!guide_q(guide,count,values[k],out+k*6))return 0;
 return 1;
}

// Samples retain Python's exact Cartesian points: lo,hi,3 chord xyz triples.
API int f3p_timing_chords(const double*geometry,const double*origin,const double*guide,int count,
 const double*samples,int samples_count,double budget){
 for(int k=0;k<samples_count;k++){
  const double*s=samples+k*11;double qa[6],qb[6];
  if(!guide_q(guide,count,s[0],qa)||!guide_q(guide,count,s[1],qb))return -1;
  for(int i=0;i<3;i++){
   double fraction=(i+1)/4.,q[6],error[2];
   for(int j=0;j<6;j++)q[j]=qa[j]+fraction*(qb[j]-qa[j]);
   f3p_q_pose_norms(geometry,q,origin,s+2+3*i,error);
   if(!std::isfinite(error[0])||error[0]>budget*.7)return 0;
  }
 }
 return 1;
}
